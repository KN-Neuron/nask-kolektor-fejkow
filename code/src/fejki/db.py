"""DuckDB persistence."""
from __future__ import annotations

import json
from pathlib import Path

import duckdb

from .schema import Ad

DDL = [
    "CREATE TABLE IF NOT EXISTS ads (ad_id VARCHAR PRIMARY KEY, source VARCHAR, first_seen_at TIMESTAMP, "
    "delivery_start TIMESTAMP, page_id VARCHAR, removed_after_seen BOOLEAN, truth_campaign VARCHAR, json VARCHAR)",
    "CREATE TABLE IF NOT EXISTS ad_vectors (ad_id VARCHAR, model VARCHAR, split VARCHAR, row_idx INTEGER)",
    "CREATE TABLE IF NOT EXISTS cert_entries (domain VARCHAR, insert_date TIMESTAMP, delete_date TIMESTAMP, snapshot_at TIMESTAMP)",
    "CREATE TABLE IF NOT EXISTS clusters (run_id VARCHAR, ad_id VARCHAR, cluster_id INTEGER, channel VARCHAR)",
    "CREATE TABLE IF NOT EXISTS campaigns (run_id VARCHAR, campaign_id VARCHAR, first_seen TIMESTAMP, n_ads INTEGER, score_json VARCHAR)",
    "CREATE TABLE IF NOT EXISTS campaign_members (run_id VARCHAR, campaign_id VARCHAR, ad_id VARCHAR)",
    "CREATE TABLE IF NOT EXISTS graph_edges (run_id VARCHAR, src VARCHAR, dst VARCHAR, etype VARCHAR, weight DOUBLE)",
    "CREATE TABLE IF NOT EXISTS comments (comment_id VARCHAR PRIMARY KEY, ad_id VARCHAR, author_hash VARCHAR, text VARCHAR, ts TIMESTAMP, source VARCHAR)",
    "CREATE TABLE IF NOT EXISTS eval_runs (run_id VARCHAR, experiment VARCHAR, config_json VARCHAR, seed INTEGER, git_hash VARCHAR, metrics_json VARCHAR, ts TIMESTAMP DEFAULT current_timestamp)",
]


def connect(path: str | Path) -> duckdb.DuckDBPyConnection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    for q in DDL:
        con.execute(q)
    return con


def upsert_ads(con, ads: list[Ad]) -> int:
    for a in ads:
        con.execute(
            "INSERT OR REPLACE INTO ads VALUES (?,?,?,?,?,?,?,?)",
            [a.ad_id, a.source, a.first_seen_at, a.delivery_start, a.page_id, a.removed_after_seen,
             a.truth_campaign, a.model_dump_json()],
        )
    return len(ads)


def load_ads(con, sources: list[str] | None = None) -> list[Ad]:
    q = "SELECT json FROM ads"
    args: list = []
    if sources:
        q += " WHERE source IN (" + ",".join("?" * len(sources)) + ")"
        args = sources
    return [Ad.model_validate_json(r[0]) for r in con.execute(q, args).fetchall()]


def log_eval(con, experiment: str, cfg: dict, seed: int, git: str, metrics: dict) -> None:
    con.execute(
        "INSERT INTO eval_runs (run_id, experiment, config_json, seed, git_hash, metrics_json) VALUES (?,?,?,?,?,?)",
        [f"{experiment}-{seed}-{git}", experiment, json.dumps(cfg, default=str), seed, git, json.dumps(metrics, default=str)],
    )
