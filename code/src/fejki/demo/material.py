"""Materiał = jeden incydent (folder przypadku albo pojedyncze wejście) i jego cechy.

Ekstrakcja działa na tym, co jest: brak HAR, HTML czy zrzutu nie przerywa analizy, tylko trafia do `missing`.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import numpy as np
from pydantic import BaseModel, Field

from ..config import ROOT
from ..process.extract import extract_artifacts, registered_domain

HTML_EXT = {".html", ".htm", ".mhtml"}
IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
VID_EXT = {".mp4", ".mov", ".webm", ".m4v"}

# Hosty infrastruktury ogólnej: wspólne dla milionów stron, więc nie są śladem kampanii.
COMMON_HOSTS = (
    "google.com", "google.pl", "googleapis.com", "gstatic.com", "googletagmanager.com", "doubleclick.net", "google-analytics.com",
    "facebook.com", "facebook.net", "fbcdn.net", "instagram.com", "jsdelivr.net", "cloudflare.com", "cdnjs.cloudflare.com",
    "unpkg.com", "jquery.com", "bootstrapcdn.com", "unsplash.com", "youtube.com", "ytimg.com", "vimeo.com", "tiktok.com",
    "netlify.app", "b-cdn.net", "akamaihd.net", "cloudfront.net", "amazonaws.com", "microsoft.com", "clarity.ms",
    "er-api.com", "fontawesome.com", "typekit.net", "hotjar.com", "yandex.ru", "matomo.cloud", "x.com", "twitter.com",
)
TRIVIAL_DIRS = {"css", "js", "img", "images", "image", "assets", "static", "fonts", "font", "media", "wp-content", "wp-includes",
                "cdn-cgi", "favicon.ico", "api", "includes", "vendor", "dist", "build", "public", "uploads", "<uuid>", "<id>", "<n>"}
RANDOM_VAL = re.compile(r"^[A-Za-z0-9]{8,}$")
UUIDISH = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)

TOPICS = {
    "fałszywy news / sensacja": ["zamach", "postrzel", "kajdank", "aresztow", "skandal", "nagranie usunięto", "studio", "wywiad",
                                 "pilne", "breaking", "dziennikar", "prezes", "napaść", "atak", "szpital", "emisji"],
    "inwestycje / zysk": ["inwest", "zysk", "akcj", "kapitał", "platform", "zarabia", "dochód", "giełd", "kryptowalut", "bitcoin",
                          "portfel", "depozyt", "1150", "summit", "dywidend"],
    "zdrowie / suplement": ["prostat", "cukrzyc", "odchudz", "sylwetk", "grzybic", "stawy", "zdrowi", "lekarz", "kapsuł", "objaw",
                            "naukowo", "kurac", "metabolizm", "ból", "suplement", "schud", "kilogram", "kg ", "tłuszcz", "waga",
                            "dietetyk", "urolog", "leczeni", "kręgosłup", "kregow", "nerw", "dysk", "zwyrodn"],
    "hazard / kasyno": ["kasyno", "casino", "bonus", "slot", "bonanza", "spin", "wygran", "depozyt", "graczy"],
    "sklep / wyprzedaż": ["koszyk", "dostaw", "wyprzedaż", "rabat", "zamów", "products", "sztuk", "przesyłk"],
}


class ImageHash(BaseModel):
    file: str
    phash: str  # 64 bity, hex
    role: str  # zrzut | kreacja | zasob | klatka


class Material(BaseModel):
    id: str
    label: str
    source: str  # folder | upload | url | tekst
    files: list[str] = Field(default_factory=list)
    titles: list[str] = Field(default_factory=list)
    text: str = ""
    ocr_text: str = ""
    keywords: list[str] = Field(default_factory=list)
    topics: dict[str, int] = Field(default_factory=dict)
    persons: list[str] = Field(default_factory=list)
    person_counts: dict[str, int] = Field(default_factory=dict)
    products: list[str] = Field(default_factory=list)
    urls: list[str] = Field(default_factory=list)
    landing_domains: list[str] = Field(default_factory=list)
    third_party_hosts: list[str] = Field(default_factory=list)
    redirects: list[str] = Field(default_factory=list)
    path_templates: list[str] = Field(default_factory=list)
    path_prefixes: list[str] = Field(default_factory=list)  # charakterystyczny początek ścieżki (zestaw/szablon strony)
    url_schemes: list[str] = Field(default_factory=list)  # odcisk schematu parametrów (np. zestaw TDS)
    ad_ids: list[str] = Field(default_factory=list)
    pixel_ids: list[str] = Field(default_factory=list)
    tracker_ids: list[str] = Field(default_factory=list)
    ad_accounts: list[str] = Field(default_factory=list)
    contacts: list[str] = Field(default_factory=list)
    advertisers: list[str] = Field(default_factory=list)  # nazwa strony-reklamodawcy z kreacji (np. zrzut z „Sponsorowane”)
    dom_tokens: list[str] = Field(default_factory=list)
    images: list[ImageHash] = Field(default_factory=list)
    pages: int = 0
    cloaking: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    # kiedy materiał zaobserwowano: [{"date": ISO, "source": opis}]; czas zebrania, nie czas emisji reklamy
    observed: list[dict] = Field(default_factory=list)


# --- osoby ----------------------------------------------------------------------------------------------------------

def load_persons(path: Path | None = None) -> list[tuple[str, list[str]]]:
    p = path or ROOT / "config" / "osoby.txt"
    out = []
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [x.strip() for x in line.split("|") if x.strip()]
        out.append((parts[0], parts))
    return out


def _token_re(tok: str) -> str:
    """Wzorzec jednego słowa z polską odmianą. Nazwiska przymiotnikowe (-ski/-cki/-ska/-cka) mają osobne końcówki męskie i żeńskie,
    żeby "Lewandowski" nie łapał "Lewandowska"."""
    t = tok.lower()
    # przymiotnikowe: spółgłoska przed -sk/-ck (Lewandow-ska, Kowal-ski); „Brzo-ska” ma samogłoskę i odmienia się jak rzeczownik
    m = re.match(r"^(.*[^aeiouyąęó](?:sk|ck|dzk))(i|a)$", t)
    if m:
        ends = "i|iego|iemu|im|ich" if m.group(2) == "i" else "a|iej|ą"
        return re.escape(m.group(1)) + f"(?:{ends})"
    if t[-1] in "aeiouyąę" and len(t) > 3:
        return re.escape(t[:-1]) + r"\w{0,4}"
    return re.escape(t) + r"\w{0,4}"


def find_persons(text: str, persons: list[tuple[str, list[str]]]) -> dict[str, int]:
    """Liczba wzmianek osób z bazy: pełne imię i nazwisko (z odmianą) albo jednoznaczny alias. Zwraca {osoba: liczba}."""
    t = text.lower()
    found: dict[str, int] = {}
    for name, variants in persons:
        n = 0
        for v in variants:  # najwięcej trafień spośród wariantów (pełne nazwisko i alias nie sumują się podwójnie)
            pat = r"\s+".join(_token_re(x) for x in v.split())
            n = max(n, len(re.findall(r"(?<!\w)" + pat + r"(?!\w)", t)))
        if n:
            found[name] = n
    return dict(sorted(found.items(), key=lambda x: -x[1]))


# --- tekst ----------------------------------------------------------------------------------------------------------

STOP = set(["a", "aby", "ale", "albo", "ani", "aż", "bardzo", "bez", "bo", "być", "był", "była", "było", "były", "będzie", "cię", "co", "czy", "dla", "do", "dziś", "gdy", "gdzie", "go", "i", "ich", "im", "in", "jak", "jako", "je", "jego", "jej", "jest", "jeszcze", "jeśli", "już", "każdy", "kiedy", "kto", "która", "które", "który", "których", "ma", "mają", "mi", "mnie", "może", "można", "mu", "na", "nad", "nam", "nas", "nawet", "nie", "nich", "nim", "no", "o", "od", "on", "ona", "one", "oni", "oraz", "po", "pod", "przez", "przy", "się", "sobie", "są", "ta", "tak", "także", "tam", "te", "tego", "tej", "ten", "też", "to", "tu", "tylko", "tym", "u", "w", "we", "więc", "z", "za", "ze", "że", "żeby", "the", "and", "of", "to", "in", "for", "is", "on", "you", "your", "with", "this", "that", "are", "be", "at", "by", "or", "from", "as", "an", "it", "was", "we", "can", "więcej", "oraz", "także", "który", "która", "które", "teraz", "dziś", "tego", "temu", "ich"])


def keywords(text: str, k: int = 15) -> list[str]:
    words = [w for w in re.findall(r"[a-ząćęłńóśźż]{4,}", text.lower()) if w not in STOP]
    return [w for w, _ in Counter(words).most_common(k)]


_PL = str.maketrans("ąćęłńóśźż", "acelnoszz")


def topics(text: str) -> dict[str, int]:
    """Słownikowa tematyka; polskie znaki ujednolicone, bo OCR bez pakietu `pol` je gubi."""
    t = text.lower().translate(_PL)
    out = {}
    for name, keys in TOPICS.items():
        n = sum(t.count(k.translate(_PL)) for k in keys)
        if n:
            out[name] = n
    return dict(sorted(out.items(), key=lambda x: -x[1]))


SPONSORED = re.compile(r"(?:^|[\s|•·>])((?:[A-ZĄĆĘŁŃÓŚŹŻ][\w'&.-]*\s){0,3}[A-ZĄĆĘŁŃÓŚŹŻ][\w'&.-]+)\s+(?:Sponsorowane|Sponsored)")


def advertisers(ocr_text: str) -> list[str]:
    """Nazwa reklamodawcy ze zrzutu reklamy z Facebooka/Instagrama: słowa z wielkiej litery tuż przed „Sponsorowane”."""
    out = []
    for m in SPONSORED.finditer(ocr_text or ""):
        name = m.group(1).strip(" .-")
        if 3 <= len(name) <= 50 and name.lower() not in ("reklama", "facebook", "instagram"):
            out.append(name)
    out = list(dict.fromkeys(out))
    # „V Sustain Studio” i „Sustain Studio” to ten sam odczyt z przyklejonym znakiem z ikony: zostaw krótszy
    return [n for n in out if not any(o != n and n.endswith(" " + o) for o in out)]


# --- URL ------------------------------------------------------------------------------------------------------------

def _val_shape(v: str) -> str:
    if UUIDISH.match(v) or re.match(r"^[0-9a-f]{6,}-", v):
        return "uuid"
    if v.isdigit():
        return f"num{len(v)}"
    if RANDOM_VAL.match(v) and re.search(r"[A-Z]", v) and re.search(r"[a-z]", v):
        return f"rnd{len(v)}"
    return "txt"


def is_common_host(host: str) -> bool:
    host = (host or "").lower()
    return any(host == c or host.endswith("." + c) for c in COMMON_HOSTS)


def url_features(url: str) -> dict:
    """Cechy adresu bez łączenia się z nim: domena, szablon ścieżki, schemat parametrów, identyfikatory reklam i pikseli."""
    u = urlsplit(url.strip())
    host = (u.hostname or "").lower()
    if "." not in host:
        host = ""
    q = parse_qsl(u.query, keep_blank_values=True)
    out = {"host": host, "domain": (registered_domain(host) or host) if host else "", "ad_ids": [], "pixel_ids": [], "accounts": [],
           "trackers": []}
    tmpl = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "<UUID>", u.path or "/", flags=re.IGNORECASE)
    tmpl = re.sub(r"\d{6,}", "<N>", tmpl)
    tmpl = re.sub(r"/[A-Za-z0-9]{6,}(?=/|$)", lambda m: "/<ID>" if re.search(r"\d", m.group(0)) else m.group(0), tmpl)
    out["path_template"] = tmpl
    segs = [s for s in tmpl.split("/") if s]
    out["prefix"] = ""
    if len(segs) >= 2 and segs[0].lower() not in TRIVIAL_DIRS:
        out["prefix"] = "/" + "/".join(segs[:3 if len(segs) > 3 else 2])
        if out["prefix"].count("<") >= 2:  # same identyfikatory, brak treści
            out["prefix"] = ""
    keys = sorted({k for k, _ in q})
    shapes = sorted({f"{k}:{_val_shape(v)}" for k, v in q
                     if k not in ("fbclid", "gclid", "gad_source", "gad_campaignid", "wbraid", "gbraid", "access_token")
                     and not re.fullmatch(r"[0-9a-f]{16,}", k)})  # losowe klucze-hashe są inne na każdej stronie
    # Schemat liczymy tylko, gdy niesie informację (losowe wartości o stałej długości albo nietypowe klucze).
    informative = [s for s in shapes if not s.endswith(":txt")] or [s for s in shapes if s.split(":")[0] not in ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term")]
    out["scheme"] = "&".join(shapes) if len(informative) >= 2 else ""
    for k, v in q:
        kl = k.lower()
        if kl in ("ad_id", "adid", "fb_ad_id") and v.isdigit():
            out["ad_ids"].append(v)
        if kl in ("pxl", "pixel", "pixel_id", "fbpixel", "pixel_fb") and re.fullmatch(r"\d{10,}", v):
            out["pixel_ids"].append(v)
        if kl in ("acc", "account", "buyer") and v:
            out["accounts"].append(v.split("_")[0])
        if kl == "id" and "facebook.com" in host and "/tr" in u.path and v.isdigit():
            out["pixel_ids"].append(v)
        if kl == "id" and "facebook.com" in host and u.path.startswith("/ads/library") and v.isdigit():
            out["ad_ids"].append(v)
    m = re.search(r"/pagead/(?:1p-)?conversion/(\d{6,})", u.path)
    if m:
        out["trackers"].append(f"google-ads:{m.group(1)}")
    for k, v in q:
        if k == "id" and re.fullmatch(r"(G|GTM|AW)-[A-Z0-9]{5,}", v):
            out["trackers"].append(v)
    out["keys"] = keys
    return out


# --- HTML -----------------------------------------------------------------------------------------------------------

def parse_html(path: Path) -> dict:
    from bs4 import BeautifulSoup

    raw = path.read_text(encoding="utf-8", errors="replace")
    saved = re.search(r"saved from url=\(\d+\)(\S+)", raw)
    soup = BeautifulSoup(raw, "lxml")
    title = (soup.title.get_text(" ", strip=True) if soup.title else "") or ""
    pixels = set(re.findall(r"fbq\(\s*['\"]init['\"]\s*,\s*['\"](\d{10,})", raw))
    trackers = set(re.findall(r"\b((?:G|GTM|AW)-[A-Z0-9]{6,})\b", raw))
    links = [a.get("href") for a in soup.find_all("a") if a.get("href", "").startswith("http")]
    dom = Counter()
    for el in soup.find_all(True)[:3000]:
        cls = el.get("class") or []
        dom[el.name] += 1
        for c in cls[:3]:
            if not re.search(r"\d{3,}", c):
                dom[f"{el.name}.{c}"] += 1
    for t in soup(["script", "style", "noscript", "svg", "template"]):
        t.decompose()
    text = " ".join(soup.get_text(" ").split())
    og = {m.get("property"): m.get("content") for m in soup.find_all("meta") if m.get("property", "").startswith("og:")}
    return {"title": title, "text": text, "saved_from": saved.group(1) if saved else None, "pixels": pixels, "trackers": trackers,
            "links": links, "dom": [k for k, _ in dom.most_common(400)], "og": og}


# --- HAR ------------------------------------------------------------------------------------------------------------

def parse_har(path: Path) -> dict:
    j = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    ents = j.get("log", {}).get("entries", [])
    urls = [e["request"]["url"] for e in ents if e.get("request", {}).get("url", "").startswith("http")]
    docs = [e["request"]["url"] for e in ents if "html" in (e.get("response", {}).get("content", {}).get("mimeType") or "")]
    redirects = []
    for e in ents:
        st = e.get("response", {}).get("status", 0)
        loc = e.get("response", {}).get("redirectURL") or ""
        if 300 <= st < 400 and st != 304 and loc:
            src_h, dst_h = urlsplit(e["request"]["url"]).hostname, urlsplit(loc).hostname or urlsplit(e["request"]["url"]).hostname
            if not (is_common_host(src_h) and is_common_host(dst_h)):
                redirects.append(f"{src_h} → {dst_h} ({st})")
    times = sorted(e["startedDateTime"] for e in ents if isinstance(e.get("startedDateTime"), str) and e["startedDateTime"][:2] == "20")
    return {"urls": urls, "docs": docs, "redirects": redirects, "first": times[0] if times else None,
            "last": times[-1] if times else None}


FILE_DATE = re.compile(r"(20\d\d)-(\d\d)-(\d\d)(?:[ _T](\d\d)[.:]?(\d\d)[.:]?(\d\d))?")


def date_from_name(name: str) -> str | None:
    """Data z nazwy pliku tylko w jednoznacznym formacie RRRR-MM-DD (np. „Zrzut ekranu 2026-10-09 082411.png”).
    Formaty typu 08-12-2026 (iOS) pomijamy, bo nie wiadomo, czy to dzień, czy miesiąc."""
    m = FILE_DATE.search(name)
    if not m:
        return None
    y, mo, d, hh, mi, ss = m.groups()
    if not (1 <= int(mo) <= 12 and 1 <= int(d) <= 31):
        return None
    if not hh:
        return f"{y}-{mo}-{d}"
    # zrzuty i nagrania mają czas lokalny urządzenia; zakładamy czas polski i przeliczamy na UTC (jak znaczniki HAR)
    from datetime import UTC, datetime
    from zoneinfo import ZoneInfo

    try:
        local = datetime(int(y), int(mo), int(d), int(hh), int(mi), int(ss), tzinfo=ZoneInfo("Europe/Warsaw"))
    except ValueError:
        return f"{y}-{mo}-{d}"
    return local.astimezone(UTC).isoformat()[:19]


def parse_urlscan(path: Path) -> dict:
    """Plik `urlscan.json` z kolektora `fejki.sources.urlscan`: metadane z wyszukiwarki, opcjonalnie pełny wynik skanu."""
    j = json.loads(path.read_text(encoding="utf-8"))
    hit = j.get("search_hit") or {}
    page, task = hit.get("page") or {}, hit.get("task") or {}
    full = j.get("result") or {}
    urls = [u for u in (page.get("url"), task.get("url")) if u]
    urls += (full.get("lists") or {}).get("urls", [])[:300]
    redirects = []
    for q in (full.get("data") or {}).get("requests", [])[:500]:
        req = q.get("request") or {}
        u = (req.get("request") or {}).get("url")
        if u:
            urls.append(u)
        rr = req.get("redirectResponse") or {}
        if rr.get("url") and u and 300 <= int(rr.get("status") or 0) < 400:
            a, b = urlsplit(rr["url"]).hostname, urlsplit(u).hostname
            if a != b and not (is_common_host(a) and is_common_host(b)):
                redirects.append(f"{a} → {b} ({rr.get('status')})")
    notes = ["materiał ze skanu urlscan.io (bierne: strona zeskanowana przez kogoś innego)"]
    if page.get("domainAgeDays") is not None:
        notes.append(f"wiek domeny w chwili skanu: {page['domainAgeDays']} dni (urlscan)")
    if page.get("tlsAgeDays") is not None:
        notes.append(f"wiek certyfikatu w chwili skanu: {page['tlsAgeDays']} dni")
    if page.get("asnname"):
        notes.append(f"hosting: {page.get('asn', '')} {page['asnname']}")
    if page.get("redirected"):
        notes.append(f"przekierowanie przy wejściu: {page['redirected']}")
    if j.get("label"):
        notes.append(f"etykieta pivotu: {j['label']} ({j.get('query', '')})")
    return {"urls": urls, "title": page.get("title"), "landing": page.get("url"), "time": task.get("time"),
            "redirects": redirects, "notes": notes}


# --- obrazy ---------------------------------------------------------------------------------------------------------

def phash(img) -> str:
    """Perceptual hash (DCT 32x32 → 8x8), bez zależności zewnętrznych."""
    from scipy.fft import dctn

    a = np.asarray(img.convert("L").resize((32, 32)), dtype=float)
    d = dctn(a, norm="ortho")[:8, :8]
    med = np.median(d.flatten()[1:])
    bits = (d > med).flatten()
    return f"{int(''.join('1' if b else '0' for b in bits), 2):016x}"


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def _ocr(img) -> str:
    try:
        import pytesseract

        langs = pytesseract.get_languages(config="")
        lang = "pol" if "pol" in langs else "eng"
        g = img.convert("L")
        if g.width < 1200:
            g = g.resize((g.width * 2, g.height * 2))
        return " ".join(pytesseract.image_to_string(g, lang=lang).split())
    except Exception:
        return ""


def video_frames(path: Path, n: int = 4) -> list:
    """Kilka klatek z filmu przez ffmpeg (jeśli jest). Zwraca listę obrazów PIL."""
    from PIL import Image

    if not shutil.which("ffmpeg"):
        return []
    tmp = Path(tempfile.mkdtemp(prefix="fejki_vid_"))
    try:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(path), "-vf", "fps=1/3", "-frames:v", str(n), str(tmp / "f%02d.png")],
                       check=False, timeout=120)
        return [Image.open(p).copy() for p in sorted(tmp.glob("f*.png"))]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --- składanie materiału -----------------------------------------------------------------------------------------

def _uniq(xs):
    return list(dict.fromkeys(x for x in xs if x))


def is_har(p: Path) -> bool:
    """HAR po rozszerzeniu, także plik nazwany samym „.har” (dla Pythona to nazwa bez rozszerzenia; jest taki w zbiorze)."""
    return p.suffix.lower() == ".har" or p.name.lower() == ".har"


def _is_asset(p: Path) -> bool:
    return any(part.endswith("_files") or part in ("assets", "resources") for part in p.parts)


def build_material(mid: str, label: str, source: str, files: list[Path] | None = None, urls: list[str] | None = None,
                   text: str = "", ocr: bool = True, persons: list | None = None, base: Path | None = None) -> Material:
    from PIL import Image

    files = files or []
    m = Material(id=mid, label=label, source=source, files=[str(f.relative_to(base) if base and f.is_relative_to(base) else f.name) for f in files])
    persons = persons if persons is not None else load_persons()
    all_urls: list[str] = list(urls or [])
    texts = [text] if text else []
    dom: Counter = Counter()
    pixel, track = set(), set()
    htmls = [f for f in files if f.suffix.lower() in HTML_EXT and not _is_asset(f)]
    hars = [f for f in files if is_har(f)]
    shots = [f for f in files if f.suffix.lower() in IMG_EXT and not _is_asset(f)]
    assets = [f for f in files if f.suffix.lower() in IMG_EXT and _is_asset(f)]
    vids = [f for f in files if f.suffix.lower() in VID_EXT]
    infos = [f for f in files if f.name.endswith(".info.json")]
    scans = [f for f in files if f.name == "urlscan.json"]
    scan_landing: list[str] = []
    for f in scans:
        try:
            d = parse_urlscan(f)
        except Exception as e:
            m.notes.append(f"urlscan.json nieczytelny ({type(e).__name__})")
            continue
        all_urls += d["urls"]
        m.redirects += d["redirects"]
        m.notes += d["notes"]
        if d["title"]:
            m.titles.append(d["title"])
            texts.append(d["title"])
        if d["landing"]:
            scan_landing.append(d["landing"])
        if d["time"]:
            m.observed.append({"date": d["time"][:19], "source": "czas skanu urlscan.io"})
    page_titles = []
    for h in htmls:
        try:
            d = parse_html(h)
        except Exception as e:
            m.notes.append(f"HTML nieczytelny: {h.name} ({type(e).__name__})")
            continue
        m.pages += 1
        if d["title"]:
            m.titles.append(d["title"])
            page_titles.append((d["title"], d["saved_from"]))
        texts.append(d["text"])
        if d["saved_from"] and d["saved_from"].startswith("http"):
            all_urls.append(d["saved_from"])
        all_urls += d["links"][:50]
        pixel |= d["pixels"]
        track |= d["trackers"]
        dom.update(d["dom"])
        if d["og"].get("og:site_name"):
            m.notes.append(f"og:site_name = {d['og']['og:site_name']}")
    for h in hars:
        try:
            d = parse_har(h)
        except Exception as e:
            m.notes.append(f"HAR nieczytelny: {h.name} ({type(e).__name__})")
            continue
        all_urls += d["urls"]
        m.redirects += d["redirects"]
        if d["first"]:
            m.observed.append({"date": d["first"][:19], "source": f"log HAR {h.name}"})
    for f in shots + vids:  # daty z nazw zrzutów i nagrań (tylko format RRRR-MM-DD)
        dt = date_from_name(f.name)
        if dt:
            m.observed.append({"date": dt, "source": f"nazwa pliku {f.name}, czas PL → UTC"})
    for f in infos:
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
            if j.get("webpage_url"):
                all_urls.append(j["webpage_url"])
            for k in ("title", "description"):
                if j.get(k):
                    texts.append(str(j[k]))
            if j.get("timestamp"):
                from datetime import UTC, datetime

                m.observed.append({"date": datetime.fromtimestamp(int(j["timestamp"]), UTC).isoformat()[:19], "source": f.name})
            mm = re.search(r"ads/library/\?id=(\d+)", j.get("webpage_url") or "")
            if mm:
                m.ad_ids.append(mm.group(1))
                m.notes.append("materiał pochodzi z Meta Ad Library")
        except Exception:
            pass
    # obrazy: zrzuty (OCR + pHash), zasoby stron (pHash), klatki wideo (OCR + pHash)
    ocr_parts = []
    for f in shots[:16]:
        try:
            img = Image.open(f)
            m.images.append(ImageHash(file=f.name, phash=phash(img), role="kreacja" if "reklama" in f.name.lower() else "zrzut"))
            if ocr:
                ocr_parts.append(_ocr(img))
        except Exception:
            m.notes.append(f"obraz nieczytelny: {f.name}")
    for f in assets:
        if len([i for i in m.images if i.role == "zasob"]) >= 60:
            break
        try:
            img = Image.open(f)
            if img.width >= 120 and img.height >= 120:
                m.images.append(ImageHash(file=f.name, phash=phash(img), role="zasob"))
        except Exception:
            pass
    for f in vids[:2]:
        for k, img in enumerate(video_frames(f)):
            m.images.append(ImageHash(file=f"{f.name}#{k}", phash=phash(img), role="klatka"))
            if ocr:
                ocr_parts.append(_ocr(img))
    m.ocr_text = " ".join(x for x in ocr_parts if x)[:20000]
    m.advertisers = advertisers(m.ocr_text)
    # zrzut karty reklamy z Meta Ad Library: „Identyfikator biblioteki: 2186…” / „Library ID: …”
    lib_ids = re.findall(r"(?:Identyfikator biblioteki|Library ID)\s*:?\s*(\d{12,20})", m.ocr_text, flags=re.IGNORECASE)
    if lib_ids:
        m.ad_ids += lib_ids
        m.notes.append("zrzut karty reklamy z Meta Ad Library (identyfikator odczytany przez OCR)")
    # URL-e
    landing, third, tmpls, schemes, prefixes = [], [], [], [], []
    for u in _uniq(all_urls):
        try:
            f = url_features(u)
        except Exception:
            continue
        m.ad_ids += f["ad_ids"]
        pixel.update(f["pixel_ids"])
        track.update(f["trackers"])
        m.ad_accounts += f["accounts"]
        if not f["host"]:
            continue
        if is_common_host(f["host"]):
            continue
        third.append(f["domain"])
        if f["scheme"]:
            schemes.append(f["scheme"])
        if f["path_template"] not in ("/", ""):
            tmpls.append(f["path_template"])
        if f["prefix"]:
            prefixes.append(f["prefix"])
    m.urls = _uniq(u for u in all_urls if urlsplit(u).hostname and not is_common_host(urlsplit(u).hostname))[:200]
    # domeny docelowe: z adresów zapisu stron i pierwszych dokumentów (strona, na którą trafia ofiara)
    for u in [p[1] for p in page_titles if p[1]] + (urls or []) + scan_landing:
        if u and u.startswith("http"):
            landing.append(url_features(u)["domain"])
    for h in hars:
        dom_name = h.stem.lower()
        if "." in dom_name and registered_domain(dom_name):
            landing.append(registered_domain(dom_name))
    if not landing and third:
        landing = [Counter(third).most_common(1)[0][0]]
    m.landing_domains = _uniq(landing)
    m.third_party_hosts = _uniq(d for d in third if d not in m.landing_domains)
    m.path_templates = _uniq(tmpls)[:30]
    m.path_prefixes = [p for p, _ in Counter(prefixes).most_common(15)]
    m.url_schemes = _uniq(schemes)[:20]
    m.pixel_ids = sorted(pixel)
    m.tracker_ids = sorted(track)
    m.ad_ids = _uniq(m.ad_ids)
    m.ad_accounts = _uniq(m.ad_accounts)
    m.redirects = _uniq(m.redirects)[:30]
    m.dom_tokens = [k for k, _ in dom.most_common(400)]
    full = " ".join(texts + [m.ocr_text])
    m.text = full[:60000]
    m.titles = _uniq(m.titles)
    m.keywords = keywords(full)
    # tematyka z tytułów i początku treści (komentarze na dole stron to szum)
    m.topics = topics((" ".join(m.titles) + " ") * 5 + " ".join(t[:6000] for t in texts) + " " + m.ocr_text[:3000])
    m.person_counts = find_persons(" ".join(m.titles) + " " + full, persons)
    m.persons = list(m.person_counts)
    m.contacts = _uniq(f"{a.kind}:{a.value}" for a in extract_artifacts(full) if a.kind in ("phone", "telegram", "whatsapp"))[:20]
    # produkt: krótki tytuł strony, który nie jest nagłówkiem newsa ani nazwą portalu
    for t in m.titles:
        tt = re.sub(r"^(App Store|Google Play)\s*[–-]\s*", "", t).strip()
        if 1 <= len(tt.split()) <= 4 and not re.search(r"(portal|gazeta|tvn|onet|wp\.pl|summit|\.org|\.com)", tt, re.IGNORECASE):
            m.products.append(tt)
    m.products = _uniq(m.products)
    # cloaking: ta sama domena serwuje strony o różnym charakterze (przykrywka + wabik)
    doms = [url_features(p[1])["domain"] for p in page_titles if p[1] and p[1].startswith("http")]
    if len(page_titles) >= 2 and len(set(doms)) == 1 and len({p[0] for p in page_titles}) >= 2:
        m.cloaking.append(f"domena {doms[0]} pokazuje {len({p[0] for p in page_titles})} różne strony: " + " | ".join(p[0][:50] for p in page_titles))
    if not htmls:
        m.missing.append("brak zapisanej strony (HTML)")
    if not hars:
        m.missing.append("brak logu ruchu (HAR)")
    if not shots and not vids:
        m.missing.append("brak zrzutu ekranu / nagrania")
    if not full.strip():
        m.missing.append("brak tekstu")
    return m


def material_from_folder(folder: Path, ocr: bool = True, persons: list | None = None) -> Material:
    files = [p for p in folder.rglob("*") if p.is_file()]
    return build_material(mid=folder.name, label=f"przypadek {folder.name}", source="folder", files=files, ocr=ocr, persons=persons, base=folder)


def material_from_inputs(label: str, files: list[Path] | None = None, url: str = "", text: str = "", ocr: bool = True) -> Material:
    mid = "nowy-" + hashlib.sha1((label + url + text + "".join(str(f) for f in files or [])).encode()).hexdigest()[:8]
    src = "upload" if files else "url" if url else "tekst"
    urls = re.findall(r"https?://[^\s<>\"']+", url) if url else []
    return build_material(mid=mid, label=label, source=src, files=files or [], urls=urls, text=text, ocr=ocr)
