"""Pobranie strony spod adresu URL do tej samej postaci, co materiały NASK: plik HTML i HAR (adresy zasobów, łańcuch przekierowań,
obrazy w base64). Dzięki temu dalsza ścieżka (`features.load_case`) jest identyczna jak dla wgranych plików.

Bez przeglądarki i bez JavaScriptu (requests + BeautifulSoup): widzimy to, co serwer oddaje botowi. Strony oszustów często ukrywają
treść przed botami (cloaking) albo już nie działają, więc każda porażka kończy się łagodnie: zostaje sama domena i ostrzeżenie.
Ochrona: tylko http/https, bez adresów prywatnych i lokalnych (SSRF), limit czasu, rozmiaru i liczby zasobów.
"""
from __future__ import annotations

import base64
import ipaddress
import json
import socket
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
TIMEOUT = 10
MAX_PAGE = 5_000_000
MAX_IMG = 2_000_000
MAX_RES = 40


class FetchError(Exception):
    pass


def _safe(url: str) -> None:
    p = urlsplit(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise FetchError(f"nieobsługiwany adres: {url}")
    try:
        infos = socket.getaddrinfo(p.hostname, None)
    except socket.gaierror as e:
        raise FetchError(f"domena nie istnieje albo nie odpowiada DNS ({p.hostname})") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise FetchError(f"adres wskazuje na sieć prywatną ({ip}), pomijam")


def _get(sess, url: str, limit: int):
    """GET z ręcznym śledzeniem przekierowań (każdy krok sprawdzany pod SSRF). Zwraca (odpowiedź, bajty, łańcuch adresów)."""
    chain = []
    for _ in range(8):
        _safe(url)
        r = sess.get(url, timeout=TIMEOUT, allow_redirects=False, stream=True)
        chain.append((url, r))
        if r.is_redirect and r.headers.get("location"):
            url = urljoin(url, r.headers["location"])
            r.close()
            continue
        data = b""
        for chunk in r.iter_content(65536):
            data += chunk
            if len(data) > limit:
                break
        return r, data[:limit], chain
    raise FetchError("za dużo przekierowań")


def _entry(url: str, r, mime: str = "", data: bytes | None = None) -> dict:
    content = {"size": len(data or b""), "mimeType": mime}
    if data is not None and mime.startswith("image/"):
        content.update(text=base64.b64encode(data).decode(), encoding="base64")
    return {"startedDateTime": datetime.now(timezone.utc).isoformat(), "request": {"method": "GET", "url": url},
            "response": {"status": getattr(r, "status_code", 0), "redirectURL": r.headers.get("location", "") if r is not None else "",
                         "content": content}}


def fetch_to_folder(url: str, dest: Path, images: bool = True) -> dict:
    """Zapisuje `strona.html` i `strona.har` do `dest`. Zwraca informacje: adres końcowy, przekierowania, liczba zasobów i obrazów.
    Rzuca FetchError, gdy strony nie da się pobrać."""
    import requests
    from bs4 import BeautifulSoup

    url = url.strip() if "://" in url else "http://" + url.strip()
    sess = requests.Session()
    sess.headers.update({"User-Agent": UA, "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.5"})
    try:
        r, data, chain = _get(sess, url, MAX_PAGE)
    except requests.RequestException as e:
        raise FetchError(f"strona nie odpowiada ({type(e).__name__})") from e
    final = chain[-1][0]
    entries = [_entry(u, rr, rr.headers.get("content-type", "")) for u, rr in chain[:-1]]
    entries.append(_entry(final, r, r.headers.get("content-type", "text/html"), data))
    if r.status_code >= 400:
        raise FetchError(f"serwer zwrócił błąd {r.status_code}")
    html = data.decode(r.encoding or "utf-8", errors="ignore")
    soup = BeautifulSoup(html, "lxml")
    refs: list[str] = []
    for tag, attr in (("script", "src"), ("link", "href"), ("img", "src"), ("iframe", "src"), ("a", "href"), ("form", "action"),
                      ("source", "src")):
        for el in soup.find_all(tag):
            v = el.get(attr)
            if v and not v.startswith(("data:", "javascript:", "mailto:", "tel:", "#")):
                refs.append(urljoin(final, v))
    refs = list(dict.fromkeys(refs))
    img_urls = [urljoin(final, el["src"]) for el in soup.find_all("img") if el.get("src") and not el["src"].startswith("data:")]
    got_img = 0
    for u in refs:
        if images and u in img_urls and got_img < MAX_RES:
            try:
                ir, idata, _ = _get(sess, u, MAX_IMG)
                mime = ir.headers.get("content-type", "").split(";")[0]
                if ir.status_code < 400 and mime.startswith("image/"):
                    entries.append(_entry(u, ir, mime, idata))
                    got_img += 1
                    continue
            except (FetchError, requests.RequestException):
                pass
        entries.append({"request": {"method": "GET", "url": u}, "response": {"status": 0, "content": {"mimeType": ""}}})
    dest.mkdir(parents=True, exist_ok=True)
    # komentarz „saved from” jak w zapisie strony z przeglądarki: features.load_case czyta z niego adres strony
    (dest / "strona.html").write_text(f"<!-- saved from url=({len(final):04d}){final} -->\n" + html, encoding="utf-8")
    (dest / "strona.har").write_text(json.dumps({"log": {"version": "1.2", "creator": {"name": "embsim.fetch"}, "entries": entries}}),
                                     encoding="utf-8")
    return {"adres_końcowy": final, "przekierowania": [u for u, _ in chain[:-1]], "zasobów": len(refs), "obrazów": got_img,
            "status": r.status_code}
