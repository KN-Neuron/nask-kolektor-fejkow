"""CERT Polska Warning List v2: tolerant parser plus snapshot download.

Exact JSON/XML field names are unverified: we look for keys containing 'domain', 'insert' and 'delete'/'remove'.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from ..config import env, path


def _parse_dt(v) -> datetime | None:
    if not v:
        return None
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v, tz=UTC)
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = datetime.strptime(str(v)[:10], "%Y-%m-%d")
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _find(d: dict, *subs: str):
    for k, v in d.items():
        kl = k.lower()
        if any(s in kl for s in subs):
            return v
    return None


def _walk(obj):
    if isinstance(obj, dict):
        if _find(obj, "domain") is not None and not isinstance(_find(obj, "domain"), (dict, list)):
            yield obj
        else:
            for v in obj.values():
                yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def parse_cert(raw) -> list[dict]:
    out = []
    for rec in _walk(raw):
        dom = _find(rec, "domain")
        if not isinstance(dom, str):
            continue
        out.append({
            "domain": dom.strip().lower().lstrip("*."),
            "insert_date": _parse_dt(_find(rec, "insert", "added", "create")),
            "delete_date": _parse_dt(_find(rec, "delete", "remove")),
        })
    return out


def load_cert_file(p: str | Path) -> list[dict]:
    return parse_cert(json.loads(Path(p).read_text()))


def fetch_cert(fmt: str = "json") -> list[dict]:
    import httpx

    base = env("CERT_BASE_URL", "https://hole.cert.pl/domains/v2/")
    r = httpx.get(base + f"domains.{fmt}", timeout=60, follow_redirects=True)
    r.raise_for_status()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    raw_path = path(f"data/cert/raw_{stamp}.json")
    raw_path.write_text(r.text)
    return parse_cert(r.json())


def store_cert(con, entries: list[dict], snapshot_at: datetime | None = None) -> None:
    snap = snapshot_at or datetime.now(UTC)
    con.execute("DELETE FROM cert_entries")
    for e in entries:
        con.execute("INSERT INTO cert_entries VALUES (?,?,?,?)", [e["domain"], e["insert_date"], e["delete_date"], snap])


def load_cert_db(con) -> dict[str, dict]:
    rows = con.execute("SELECT domain, insert_date, delete_date FROM cert_entries").fetchall()
    return {d: {"insert_date": i, "delete_date": x} for d, i, x in rows}
