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
    dot = A.network_dot(new, d)
    assert dot.startswith("digraph G {") and '"NOWY"' in dot and dot.count('"NOWY" ->') == len(d.matches[:5])


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
    boxes = A.trace_boxes(g, camps, traces)
    edges = dot.count(" -- ")
    assert 0 < edges <= sum(len(b["materiały"]) for b in boxes) <= sum(len(t["materiały"]) for t in traces)   # ramka zamiast śladu
    assert all(b["kampania"] is None or len(b["kampanie"]) == 1 for b in boxes)
    assert isinstance(A.cluster_summary(g, camps, traces), list)
    md = A.cluster_markdown(f"operator {op}", [{"materiał": "a", "kampania": "K1", "operator": op, "tekst": "x"}], traces)
    assert md.startswith("# Klaster: operator") and "## Materiały" in md


def test_url_passive_scheme_and_blocked_private_fetch():
    from embsim import analyze as A
    c, info = A.case_from_inputs([], "", "https://x-scam.xyz/?utm_id=1&utm_visit=2", fetch=False)
    assert c.sets["host"] == {"x-scam.xyz"} and c.sets["scheme"] == {"utm_id,utm_visit"}
    c, info = A.case_from_inputs([], "", "http://127.0.0.1:9/", fetch=True)
    assert any("prywatn" in w for w in info["ostrzeżenia"]) and "img" not in c.sets


def test_fetch_builds_html_and_har(tmp_path, monkeypatch):
    import json
    from embsim import fetch as F

    class R:
        def __init__(self, url, body, ct, status=200, loc=None):
            self.status_code, self._b, self.encoding = status, body, "utf-8"
            self.headers = {"content-type": ct, **({"location": loc} if loc else {})}
            self.is_redirect = loc is not None
        def iter_content(self, n): yield self._b
        def close(self): pass

    pages = {"http://scam.test/": R("", b"", "", 302, "http://scam.test/lp"),
             "http://scam.test/lp": R("", b'<html><body>Zarabiaj z AI<img src="/a.png"><script src="https://cdn.kit.test/x/y/app.js"></script></body></html>', "text/html"),
             "http://scam.test/a.png": R("", b"\x89PNG" + b"0" * 4000, "image/png")}

    class S:
        headers = {}
        def get(self, url, **kw): return pages[url]

    monkeypatch.setattr(F, "_safe", lambda url: None)
    monkeypatch.setattr("requests.Session", lambda: S())
    info = F.fetch_to_folder("http://scam.test/", tmp_path)
    assert info["adres_końcowy"] == "http://scam.test/lp" and info["przekierowania"] == ["http://scam.test/"] and info["obrazów"] == 1
    har = json.loads((tmp_path / "strona.har").read_text())
    assert any("cdn.kit.test" in e["request"]["url"] for e in har["log"]["entries"])
    assert "Zarabiaj" in (tmp_path / "strona.html").read_text()


def test_regroup_removes_order_dependence():
    from embsim import analyze as A
    from embsim.api import Gallery, Case
    g = Gallery(embed_fn=A.hash_embed, profile="strony")
    scam = "Prezes ujawnił sekret: wpłać 1000 zł na platformę AI i zarabiaj codziennie bez wysiłku. Zarejestruj się teraz."
    bg = ["Przepis na ciasto drożdżowe z kruszonką i śliwkami.", "Prognoza pogody na weekend: deszcz i wiatr na północy.",
          "Wyniki meczu ligi: remis po dogrywce i rzutach karnych.", "Nowy rozkład jazdy tramwajów od poniedziałku w centrum."]
    g.add(Case(id="a", text=scam, sets={"host": {"zysk-ai.xyz"}}))
    for i, t in enumerate(bg):
        g.add(Case(id=f"bg{i}", text=t, sets={"host": {f"strona{i}.pl"}}))
    g.add(Case(id="c", text=scam.replace("1000", "1500"), sets={"host": {"zysk-ai.xyz"}}))
    g.regroup()
    grp = {it["case"].id: it["group"] for it in g.items}
    assert grp["a"] == grp["c"]
    assert len({grp[f"bg{i}"] for i in range(4)} | {grp["a"]}) == 5
