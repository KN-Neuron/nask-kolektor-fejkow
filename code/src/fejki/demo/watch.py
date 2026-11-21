"""Scheduler: okresowe wyszukiwanie podejrzanych reklam w Meta Ad Library i dopasowanie ich do znanych kampanii.

Jedno uruchomienie (`run_once`):
1. zapytania `ads_archive` po słowach kluczowych (kraj PL, tylko ostatnie `days` dni, tylko reklamy NOWE od poprzedniego przebiegu),
2. każda nowa reklama staje się materiałem (tekst, tytuł, domena z linku, reklamodawca, identyfikator reklamy),
3. dopasowanie do indeksu: do znanej kampanii / sieci albo „nowy wzorzec”; reklamy usunięte przez Metę oznaczone,
4. raport CSV z historią (`data/meta/watch_report.csv`, dopisywany).
Token tylko z `code/.env` (`META_ACCESS_TOKEN`); bez tokenu scheduler zgłasza błąd, a reszta narzędzia działa.
"""
from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from ..sources.meta_library import REMOVED, Collector, MetaError, load_ads
from .batch import analyze
from .material import Material, build_material
from .store import Index


def material_from_ad(ad: dict) -> Material:
    body = " ".join(ad.get("ad_creative_bodies") or [])
    titles = ad.get("ad_creative_link_titles") or []
    caps = ad.get("ad_creative_link_captions") or []
    urls = [c if c.startswith("http") else f"https://{c}" for c in caps if "." in c and " " not in c.strip()]
    m = build_material(f"meta:{ad['id']}", f"reklama Meta {ad['id']}", "tekst", urls=urls,
                       text=" ".join([*titles, body]), ocr=False)
    m.ad_ids = [ad["id"], *m.ad_ids]
    if ad.get("page_name"):
        m.advertisers = [ad["page_name"]]
    m.titles = [t for t in titles if t][:2] or m.titles
    start = ad.get("ad_delivery_start_time")
    if start:
        m.observed.append({"date": start[:19], "source": "data rozpoczęcia emisji (Meta Ad Library)"})
    if REMOVED in body:
        m.notes.append("reklama usunięta przez Metę (treść niedostępna w API)")
    return m


def run_once(idx: Index, keywords: list[str], out_dir: Path, days: int = 7, max_pages: int = 2, thr: float = 0.7,
             maybe: float = 0.4, log=print) -> pd.DataFrame:
    c = Collector(out_dir, log=log)
    before = set(c.seen)
    c.keywords(keywords, days=days, max_pages=max_pages)
    new_ads = [a for a in load_ads(out_dir / "ads.jsonl") if a["id"] not in before]
    log(f"nowych reklam od poprzedniego przebiegu: {len(new_ads)}")
    if not new_ads:
        return pd.DataFrame()
    mats = [material_from_ad(a) for a in new_ads]
    df, _ = analyze(idx, mats, thr, maybe)
    df.insert(0, "czas przebiegu", datetime.now(UTC).isoformat(timespec="seconds"))
    df["usunięta przez Metę"] = [any("usunięta przez Metę" in n for n in m.notes) for m in mats]
    report = out_dir / "watch_report.csv"
    df.to_csv(report, mode="a", header=not report.exists(), index=False)
    return df


def loop(idx: Index, keywords: list[str], out_dir: Path, every_min: int = 60, **kw) -> None:
    while True:
        try:
            run_once(idx, keywords, out_dir, **kw)
        except MetaError as e:
            print(f"scheduler: {e}")
            if "190" in str(e):
                return
        time.sleep(every_min * 60)
