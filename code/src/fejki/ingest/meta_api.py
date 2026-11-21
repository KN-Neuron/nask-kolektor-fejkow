"""Meta Ad Library adapter (official Graph API, ads_archive). Field names unverified: unsupported fields are dropped on 400."""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from datetime import UTC, datetime

import httpx

from ..config import env, path
from ..schema import Ad

log = logging.getLogger(__name__)
FIELDS = ["id", "ad_creation_time", "ad_delivery_start_time", "ad_delivery_stop_time", "ad_creative_bodies",
          "ad_creative_link_captions", "ad_creative_link_descriptions", "ad_creative_link_titles", "ad_snapshot_url",
          "page_id", "page_name", "bylines", "languages", "publisher_platforms", "impressions", "spend", "currency",
          "eu_total_reach", "beneficiary_payers"]


def _dt(v) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00").replace("+0000", "+00:00"))
    except ValueError:
        return None


def to_ad(rec: dict, now: datetime | None = None) -> Ad:
    j = lambda k: " ".join(rec.get(k) or [])
    now = now or datetime.now(UTC)
    start = _dt(rec.get("ad_delivery_start_time"))
    meta = {k: rec.get(k) for k in ("impressions", "spend", "currency", "eu_total_reach", "beneficiary_payers",
                                      "bylines", "publisher_platforms", "ad_snapshot_url") if rec.get(k) is not None}
    return Ad(
        ad_id=f"meta:{rec['id']}", source="meta", first_seen_at=now, delivery_start=start or _dt(rec.get("ad_creation_time")),
        delivery_stop=_dt(rec.get("ad_delivery_stop_time")), page_id=rec.get("page_id"), page_name=rec.get("page_name"),
        body=j("ad_creative_bodies"), title=j("ad_creative_link_titles") or None, description=j("ad_creative_link_descriptions") or None,
        link_caption=j("ad_creative_link_captions") or None, lang=(rec.get("languages") or [None])[0], meta=meta)


class MetaAccessError(RuntimeError):
    """Raised for Graph API errors; message never contains the access token."""


def _get(url: str, params: dict, token: str) -> httpx.Response:
    """GET with the token in the Authorization header; a token embedded in a paging URL is stripped."""
    url = re.sub(r"([?&])access_token=[^&]*&?", r"\1", url).rstrip("?&")
    return httpx.get(url, params=params, headers={"Authorization": f"Bearer {token}"}, timeout=60)


def _raise_for_error(r: httpx.Response) -> None:
    if r.status_code < 400:
        return
    try:
        err = r.json().get("error", {})
    except ValueError:
        err = {}
    code, sub = err.get("code"), err.get("error_subcode")
    hint = ""
    if (code, sub) == (10, 2332002):
        hint = " Konto/aplikacja nie ma dostepu do Ad Library API: potwierdz tozsamosc i warunki na facebook.com/ads/library/api."
    elif code == 613:
        hint = " Limit zapytan (613)."
    raise MetaAccessError(f"HTTP {r.status_code} code={code} subcode={sub}: {err.get('message', r.text[:200])}.{hint}")


def fetch(query: str, countries=("PL",), days: int = 30, limit: int = 100, max_pages: int = 20, cfg: dict | None = None) -> list[dict]:
    token = env("META_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("META_ACCESS_TOKEN not set; work offline with fixtures")
    ver = env("META_API_VERSION") or (cfg or {}).get("meta", {}).get("api_version", "v21.0")
    fields = list(FIELDS)
    params = {"search_terms": query, "ad_reached_countries": json.dumps(list(countries)), "ad_type": "ALL",
              "ad_active_status": "ALL", "limit": limit}
    url = f"https://graph.facebook.com/{ver}/ads_archive"
    out: list[dict] = []
    for _ in range(max_pages):
        key = hashlib.sha1(f"{url}{query}{fields}{len(out)}".encode()).hexdigest()[:16]
        cache = path(f"data/raw/meta/{key}.json")
        if cache.exists():
            data = json.loads(cache.read_text())
        else:
            for attempt in range(5):
                r = _get(url, {**params, "fields": ",".join(fields)} if params else {}, token)
                if r.status_code == 400:
                    m = re.search(r"(?:nonexisting field|Unsupported field)[^(]*\(?(\w+)", r.text, re.IGNORECASE)
                    bad = m.group(1) if m else None
                    if bad in fields:
                        log.warning("dropping unsupported field %s", bad)
                        fields.remove(bad)
                        continue
                rate_limited = r.status_code == 400 and '"code":613' in r.text.replace(" ", "")
                if r.status_code in (429, 500, 503) or rate_limited:
                    time.sleep(min(2 ** attempt * (30 if rate_limited else 1), 300))
                    continue
                _raise_for_error(r)
                break
            data = r.json()
            cache.write_text(json.dumps(data))
        out += data.get("data", [])
        nxt = data.get("paging", {}).get("next")
        if not nxt:
            break
        url, params = nxt, {}
    return out


def mark_removed(prev_ads: dict[str, Ad], seen_now: dict[str, Ad], now: datetime) -> list[Ad]:
    """Ads that had content when first seen but now come back empty are flagged as removed (weak label, DSA 39(3))."""
    flagged = []
    for aid, a in seen_now.items():
        old = prev_ads.get(aid)
        if old and old.body and not a.body and not old.removed_after_seen:
            old.removed_after_seen = True
            old.meta["removed_detected_at"] = now.isoformat()
            flagged.append(old)
    return flagged
