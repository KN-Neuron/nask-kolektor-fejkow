"""Wsad nowego zbioru, eksport grafu, scheduler (atrapa), logotypy i kanał semantyczny, na sztucznych plikach."""
from __future__ import annotations

import zipfile

import numpy as np
from test_demo import PIXEL, STORY, TDS, _case

from fejki.demo.batch import analyze, discover, extract_zip, materials_from
from fejki.demo.export import build_graph, csvs, cypher, graphml
from fejki.demo.material import brand_logos
from fejki.demo.similar import TextSpace, all_pairs, campaigns, evidence
from fejki.demo.store import Index
from fejki.demo.watch import material_from_ad


def _index(tmp_path):
    a = _case(tmp_path, "1", "Wiem, kto strzelał: zamach", STORY, "alpha-news.live", pixel=PIXEL)
    b = _case(tmp_path, "2", "Wiem, kto strzelał: zamach", STORY, "beta-news.live", pixel=PIXEL)
    c = _case(tmp_path, "3", "Kardiolog ostrzega", "Nowy suplement obniża ciśnienie w 7 dni. Zamów kapsułki dziś.",
              "gamma-health.top", kit="/inny/zestaw", query="utm_source=fb")
    return Index(built_at="t", data_dir=str(tmp_path), materials=[a, b, c])


def test_discover_folder_flat_and_zip(tmp_path):
    new = tmp_path / "nowe"
    d = _case(new.parent / "tmp_src" if False else tmp_path, "9", "Nowy", STORY, "delta-news.live", pixel=PIXEL)
    src = tmp_path / "9"
    # układ 1: folder z podfolderami
    root = tmp_path / "zbior"
    (root / "do_udostepnienia").mkdir(parents=True)
    (root / "do_udostepnienia" / "9").mkdir()
    for f in src.rglob("*"):
        if f.is_file():
            (root / "do_udostepnienia" / "9" / f.name).write_bytes(f.read_bytes())
    assert [k for k, _ in discover(root)] == ["9"]
    # układ 2: płaski folder (pliki o tej samej nazwie bazowej = jeden materiał)
    flat = tmp_path / "plaski"
    flat.mkdir()
    (flat / "strona.html").write_text("<html><title>X</title></html>", encoding="utf-8")
    (flat / "strona.har").write_text("{}", encoding="utf-8")
    (flat / "inny.png").write_bytes(b"x")
    assert {k for k, _ in discover(flat)} == {"strona", "inny"}
    # układ 3: zip
    z = tmp_path / "n.zip"
    with zipfile.ZipFile(z, "w") as zz:
        zz.write(flat / "strona.html", "strona.html")
        zz.write(flat / "inny.png", "inny.png")
    assert {k for k, _ in discover(z)} == {"strona", "inny"}
    assert d.id == "9"


def test_zip_slip_is_blocked(tmp_path):
    z = tmp_path / "zly.zip"
    with zipfile.ZipFile(z, "w") as zz:
        zz.writestr("../../ucieczka.txt", "x")
        zz.writestr("ok.txt", "x")
    dest = tmp_path / "out"
    dest.mkdir()
    extract_zip(z, dest)
    assert (dest / "ok.txt").exists() and not (tmp_path.parent / "ucieczka.txt").exists()


def test_batch_assigns_variant_flags_new_and_proposes_campaign(tmp_path):
    idx = _index(tmp_path)
    new = tmp_path / "nowe"
    new.mkdir()
    # wariant znanej kampanii (inna domena, ten sam tekst i piksel)
    _case(new, "v1", "Wiem, kto strzelał: zamach", STORY, "delta-news.live", pixel=PIXEL)
    # dwa nowe, podobne do siebie materiały spoza zbioru (ten sam obcy tekst i piksel)
    obcy = "Odbierz bonus w kasynie. Zagraj w automaty, wpłać depozyt i wygraj nagrodę już dziś. " * 5
    _case(new, "n1", "Kasyno bonus", obcy, "casino-a.xyz", pixel="9999999999999991", query="utm_source=fb", kit="/kasyno/a")
    _case(new, "n2", "Kasyno bonus", obcy, "casino-b.xyz", pixel="9999999999999991", query="utm_source=fb", kit="/kasyno/b")
    _case(new, "x1", "Przepis na sernik", "Przepis na sernik z rodzynkami i wanilią. Piec godzinę.", "kuchnia.example", query="a=1", kit="/k")
    mats = materials_from(new, ocr=False)
    df, proposals = analyze(idx, mats)
    by = df.set_index("materiał")
    assert by.loc["v1", "decyzja"].startswith("przypisano do kampanii")
    assert by.loc["x1", "decyzja"].startswith("nowy wzorzec")
    assert any(set(p["materiały"]) == {"n1", "n2"} for p in proposals)
    assert by.loc["n1", "nowa kampania (propozycja)"] == by.loc["n2", "nowa kampania (propozycja)"] != ""


def test_graph_export_formats(tmp_path):
    idx = _index(tmp_path)
    pairs = all_pairs(idx.materials)
    g = build_graph(idx.materials, pairs, campaigns(idx.materials, pairs, 0.7, "kampania"), campaigns(idx.materials, pairs, 0.7, "sieć"))
    assert "<graphml" in graphml(g)
    cy = cypher(g)
    assert 'MERGE (n:Node {key: "m:1"})' in cy and "[r:SIMILAR]" in cy and '"label"' not in cy  # klucze map bez cudzysłowu
    c = csvs(g)
    assert c["nodes.csv"].startswith("key,kind,label") and "SIMILAR" in c["edges.csv"]


def test_meta_ad_becomes_material_and_matches_known_campaign(tmp_path):
    idx = _index(tmp_path)
    ad = {"id": "123", "page_name": "Strona Testowa", "ad_creative_bodies": [STORY], "ad_creative_link_titles": ["Zamach"],
          "ad_creative_link_captions": ["alpha-news.live"], "ad_delivery_start_time": "2026-11-20T10:00:00+0000"}
    m = material_from_ad(ad)
    assert m.ad_ids[0] == "123" and m.landing_domains == ["alpha-news.live"] and m.advertisers == ["Strona Testowa"]
    assert m.observed[0]["date"].startswith("2026-11-20")
    df, _ = analyze(idx, [m])
    assert "alpha" not in df.loc[0, "decyzja"] and df.loc[0, "najlepszy wynik"] >= 0.7
    removed = material_from_ad({"id": "5", "ad_creative_bodies": ["This content was removed because it didn't follow our Advertising Standards."]})
    assert any("usunięta przez Metę" in n for n in removed.notes)


def test_logo_brand_and_semantic_channel(tmp_path):
    from pathlib import Path

    assert brand_logos([Path("logo-gazeta.svg"), Path("header-logo.png"), Path("tvn24-logo.webp"), Path("hero.jpg")]) == ["gazeta", "tvn24"]
    idx = _index(tmp_path)
    a, c = idx.materials[0], idx.materials[2]
    ts = TextSpace(idx.materials)
    ts.sem = {"1": np.array([1.0, 0.0]), "3": np.array([0.96, 0.28])}  # cos = 0,96
    codes = {e.code for e in evidence(a, c, ts, {"person": {}, "topic": {}, "host": {}, "prefix": {}})[0]}
    assert "semantic" in codes
    ts.sem = {"1": np.array([1.0, 0.0]), "3": np.array([0.6, 0.8])}  # cos = 0,6: poniżej tła, brak dowodu
    assert "semantic" not in {e.code for e in evidence(a, c, ts, {"person": {}, "topic": {}, "host": {}, "prefix": {}})[0]}
    assert TDS  # (import wykorzystany)
