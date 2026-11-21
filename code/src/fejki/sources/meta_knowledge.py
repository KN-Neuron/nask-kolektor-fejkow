"""Wiedza z zebranych reklam Meta Ad Library: co wiemy o domenie, stronie-reklamodawcy lub identyfikatorze reklamy.

To NIE jest wynik podobieństwa, tylko kontekst dla analityka: „ta domena pojawia się w N reklamach, M usuniętych przez Metę, strony X, Y”.
Dane lokalne (`data/meta/ads.jsonl`), budowane `fejki.sources.meta_library`. Bez pliku moduł zwraca puste wyniki.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from .meta_library import REMOVED

DOM = re.compile(r"(?:https?://)?([a-z0-9.-]+\.[a-z]{2,})", re.I)


class MetaKnowledge:
    def __init__(self, path: Path):
        self.by_domain: dict[str, list[dict]] = defaultdict(list)
        self.by_page: dict[str, list[dict]] = defaultdict(list)
        self.by_id: dict[str, dict] = {}
        self.n = 0
        p = Path(path)
        if not p.exists():
            return
        for line in p.open(encoding="utf-8"):
            try:
                a = json.loads(line)
            except ValueError:
                continue
            self.n += 1
            self.by_id[a["id"]] = a
            if a.get("page_name"):
                self.by_page[a["page_name"].lower()].append(a)
            for c in a.get("ad_creative_link_captions") or []:
                m = DOM.match(c.strip())
                if m:
                    self.by_domain[m.group(1).lower().removeprefix("www.")].append(a)

    @staticmethod
    def removed(a: dict) -> bool:
        return REMOVED in " ".join(a.get("ad_creative_bodies") or [])

    def summary(self, ads: list[dict]) -> dict:
        pages = {a.get("page_name") for a in ads if a.get("page_name")}
        starts = sorted(a["ad_delivery_start_time"][:10] for a in ads if a.get("ad_delivery_start_time"))
        return {"reklam": len(ads), "usuniętych przez Metę": sum(self.removed(a) for a in ads), "stron-reklamodawców": len(pages),
                "przykładowe strony": sorted(pages)[:5], "pierwsza emisja": starts[0] if starts else None,
                "ostatnia emisja": starts[-1] if starts else None}

    def lookup(self, domains: list[str], advertisers: list[str], ad_ids: list[str]) -> list[dict]:
        rows = []
        for d in domains:
            ads = self.by_domain.get(d.lower().removeprefix("www."), [])
            if ads:
                rows.append({"po czym": f"domena {d}", **self.summary(ads)})
        for v in advertisers:
            ads = self.by_page.get(v.lower(), [])
            if ads:
                rows.append({"po czym": f"strona-reklamodawca „{v}”", **self.summary(ads)})
        for i in ad_ids:
            a = self.by_id.get(i)
            if a:
                rows.append({"po czym": f"identyfikator reklamy {i}", **self.summary([a])})
        return rows
