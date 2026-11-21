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
