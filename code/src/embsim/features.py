"""Cechy przypadku wyciągane bez uczenia: tekst + zbiory śladów (piksele, zestaw strony, schemat adresu, hosty).

Zbiory śladów są ogólne (nie dopasowane do żadnego zbioru danych); wagę śladu nadaje rzadkość w korpusie (zob. score.py).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from .material import _walk, html_text, info_text

PIXEL = [re.compile(p) for p in (r"fbq\(\s*['\"]init['\"]\s*,\s*['\"](\d{6,})['\"]", r"\b(GTM-[A-Z0-9]{4,})\b",
                                 r"\b(AW-\d{6,})\b", r"\b(UA-\d{4,}-\d+)\b", r"\b(G-[A-Z0-9]{6,})\b")]
SAVED_FROM = re.compile(r"saved from url=\(\d+\)(\S+)")


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


def registered(host: str) -> str:
    """Przybliżenie domeny rejestrowalnej (bez listy sufiksów): dwa ostatnie człony."""
    p = host.split(".")
    return ".".join(p[-2:]) if len(p) >= 2 else host


def scheme_fp(url: str) -> str | None:
    names = sorted({k for k, _ in parse_qsl(urlsplit(url).query, keep_blank_values=True)})
    return ",".join(names) if names else None


def prefixes(url: str) -> str | None:
    seg = [s for s in urlsplit(url).path.split("/") if s]
    return "/" + "/".join(seg[:-1][:2]) if len(seg) >= 2 else None  # katalog zasobów (bez nazwy pliku)


def load_case(root: Path) -> Case:
    c = Case(root.name)
    texts, urls = [], []
    sets: dict[str, set[str]] = {k: set() for k in ("pixel", "kit", "scheme", "host")}
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
    for u in urls:
        if h := host_of(u):
            sets["host"].add(registered(h))
        if k := prefixes(u):
            sets["kit"].add(k)
        if s := scheme_fp(u):
            sets["scheme"].add(s)
    c.text = "\n".join(texts)
    c.sets = {k: v for k, v in sets.items() if v}  # pusty kanał = brak danych, nie „brak podobieństwa”
    return c
