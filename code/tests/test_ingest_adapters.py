import httpx
import pytest

from fejki.ingest import meta_api
from fejki.ingest.bigquery_google import row_to_ad
from fejki.ingest.csv_export import read_csv


def test_csv_loose_columns_semicolon(tmp_path):
    f = tmp_path / "e.csv"
    f.write_text("﻿Ad Archive ID;Page Name;Ad Creative Body;Ad Delivery Start Time\n"
                 "1;Acme;Zainwestuj 250 zl i zarabiaj;2026-11-01\n2;Acme;;2026-11-02\n", encoding="utf-8")
    ads = read_csv(f)
    assert len(ads) == 1 and ads[0].ad_id == "meta:1" and ads[0].page_name == "Acme" and ads[0].delivery_start


def test_csv_without_text_column_fails(tmp_path):
    f = tmp_path / "e.csv"
    f.write_text("a,b\n1,2\n")
    with pytest.raises(ValueError):
        read_csv(f)


def test_google_row_to_ad():
    a = row_to_ad({"creative_id": "CR1", "advertiser_id": "AR1", "advertiser_disclosed_name": "X", "ad_url": "https://u"})
    assert a.source == "google" and a.page_name == "X" and a.meta["ad_url"] == "https://u"


def test_meta_token_in_header_and_stripped_from_error(monkeypatch, tmp_path):
    seen = {}

    def fake(url, params=None, headers=None, timeout=None):
        seen.update(url=url, params=params, headers=headers)
        return httpx.Response(400, json={"error": {"code": 10, "error_subcode": 2332002, "message": "no perm"}},
                              request=httpx.Request("GET", url))

    monkeypatch.setattr(meta_api.httpx, "get", fake)
    monkeypatch.setattr(meta_api, "path", lambda p: tmp_path / p.split("/")[-1])
    monkeypatch.setattr(meta_api, "env", lambda k: "SECRETTOKEN" if k == "META_ACCESS_TOKEN" else None)
    with pytest.raises(meta_api.MetaAccessError) as e:
        meta_api.fetch("x")
    assert "SECRETTOKEN" not in str(e.value) and "2332002" in str(e.value)
    assert seen["headers"]["Authorization"] == "Bearer SECRETTOKEN" and "access_token" not in seen["params"]
