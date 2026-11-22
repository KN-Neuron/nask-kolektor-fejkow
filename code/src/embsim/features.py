"""Cechy przypadku wyciągane bez uczenia: tekst + zbiory śladów (piksele, zestaw strony, schemat adresu, hosty, obrazy).

Zbiory śladów są ogólne (nie dopasowane do żadnego zbioru danych); wagę śladu nadaje rzadkość w korpusie (zob. score.py).

Obrazy (`img`): dokładny odcisk SHA-256 bajtów każdego obrazu strony, z treści odpowiedzi w HAR i z plików przypadku (także zasobów
zapisanej strony `*_files`). Bez modelu i bez uczenia: ten sam plik u dwóch materiałów to wspólny ślad jak piksel czy host. Obrazy
mniejsze niż MIN_IMG_BYTES (ikonki, piksele 1×1, reakcje z widżetów komentarzy) pomijamy, bo krążą między niezależnymi zestawami.
Metadanych EXIF/PNG zrzutów nie używamy: opisują urządzenie osoby zgłaszającej (telefon, narzędzie do zrzutów), nie operatora.

`drop_common=True`: adresy pospolitych usług (Google, Meta, CDN, czcionki) nie dają śladów hosta, zestawu ani schematu. W dużym
korpusie idf sam je wycisza, ale w małej galerii (kilka przypadków) google.com u dwóch z dziesięciu wygląda na rzadki wspólny ślad.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from .material import _walk, html_text, info_text

PIXEL = [re.compile(p) for p in (r"fbq\(\s*['\"]init['\"]\s*,\s*['\"](\d{6,})['\"]", r"\b(GTM-[A-Z0-9]{4,})\b",
                                 r"\b(AW-\d{6,})\b", r"\b(UA-\d{4,}-\d+)\b", r"\b(G-[A-Z0-9]{6,})\b")]
SAVED_FROM = re.compile(r"saved from url=\(\d+\)(\S+)")
IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
MIN_IMG_BYTES = 2048
COMMON_HOSTS = frozenset((
    "google.com", "google.pl", "googleapis.com", "gstatic.com", "googletagmanager.com", "doubleclick.net", "google-analytics.com",
    "googleusercontent.com", "googlesyndication.com", "facebook.com", "facebook.net", "fbcdn.net", "instagram.com", "jsdelivr.net",
    "cloudflare.com", "cloudflareinsights.com", "unpkg.com", "jquery.com", "bootstrapcdn.com", "unsplash.com", "youtube.com",
    "ytimg.com", "vimeo.com", "tiktok.com", "akamaihd.net", "cloudfront.net", "amazonaws.com", "microsoft.com", "clarity.ms",
    "fontawesome.com", "typekit.net", "hotjar.com", "yandex.ru", "x.com", "twitter.com", "w3.org", "schema.org",
))


@dataclass
class Case:
    id: str
    text: str = ""
    sets: dict[str, set[str]] = field(default_factory=dict)  # kanał -> zbiór śladów
    vec: object = None                                         # wektor tekstu z modelu (surowy)
    vec_t: object = None                                       # wektor po korekcie PCA korpusu (uzupełnia score.Corpus; None = brak korekty)
    lex_i: int | None = None                                   # wiersz w macierzy TF-IDF korpusu (uzupełnia score.Corpus)
    lex_vec: object = None                                     # wiersz TF-IDF dla materiału spoza korpusu (zapytanie, późne dodanie)
    meta: dict = field(default_factory=dict)                   # dane opisowe, które nie wchodzą do wyniku (np. page_id, płatnik, daty)


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


# Najczęstsze sufiksy wieloczłonowe (podzbiór Public Suffix List, offline): bez nich `a.com.pl` i `b.com.pl` zlewałyby się w `com.pl`.
MULTI_SUFFIX = {"com.pl", "net.pl", "org.pl", "edu.pl", "gov.pl", "info.pl", "biz.pl", "waw.pl", "krakow.pl", "co.uk", "org.uk", "ac.uk",
                "gov.uk", "com.au", "net.au", "org.au", "co.jp", "com.br", "com.cn", "com.tr", "com.ua", "com.mx", "co.in", "co.za", "co.nz",
                "com.ar", "com.sg", "com.hk", "com.tw", "co.kr", "co.il"}
_IPV4 = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


def registered(host: str) -> str:
    """Domena rejestrowalna: dwa ostatnie człony albo trzy, gdy sufiks jest wieloczłonowy (MULTI_SUFFIX); adres IPv4 zostaje w całości."""
    if _IPV4.match(host):
        return host
    p = host.split(".")
    if len(p) >= 3 and ".".join(p[-2:]) in MULTI_SUFFIX:
        return ".".join(p[-3:])
    return ".".join(p[-2:]) if len(p) >= 2 else host


def scheme_fp(url: str) -> str | None:
    names = sorted({k for k, _ in parse_qsl(urlsplit(url).query, keep_blank_values=True)})
    return ",".join(names) if names else None


def prefixes(url: str) -> str | None:
    seg = [s for s in urlsplit(url).path.split("/") if s]
    return "/" + "/".join(seg[:-1][:2]) if len(seg) >= 2 else None  # katalog zasobów (bez nazwy pliku)


def is_common(host: str) -> bool:
    return registered(host) in COMMON_HOSTS


def img_key(data: bytes) -> str | None:
    return hashlib.sha256(data).hexdigest()[:16] if len(data) >= MIN_IMG_BYTES else None


def har_images(entries: list[dict]) -> list[tuple[str, bytes]]:
    """(adres, bajty) obrazów zapisanych w HAR (treść odpowiedzi base64 albo tekst, np. SVG)."""
    out = []
    for e in entries:
        ct = (e.get("response") or {}).get("content") or {}
        if not str(ct.get("mimeType", "")).startswith("image/") or not ct.get("text"):
            continue
        try:
            data = base64.b64decode(ct["text"]) if ct.get("encoding") == "base64" else ct["text"].encode()
        except (ValueError, TypeError):
            continue
        out.append((e.get("request", {}).get("url", ""), data))
    return out


def load_case(root: Path, drop_common: bool = False) -> Case:
    c = Case(root.name)
    texts, urls = [], []
    sets: dict[str, set[str]] = {k: set() for k in ("pixel", "kit", "scheme", "host", "img")}
    names: dict[str, str] = {}

    def add_img(name: str, data: bytes) -> None:
        if k := img_key(data):
            sets["img"].add(k)
            names.setdefault(k, name.rsplit("/", 1)[-1].split("?")[0][:60] or k)

    blobs: list[tuple[str, bytes]] = []          # obrazy do wykrywania twarzy (embsim/faces.py)
    for p in root.rglob("*"):                    # obrazy także z zasobów strony (`*_files`), które _walk pomija
        if p.is_file() and p.suffix.lower() in IMG_EXT:
            blobs.append((p.name, p.read_bytes()))
            add_img(p.name, blobs[-1][1])
    for p in _walk(root):
        ext = p.suffix.lower()
        if ext in {".html", ".htm"}:
            raw = p.read_text(encoding="utf-8", errors="ignore")
            if t := html_text(p):
                texts.append(t)
            for rx in PIXEL:
                sets["pixel"].update(rx.findall(raw))
            if m := SAVED_FROM.search(raw):
                urls.append(m.group(1))
        elif p.name.endswith(".info.json"):
            try:
                if t := info_text(p):
                    texts.append(t)
            except (ValueError, OSError):
                pass
        elif ext == ".har":
            try:
                entries = json.loads(p.read_text(encoding="utf-8", errors="ignore"))["log"]["entries"]
            except (ValueError, KeyError):
                continue
            urls += [e["request"]["url"] for e in entries]
            for u, data in har_images(entries):
                add_img(u, data)
                blobs.append((u, data))
    for u in urls:
        h = host_of(u)
        if drop_common and h and is_common(h):
            continue
        if h:
            sets["host"].add(registered(h))
        if k := prefixes(u):
            sets["kit"].add(k)
        if s := scheme_fp(u):
            sets["scheme"].add(s)
    c.text = "\n".join(texts)
    c.sets = {k: v for k, v in sets.items() if v}  # pusty kanał = brak danych, nie „brak podobieństwa”
    if names:
        c.meta["img_names"] = names
    if blobs and os.environ.get("EMBSIM_FACES", "1") != "0":
        from .faces import faces_of

        if f := faces_of(blobs):
            c.meta["faces"] = f                 # osadzenia twarzy (przesłanka, embsim/faces.py)
        from .imghash import hashes_of

        if hh := hashes_of(blobs, img_key):
            c.meta["dhash"] = hh                # odciski percepcyjne obrazów (przesłanka, embsim/imghash.py)
    return c
