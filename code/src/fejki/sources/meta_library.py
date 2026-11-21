"""Meta Ad Library API: szybkie zbieranie surowych reklam do JSONL (póki token działa).

- wyszukiwanie `ads_archive` po słowach kluczowych (kraj PL, wszystkie typy reklam, aktywne i nieaktywne),
- druga runda: wszystkie reklamy wybranych stron (`search_page_ids`, do 10 na zapytanie),
- zapis przyrostowy (każda strona wyników od razu na dysk), deduplikacja po `id`, wznawianie po przerwie,
- token tylko z `code/.env` (`META_ACCESS_TOKEN`), w nagłówku; nigdy w logach ani w plikach wynikowych.
Dane zostają lokalnie (`data/meta/`, w `.gitignore`).
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

FIELDS = ["id", "page_id", "page_name", "ad_creation_time", "ad_delivery_start_time", "ad_delivery_stop_time",
          "ad_creative_bodies", "ad_creative_link_captions", "ad_creative_link_descriptions", "ad_creative_link_titles",
          "ad_snapshot_url", "languages", "publisher_platforms", "eu_total_reach", "target_ages", "target_gender",
          "target_locations", "beneficiary_payers", "bylines"]
REMOVED = "removed because it didn't follow our Advertising Standards"


class MetaError(RuntimeError):
    pass


class Collector:
    def __init__(self, out_dir: Path, token: str | None = None, version: str = "v21.0", delay: float = 1.0, log=print):
        self.token = token or os.environ.get("META_ACCESS_TOKEN")
        if not self.token:
            raise MetaError("brak META_ACCESS_TOKEN w code/.env")
        self.url = f"https://graph.facebook.com/{version}/ads_archive"
        self.http = httpx.Client(timeout=120, headers={"Authorization": f"Bearer {self.token}"})
        self.out = Path(out_dir)
        self.out.mkdir(parents=True, exist_ok=True)
        self.ads_path = self.out / "ads.jsonl"
        self.log_path = self.out / "queries.jsonl"
        self.delay = delay
        self.log = log
        self.fields = list(FIELDS)
        self.seen: set[str] = set()
        if self.ads_path.exists():
            for line in self.ads_path.open(encoding="utf-8"):
                try:
                    self.seen.add(json.loads(line)["id"])
                except Exception:
                    pass

    def _get(self, url: str, params: dict | None) -> dict:
        url = re.sub(r"([?&])access_token=[^&]*&?", r"\1", url).rstrip("?&")  # token z linku stronicowania usuwamy
        for k in range(5):
            r = self.http.get(url, params=params)
            if r.status_code == 200:
                return r.json()
            j = r.json() if r.headers.get("content-type", "").startswith(("application/json", "text/javascript")) else {}
            err = j.get("error", {})
            msg = err.get("message", r.text[:200])
            if err.get("code") in (4, 17, 613) or r.status_code == 429:  # limity zapytań
                wait = 60 * (k + 1)
                self.log(f"limit API, czekam {wait} s")
                time.sleep(wait)
                continue
            m = re.search(r"\(#100\).*?field[s]?\s*\(?([a-z_]+)", msg)
            if m and m.group(1) in self.fields and params:  # nieobsługiwane pole: usuwamy i ponawiamy
                self.fields.remove(m.group(1))
                params["fields"] = ",".join(self.fields)
                continue
            if err.get("code") == 190:
                raise MetaError("token wygasł lub jest nieważny (kod 190)")
            raise MetaError(f"{r.status_code}: {msg}")
        raise MetaError("limit API nie minął")

    def query(self, tag: str, params: dict, max_pages: int = 10, page_size: int = 250) -> int:
        """Jedno zapytanie z paginacją; zwraca liczbę nowych reklam."""
        p = {"ad_reached_countries": '["PL"]', "ad_type": "ALL", "ad_active_status": "ALL", "limit": page_size,
             "fields": ",".join(self.fields), **params}
        url, new, total = self.url, 0, 0
        for page in range(max_pages):
            j = self._get(url, p if page == 0 else None)
            data = j.get("data", [])
            total += len(data)
            with self.ads_path.open("a", encoding="utf-8") as f:
                for ad in data:
                    if ad.get("id") in self.seen:
                        continue
                    self.seen.add(ad["id"])
                    ad["_query"] = tag
                    ad["_collected_at"] = datetime.now(UTC).isoformat(timespec="seconds")
                    f.write(json.dumps(ad, ensure_ascii=False) + "\n")
                    new += 1
            nxt = (j.get("paging") or {}).get("next")
            if not nxt or not data:
                break
            url = nxt
            time.sleep(self.delay)
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"tag": tag, "params": {k: v for k, v in params.items()}, "total": total, "new": new,
                                "at": datetime.now(UTC).isoformat(timespec="seconds")}, ensure_ascii=False) + "\n")
        return new

    def keywords(self, terms: list[str], days: int = 120, max_pages: int = 10) -> None:
        since = (datetime.now(UTC) - timedelta(days=days)).date().isoformat()
        for t in terms:
            try:
                n = self.query(f"kw:{t}", {"search_terms": t, "ad_delivery_date_min": since}, max_pages=max_pages)
                self.log(f"„{t}”: +{n} (razem {len(self.seen)})")
            except MetaError as e:
                self.log(f"„{t}”: błąd {e}")
                if "190" in str(e):
                    raise
            time.sleep(self.delay)

    def pages(self, page_ids: list[str], max_pages: int = 5) -> None:
        for k in range(0, len(page_ids), 10):
            chunk = page_ids[k:k + 10]
            try:
                n = self.query(f"pages:{','.join(chunk)}", {"search_page_ids": json.dumps(chunk)}, max_pages=max_pages)
                self.log(f"strony {k + 1}–{k + len(chunk)}: +{n} (razem {len(self.seen)})")
            except MetaError as e:
                self.log(f"strony {k + 1}–{k + len(chunk)}: błąd {e}")
                if "190" in str(e):
                    raise
            time.sleep(self.delay)


def load_ads(path: Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).open(encoding="utf-8") if line.strip()]


def suspicious_pages(ads: list[dict], min_removed: int = 1) -> list[str]:
    """Strony z reklamami usuniętymi przez Metę (sygnał oszustwa) albo z linkami do typowych domen-wabików."""
    score: dict[str, int] = {}
    for a in ads:
        pid = a.get("page_id")
        if not pid:
            continue
        body = " ".join(a.get("ad_creative_bodies") or [])
        caps = " ".join(a.get("ad_creative_link_captions") or []).lower()
        s = 0
        if REMOVED in body:
            s += 2
        if re.search(r"\.(live|top|icu|xyz|click|pro|sbs|online|site|media|info)\b", caps):
            s += 1
        if s:
            score[pid] = score.get(pid, 0) + s
    return [p for p, s in sorted(score.items(), key=lambda x: -x[1]) if s >= min_removed]
