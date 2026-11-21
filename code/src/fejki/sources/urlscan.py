"""urlscan.io: wyszukiwanie ISTNIEJĄCYCH publicznych skanów i zapis ich jako folderów przypadków.

Zasady:
- tylko wyszukiwanie i pobieranie gotowych skanów; NIGDY nie zlecamy nowych skanów (`/scan/`), bo wtedy urlscan
  odwiedziłby stronę oszustów w naszym imieniu i opublikował wynik;
- bez klucza: wyszukiwarka (metadane strony: adres z parametrami, tytuł, wiek domeny i certyfikatu, ASN) i zrzut ekranu;
- z kluczem (`URLSCAN_API_KEY` w `.env`, darmowe konto): także pełny wynik (lista żądań ~ HAR, przekierowania) i DOM;
- dane z urlscan to dane stron trzecich: zostają lokalnie (`data/urlscan/`, w `.gitignore`), w metodyce podajemy źródło.

Folder przypadku (zgodny z `fejki.demo.material.build_material`):
    <uuid>/urlscan.json    metadane z wyszukiwarki (+ pełny wynik, jeśli jest klucz)
    <uuid>/screenshot.png  zrzut ekranu z urlscan
    <uuid>/dom.html        DOM strony z komentarzem `saved from url=` (tylko z kluczem)
"""
from __future__ import annotations

import csv
import json
import os
import time
from pathlib import Path

import httpx
import yaml

API = "https://urlscan.io/api/v1"
UA = "fejki-research/0.1"


class UrlscanError(RuntimeError):
    pass


class Client:
    def __init__(self, api_key: str | None = None, delay: float = 2.0, http: httpx.Client | None = None):
        self.api_key = api_key if api_key is not None else os.environ.get("URLSCAN_API_KEY") or None
        self.delay = delay
        headers = {"User-Agent": UA}
        if self.api_key:
            headers["API-Key"] = self.api_key
        self.http = http or httpx.Client(timeout=60, headers=headers, follow_redirects=True)
        self._last = 0.0

    def _get(self, url: str, params: dict | None = None, tries: int = 4) -> httpx.Response:
        for k in range(tries):
            wait = self.delay - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            r = self.http.get(url, params=params)
            self._last = time.monotonic()
            if r.status_code == 429:  # limit zapytań: czekamy, ile każe serwer
                time.sleep(min(120, float(r.headers.get("Retry-After", 10 * (k + 1)))))
                continue
            return r
        raise UrlscanError(f"limit zapytań urlscan nie minął: {url}")

    def search(self, query: str, size: int = 100, search_after: str | None = None) -> dict:
        params = {"q": query, "size": size}
        if search_after:
            params["search_after"] = search_after
        r = self._get(f"{API}/search/", params)
        if r.status_code != 200:
            raise UrlscanError(f"wyszukiwanie {r.status_code}: {r.text[:200]}")
        return r.json()

    def iter_search(self, query: str, limit: int = 100):
        """Kolejne trafienia (od najnowszych), stronicowanie przez `search_after`."""
        seen, after = 0, None
        while seen < limit:
            j = self.search(query, size=min(100, limit - seen), search_after=after)
            res = j.get("results", [])
            for hit in res:
                yield hit
                seen += 1
                if seen >= limit:
                    return
            if not res or not j.get("has_more"):
                return
            after = ",".join(str(x) for x in res[-1].get("sort", []))

    def result(self, uuid: str) -> dict | None:
        if not self.api_key:
            return None
        r = self._get(f"{API}/result/{uuid}/")
        return r.json() if r.status_code == 200 else None

    def dom(self, uuid: str) -> str | None:
        if not self.api_key:
            return None
        r = self._get(f"https://urlscan.io/dom/{uuid}/")
        return r.text if r.status_code == 200 and not r.text.lstrip().startswith("{") else None

    def screenshot(self, uuid: str) -> bytes | None:
        r = self._get(f"https://urlscan.io/screenshots/{uuid}.png")
        return r.content if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/") else None


def save_case(client: Client, hit: dict, out_dir: Path, label: str, query: str, screenshot: bool = True) -> Path:
    uuid = hit.get("_id") or hit["task"]["uuid"]
    d = out_dir / uuid
    d.mkdir(parents=True, exist_ok=True)
    meta = {"source": "urlscan.io", "label": label, "query": query, "search_hit": hit}
    full = client.result(uuid)
    if full:
        meta["result"] = full
    (d / "urlscan.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    if screenshot and not (d / "screenshot.png").exists():
        img = client.screenshot(uuid)
        if img:
            (d / "screenshot.png").write_bytes(img)
    dom = client.dom(uuid)
    if dom:
        url = hit.get("page", {}).get("url", "")
        (d / "dom.html").write_text(f"<!-- saved from url=({len(url):04d}){url} -->\n{dom}", encoding="utf-8")
    return d


def load_pivots(path: Path) -> list[dict]:
    cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return [p for p in cfg.get("pivots", []) if p.get("query")]


def collect(client: Client, pivots: list[dict], out_dir: Path, max_per_domain: int = 2, screenshot: bool = True,
            log=print) -> list[dict]:
    """Zbiera skany dla listy pivotów i dopisuje etykiety do `labels.csv`.

    Etykieta = nazwa pivotu (np. wspólny zestaw strony). To etykieta słaba: ten sam zestaw może służyć wielu operatorom.
    `max_per_domain` ogranicza powtórzenia tej samej domeny (urlscan często ma wiele skanów jednej strony).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    labels_path = out_dir / "labels.csv"
    rows, done = [], set()
    if labels_path.exists():
        with labels_path.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                rows.append(r)
                done.add(r["case_id"])
    per_domain: dict[str, int] = {}
    for r in rows:
        per_domain[r["domain"]] = per_domain.get(r["domain"], 0) + 1
    for p in pivots:
        label, query, limit = p["label"], p["query"], int(p.get("limit", 50))
        n_new = 0
        try:
            for hit in client.iter_search(query, limit=limit * 3):
                uuid = hit.get("_id")
                dom = (hit.get("page") or {}).get("apexDomain") or (hit.get("page") or {}).get("domain") or ""
                if not uuid or uuid in done or per_domain.get(dom, 0) >= max_per_domain:
                    continue
                save_case(client, hit, out_dir, label, query, screenshot)
                done.add(uuid)
                per_domain[dom] = per_domain.get(dom, 0) + 1
                rows.append({"case_id": uuid, "label": label, "kind": p.get("kind", "pozytyw"), "query": query, "domain": dom,
                             "page_url": (hit.get("page") or {}).get("url", ""), "time": hit.get("task", {}).get("time", ""),
                             "source": f"https://urlscan.io/result/{uuid}/"})
                n_new += 1
                if n_new >= limit:
                    break
        except UrlscanError as e:
            log(f"{label}: błąd {e}")
        log(f"{label}: +{n_new} przypadków ({query})")
        with labels_path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["case_id", "label", "kind", "query", "domain", "page_url", "time", "source"])
            w.writeheader()
            w.writerows(rows)
    return rows
