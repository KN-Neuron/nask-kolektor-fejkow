import json

import pytest

from embsim import analyze as A
from embsim.api import Gallery
from embsim.bench import Config
from embsim.synth2 import generate

HAR = json.dumps({"log": {"entries": [{"request": {"url": f"https://x.test{p}"}} for p in
                                      ("/?utm_id=1&utm_medium=2", "/abc/def/app.js", "/abc/def/style.css")]}}).encode()
HTML = "<!-- saved from url=(0020)https://x.test/?utm_id=1 --><html><head><title>Szokujące</title></head><body><p>Wpłać 500 zł i zarabiaj</p></body></html>"


def cfg():
    return Config(adjust_levels=["campaign"], lexical=True, trace_mode="overlap", trace_mode_operator="contain",
                  thresholds={"campaign": 0.6, "operator": 0.25}, e_ref={"campaign": 0.6})


def test_inputs_are_combined_into_one_case_and_url_is_not_visited():
    case, info = A.case_from_inputs([("a.html", HTML.encode()), ("a.har", HAR)], text="Dodatkowy opis produktu", url="https://sklep.pl/oferta?x=1", ocr=False)
    assert "Wpłać 500 zł" in case.text and "Dodatkowy opis produktu" in case.text
    assert case.sets["scheme"] and case.sets["kit"] == {"/abc/def"} and "sklep.pl" in case.sets["host"]
    assert "adresu nie odwiedzamy" in info["url"] and case.id.startswith("nowy_")


def test_meta_record_json_is_recognised():
    rec = {"id": "9", "page_id": "5", "ad_creative_bodies": ["Kup teraz"], "ad_creative_link_titles": ["Promocja"],
           "ad_creative_link_captions": ["sklep-x.pl"], "beneficiary_payers": [{"payer": "Firma"}]}
    case, info = A.case_from_inputs([("r.json", json.dumps(rec).encode())])
    assert case.id == "9" and "reklama Meta" in info["źródło"] and case.sets["payer"] == {"Firma"}


def test_screenshot_without_ocr_warns_and_ocr_degrades_gracefully(tmp_path):
    from PIL import Image, ImageDraw

    p = tmp_path / "z.png"
    im = Image.new("RGB", (400, 120), "white"); ImageDraw.Draw(im).text((10, 40), "PROMOCJA 500 ZL", fill="black"); im.save(p)
    _, info = A.case_from_inputs([("z.png", p.read_bytes())], ocr=False)
    assert any("OCR wyłączony" in w for w in info["ostrzeżenia"])
    _, info = A.case_from_inputs([("z.png", p.read_bytes())], ocr=True)
    if A.ocr_languages():
        assert info["ocr_język"] is not None
    else:
        assert any("OCR niedostępny" in w for w in info["ostrzeżenia"])


def test_reasons_confidence_card_and_network_on_real_gallery(tmp_path):
    generate(tmp_path / "w", seed=3, n_operators=3, campaigns_per_op=2, variants=3, missing_rate=0.0)
    g = Gallery(cfg(), embed_fn=A.hash_embed)
    n = A.build_from_folders(g, tmp_path / "w")
    assert n > 10 and len(g) > 10 and A.gallery_summary(g)["kampanii"] >= 2
    some = g.items[0]["case"]
    new, _ = A.case_from_inputs([], text=some.text, url="")
    new.sets = {k: set(v) for k, v in some.sets.items()}
    d = g.query(new, 5)
    assert d.matches and 1 <= len(A.top_reasons(d.matches[0])) <= 3
    assert A.confidence_label(0.9) == "wysoka" and A.confidence_label(0.6) == "średnia" and "niska" in A.confidence_label(0.2)
    assert A.verdict_style(d)[1] and "Karta materiału" in A.card_markdown(new, d)
    fig = A.network_figure(new, d)
    assert any(t.name == "nowy" for t in fig.data) and any(t.name == "materiał" for t in fig.data)


def test_gallery_clusters_traces_without_hubs_and_dot(tmp_path):
    generate(tmp_path / "w", seed=6, n_operators=3, campaigns_per_op=2, variants=3, missing_rate=0.0)
    g = Gallery(cfg(), embed_fn=A.hash_embed)
    A.build_from_folders(g, tmp_path / "w")
    idx = A.cluster_index(g)
    assert sum(len(v) for o in idx.values() for v in o.values()) == len(g)
    op = max(idx, key=lambda o: sum(len(v) for v in idx[o].values()))
    camps = idx[op]
    all_idx = [i for v in camps.values() for i in v]
    traces = A.shared_traces(g, all_idx)
    cap = max(10, int(A.HUB_FRACTION * len(g.items)))
    assert all(t["w galerii"] <= cap and len(t["materiały"]) >= 2 for t in traces)          # bez hubów, tylko ślady wspólne
    assert traces == sorted(traces, key=lambda t: (t["w galerii"], -len(t["materiały"])))   # rzadkie najpierw
    dot = A.cluster_dot(g, camps, f"operator {op}", traces)
    assert dot.startswith("graph G {") and dot.rstrip().endswith("}") and "cluster_op" in dot and 'label="kampania' in dot
    md = A.cluster_markdown(f"operator {op}", [{"materiał": "a", "kampania": "K1", "operator": op, "tekst": "x"}], traces)
    assert md.startswith("# Klaster: operator") and "## Materiały" in md
