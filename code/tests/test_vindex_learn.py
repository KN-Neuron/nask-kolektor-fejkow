"""Indeks FAISS i wyuczony model par: testy na sztucznych materiałach."""
from fejki.demo.learn import resolve, score_with
from fejki.demo.material import Material
from fejki.demo.similar import Evidence
from fejki.demo.vindex import VectorIndex, blocking_keys


def _m(i, text, domain=None, scheme=None):
    return Material(id=i, label=i, source="test", text=text, landing_domains=[domain] if domain else [],
                    url_schemes=[scheme] if scheme else [])


def _set():
    return [_m("a", "szybki zysk z inwestycji w kryptowaluty gwarantowany", "x.example", "s1"),
            _m("b", "szybki zysk z inwestycji w kryptowaluty gwarantowany dziś", "x.example", "s1"),
            _m("c", "przepis na sernik z malinami i kruszonką", "y.example"),
            _m("d", "kasyno online bonus powitalny darmowe spiny", "z.example", "s9"),
            _m("e", "zdrowie suplement odchudzanie bez wysiłku", "w.example")]


def test_faiss_finds_variant_first_and_persists(tmp_path):
    ms = _set()
    vi = VectorIndex().fit(ms)
    assert vi.search(ms[0], 3)[0][0] == "b"
    assert "a" not in [i for i, _ in vi.search(ms[0], 4)]
    vi.save(tmp_path)
    back = VectorIndex.load(tmp_path)
    assert back is not None and back.ids == vi.ids and back.search(ms[0], 1)[0][0] == "b"
    assert ("a", "b") in vi.neighbours(ms, k=1)


def test_blocking_keys_include_domain_and_scheme():
    assert {"d:x.example", "sc:s1"} <= set(blocking_keys(_set()[0]))


def test_model_resolution_and_monotonic_score():
    assert resolve(False) is None
    m = {"features": ["same_scheme", "text_sim"], "coef": {"same_scheme": 3.0, "text_sim": 2.0}, "intercept": -3.0}
    assert resolve(m) is m
    weak = score_with(m, [], 0.0)
    strong = score_with(m, [Evidence(code="same_scheme", channel="adres", weight=0.6, reason="x")], 0.5)
    assert strong > weak
