"""Adapter for CSV exports from the Meta Ad Library UI (or any ad CSV). Column names are matched loosely:
case/space/underscore-insensitive aliases, because the exact export header is unverified."""
from __future__ import annotations

import csv
import hashlib
from datetime import UTC, datetime
from pathlib import Path

from ..schema import Ad
from .meta_api import _dt

ALIASES = {
    "id": ["adid", "adarchiveid", "id", "archiveid"],
    "page_id": ["pageid", "advertiserid"],
    "page_name": ["pagename", "advertiser", "advertisername", "paidforby"],
    "body": ["adcreativebody", "adcreativebodies", "adtext", "body", "text", "creativebody"],
    "title": ["adcreativelinktitle", "adcreativelinktitles", "title", "linktitle"],
    "description": ["adcreativelinkdescription", "adcreativelinkdescriptions", "description", "linkdescription"],
    "link_caption": ["adcreativelinkcaption", "adcreativelinkcaptions", "linkcaption", "caption"],
    "start": ["addeliverystarttime", "deliverystart", "startdate", "adcreationtime", "adcreationdate"],
    "stop": ["addeliverystoptime", "deliverystop", "enddate", "stopdate"],
    "lang": ["languages", "language", "lang"],
    "snapshot": ["adsnapshoturl", "snapshoturl", "url", "adurl"],
    "reach": ["eutotalreach", "reach"],
    "impressions": ["impressions"],
    "spend": ["spend"],
    "currency": ["currency"],
}


def _norm(h: str) -> str:
    return "".join(c for c in h.lower() if c.isalnum())


def _column_map(header: list[str]) -> dict[str, str]:
    by_norm = {_norm(h): h for h in header}
    out = {}
    for field, al in ALIASES.items():
        for a in al:
            if a in by_norm:
                out[field] = by_norm[a]
                break
    return out


def read_csv(file: str | Path, source: str = "meta", now: datetime | None = None) -> list[Ad]:
    now = now or datetime.now(UTC)
    ads: list[Ad] = []
    with open(file, newline="", encoding="utf-8-sig") as f:
        sample = f.read(4096)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        rd = csv.DictReader(f, dialect=dialect)
        cols = _column_map(rd.fieldnames or [])
        if "body" not in cols:
            raise ValueError(f"no ad text column found in {file}; header: {rd.fieldnames}")
        for i, row in enumerate(rd):
            def g(k, row=row):
                return (row.get(cols[k]) or "").strip() if k in cols else ""

            body = g("body")
            if not body:
                continue
            aid = g("id") or hashlib.sha1(f"{g('page_name')}{body}".encode()).hexdigest()[:12]
            meta = {k: g(k) for k in ("reach", "impressions", "spend", "currency", "snapshot") if g(k)}
            ads.append(Ad(
                ad_id=f"{source}:{aid}", source=source, first_seen_at=now, delivery_start=_dt(g("start")),
                delivery_stop=_dt(g("stop")), page_id=g("page_id") or None, page_name=g("page_name") or None,
                body=body, title=g("title") or None, description=g("description") or None,
                link_caption=g("link_caption") or None, lang=(g("lang").split(",")[0].strip() or None),
                meta={**meta, "export_row": i}))
    return ads
