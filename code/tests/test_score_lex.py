import numpy as np

from embsim.features import Case
from embsim.score import LEX_WEIGHTS, Corpus


def cases():
    return [Case("a", "Rafał Brzoska postrzelony. Wpłać 1000 zł i obserwuj zysk już dziś. Zostało tylko 12 miejsc."),
            Case("b", "Rafał Brzoska postrzelony. Przelej 1000 zł i obserwuj zysk już dziś. Zostało tylko 7 miejsc."),
            Case("c", "Ogłoszenie o otwarciu wystawy sztuki nowoczesnej w galerii miejskiej w sobotę o godzinie 18."),
            Case("d", "")]


def test_lexical_channel_similar_vs_unrelated_and_missing_text():
    cs = cases()
    c = Corpus(cs, None, {k: (1.0 if k == "text_lex" else 0.0) for k in LEX_WEIGHTS})
    ab, ac = c.score(cs[0], cs[1]), c.score(cs[0], cs[2])
    assert ab.channels["text_lex"] > 0.5 > ac.channels["text_lex"]
    assert c.score(cs[0], cs[3]).channels == {}            # brak tekstu = kanał milczy, nie „zero podobieństwa”
    assert c.availability(cs[0], cs[3]) == 0 and c.availability(cs[0], cs[1]) == 1.0


def test_no_lexical_weight_means_no_tfidf():
    c = Corpus(cases(), None)
    assert c.lex is None and "text_lex" not in c.score(c.cases[0], c.cases[1]).channels


def test_embed_fix_removes_common_direction_and_applies_to_new_items():
    rng = np.random.default_rng(1)
    common = rng.normal(size=32) * 3.0                      # wspólna składowa wszystkich wektorów (anizotropia)
    base = [rng.normal(size=32) for _ in range(30)]
    cs = [Case(f"c{i}", f"tekst numer {i}", vec=(common + b) / np.linalg.norm(common + b)) for i, b in enumerate(base)]
    raw = Corpus([Case(c.id, c.text, vec=c.vec) for c in cs], None, {"text": 1.0}, embed_fix="none")
    fix = Corpus(cs, None, {"text": 1.0}, embed_fix="abtt1")
    cos = lambda a, b: float(a.vec @ b.vec)
    assert cos(cs[0], cs[1]) > 0.8                           # surowe: wszystko podobne do wszystkiego
    assert all(abs(np.linalg.norm(c.vec_t) - 1) < 1e-4 for c in cs)
    assert float(cs[0].vec_t @ cs[1].vec_t) < cos(cs[0], cs[1]) - 0.5   # po korekcie: różnicuje
    q = Case("q", "nowy", vec=cs[0].vec.copy())
    fix.prepare(q)
    assert float(q.vec_t @ cs[0].vec_t) > 0.999             # ten sam wektor -> ta sama korekta (średnia i składowa zapamiętane)
    assert raw.cases[0].vec_t is None                        # bez korekty nic się nie zmienia


def test_identical_texts_do_not_divide_by_zero():
    """Regresja: gdy większość materiałów ma identyczny tekst, mediana kosinusów = 1 i normalizacja (cos − μ)/(1 − μ) dzieliła przez zero."""
    v = np.ones(16, dtype=np.float32) / 4.0
    cs = [Case(f"c{i}", "ten sam tekst reklamy powtórzony wiele razy", vec=v.copy()) for i in range(8)]
    c = Corpus(cs, None, {"text": 1.0, "text_lex": 1.0})
    s = c.score(cs[0], cs[1])
    assert 0.0 <= s.value <= 1.0 and np.isfinite(s.value) and c.mu < 1.0 and c.mu_lex < 1.0


def _traces_corpus(n_hub_users=12, **kw):
    from embsim.features import Case as C

    cs = []
    for i in range(20):
        sets = {"kit": {"/static", f"/uniq{i}"} if i < n_hub_users else {f"/uniq{i}"}, "scheme": {"utm_a"} if i < 3 else {f"s{i}"}}
        cs.append(C(f"c{i}", "", sets))
    return cs, Corpus(cs, None, {"kit": 1.0, "scheme": 1.0}, trace_mode="overlap", **kw)


def test_hub_trace_is_ignored_but_campaign_trace_in_small_group_is_kept():
    cs, plain = _traces_corpus()
    _, capped = _traces_corpus(hub_frac=0.4)                  # /static w 12 z 20 materiałów (60%) = hub
    a, b = cs[0], cs[1]                                       # wspólne: pospolite /static i rzadkie utm_a (3 materiały)
    assert "kit" in plain.score(a, b).channels and "kit" not in capped.score(a, b).channels     # /static zignorowany
    assert "scheme" in capped.score(a, b).channels                                               # utm_a (3 < hub_min) zostaje
    assert "/static" in capped.hubs["kit"] and "utm_a" not in capped.hubs["scheme"]
    x, y = cs[15], cs[16]                                     # materiały bez wspólnego śladu
    assert capped.score(x, y).value == 0.0
    # materiał z samymi hubami nie ma danych w kanale (brak dowodu), a nie „zerowe podobieństwo”
    only_hub = Case("h", "", {"kit": {"/static"}})
    assert capped.availability(only_hub, cs[0]) < plain.availability(only_hub, cs[0])


def test_hub_min_protects_small_galleries():
    cs, c = _traces_corpus(hub_frac=0.01)                     # bardzo niski ułamek, ale df < hub_min nie jest hubem
    assert c.hubs["scheme"] == set() and "/static" in c.hubs["kit"]
