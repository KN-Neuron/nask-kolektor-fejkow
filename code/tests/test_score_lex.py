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
