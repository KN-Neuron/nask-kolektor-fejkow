"""Kolektor urlscan na atrapie HTTP (bez sieci) i odczyt folderu przypadku przez ekstrakcję cech."""
from __future__ import annotations

import csv
import io
import json

import httpx
from PIL import Image

from fejki.demo.evaluate import against_labels, bcubed
from fejki.demo.material import material_from_folder
from fejki.sources.urlscan import Client, collect

TDS = "utm_id=AbCdEfGhIjKlMnOpQrSt&utm_medium=Ab12Cd34Ef&utm_campaign=Gh56Ij78Kl&utm_content=Mn90Op12Qr&utm_visit=01a19999-1111-7222-8333-444455556666"


def _hit(uuid, domain, title, age=2):
    return {"_id": uuid, "sort": [1, uuid],
            "task": {"uuid": uuid, "time": "2026-11-20T10:00:00.000Z", "url": f"http://{domain}/"},
            "page": {"url": f"https://{domain}/?{TDS}", "domain": domain, "apexDomain": domain, "title": title,
                     "domainAgeDays": age, "tlsAgeDays": 1, "asn": "AS13335", "asnname": "CLOUDFLARENET"}}


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(buf, "PNG")
    return buf.getvalue()


def _client(hits, calls):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        assert "/scan/" not in request.url.path  # nigdy nie zlecamy nowych skanów
        if request.url.path == "/api/v1/search/":
            return httpx.Response(200, json={"total": len(hits), "has_more": False, "results": hits})
        if request.url.path.startswith("/screenshots/"):
            return httpx.Response(200, content=_png(), headers={"content-type": "image/png"})
        return httpx.Response(403, json={"warning": "You're not logged in!"})

    return Client(api_key="", delay=0, http=httpx.Client(transport=httpx.MockTransport(handler)))


def test_collect_writes_case_folders_and_labels(tmp_path):
    calls = []
    hits = [_hit("u1", "alpha-invest.media", "Verdienen Sie 950 EUR"), _hit("u2", "beta-invest.media", "Verdienen Sie 950 EUR"),
            _hit("u3", "alpha-invest.media", "Verdienen Sie 950 EUR")]  # druga kopia tej samej domeny
    c = _client(hits, calls)
    rows = collect(c, [{"label": "zestaw-x", "query": 'filename:"x.js"', "limit": 10}], tmp_path, max_per_domain=1, log=lambda *_: None)
    assert [r["case_id"] for r in rows] == ["u1", "u2"]  # limit na domenę
    assert (tmp_path / "u1" / "urlscan.json").exists() and (tmp_path / "u1" / "screenshot.png").exists()
    assert not (tmp_path / "u1" / "dom.html").exists()  # bez klucza nie ma DOM
    labels = list(csv.DictReader((tmp_path / "labels.csv").open(encoding="utf-8")))
    assert labels[0]["label"] == "zestaw-x" and labels[0]["source"].startswith("https://urlscan.io/result/")
    assert not any("/scan/" in u for u in calls)


def test_case_folder_is_readable_as_material(tmp_path):
    c = _client([_hit("u1", "alpha-invest.media", "Verdienen Sie 950 EUR", age=3)], [])
    collect(c, [{"label": "zestaw-x", "query": "q", "limit": 5}], tmp_path, log=lambda *_: None)
    m = material_from_folder(tmp_path / "u1", ocr=False)
    assert m.landing_domains == ["alpha-invest.media"]
    assert m.titles == ["Verdienen Sie 950 EUR"]
    assert m.url_schemes and "utm_visit:uuid" in m.url_schemes[0]
    assert any("wiek domeny w chwili skanu: 3 dni" in n for n in m.notes)
    assert m.observed and m.observed[0]["source"] == "czas skanu urlscan.io"


def test_bcubed_and_labels_with_negatives(tmp_path):
    assert bcubed({"a": "1", "b": "1"}, {"a": "x", "b": "x"})["f1"] == 1.0
    c = _client([_hit("p1", "alpha-invest.media", "Verdienen Sie 950 EUR"), _hit("p2", "beta-invest.media", "Verdienen Sie 950 EUR")], [])
    collect(c, [{"label": "zestaw-x", "query": "q", "limit": 5}], tmp_path, log=lambda *_: None)
    neg = tmp_path / "n1"
    neg.mkdir()
    (neg / "urlscan.json").write_text(json.dumps({"label": "neg", "search_hit": {
        "task": {"time": "2026-11-20T10:00:00Z"}, "page": {"url": "https://wiadomosci.example.pl/artykul", "title": "Prawdziwy news"}}}),
        encoding="utf-8")
    mats = [material_from_folder(tmp_path / x, ocr=False) for x in ("p1", "p2", "n1")]
    labels = {"p1": {"label": "zestaw-x", "kind": "pozytyw"}, "p2": {"label": "zestaw-x", "kind": "pozytyw"},
              "n1": {"label": "neg", "kind": "negatyw"}}
    res = against_labels(mats, labels)
    assert res["sieć"]["f1"] == 1.0 and res["sieć"]["negatywy_doklejone_do_oszustw"] == 0
