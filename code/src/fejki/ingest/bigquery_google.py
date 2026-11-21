"""Google Ads Transparency Center via BigQuery (public dataset, needs a GCP project with the BigQuery API enabled).

Table: bigquery-public-data.google_ads_transparency_center.creative_stats. Column names are unverified and we
select only columns that exist (via get_table). NOTE: this table is not known to contain ad text (it has the
advertiser, the creative preview URL and dates), so the text channel will be mostly empty: rows are useful for
the advertiser/infrastructure channel. Not tested against live BigQuery.
"""
from __future__ import annotations

from datetime import UTC, datetime

from ..config import env
from ..schema import Ad
from .meta_api import _dt

TABLE = "bigquery-public-data.google_ads_transparency_center.creative_stats"
WANTED = ["creative_id", "advertiser_id", "advertiser_disclosed_name", "advertiser_legal_name", "advertiser_location",
          "ad_url", "creative_page_url", "ad_format_type", "regions", "first_shown", "last_shown"]


def row_to_ad(row: dict, now: datetime | None = None) -> Ad:
    name = row.get("advertiser_disclosed_name") or row.get("advertiser_legal_name")
    url = row.get("ad_url") or row.get("creative_page_url")
    meta = {k: str(row[k]) for k in ("advertiser_legal_name", "advertiser_location", "ad_format_type", "regions") if row.get(k)}
    if url:
        meta["ad_url"] = url
    return Ad(ad_id=f"google:{row['creative_id']}", source="google", first_seen_at=now or datetime.now(UTC),
              delivery_start=_dt(row.get("first_shown")), delivery_stop=_dt(row.get("last_shown")),
              page_id=row.get("advertiser_id"), page_name=name, body="", link_caption=url, meta=meta)


def fetch(region: str = "PL", days: int = 30, limit: int = 5000, project: str | None = None) -> list[dict]:
    try:
        from google.cloud import bigquery
    except ImportError as e:
        raise RuntimeError("pip install google-cloud-bigquery; then `gcloud auth application-default login`") from e
    client = bigquery.Client(project=project or env("GCP_PROJECT") or None)
    have = {f.name for f in client.get_table(TABLE).schema}
    cols = [c for c in WANTED if c in have]
    if "creative_id" not in cols:
        raise RuntimeError(f"unexpected schema of {TABLE}: {sorted(have)}")
    where = []
    if "regions" in have:
        where.append("regions LIKE @region")
    if "last_shown" in have:
        where.append("last_shown >= DATE_SUB(CURRENT_DATE(), INTERVAL @days DAY)")
    sql = f"SELECT {', '.join(cols)} FROM `{TABLE}`" + (f" WHERE {' AND '.join(where)}" if where else "") + f" LIMIT {int(limit)}"
    cfg = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("region", "STRING", f"%{region}%"),
                                                    bigquery.ScalarQueryParameter("days", "INT64", days)])
    return [dict(r) for r in client.query(sql, job_config=cfg).result()]
