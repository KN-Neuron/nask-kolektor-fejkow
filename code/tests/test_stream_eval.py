import numpy as np

from embsim.features import Case
from embsim.stream_eval import (CONTENT, Retriever, cluster_bootstrap, metrics, pick_threshold, run_queries, slices, split_chronological)


def test_chronological_split_is_disjoint_ordered_and_complete():
    g, v, t = split_chronological(101)
    assert list(g) + list(v) + list(t) == list(range(101))
    assert len(g) == 50 and len(v) == 20 and len(t) == 31 and max(g) < min(v) and max(v) < min(t)


def rows_toy():
    # znani: trafieni z wysokim wynikiem; nowi: niski wynik
    kn = [{"page": "a", "best_page": "a", "score": 0.9, "known": True, "has_text": True, "dup": False, "n_cand": 5} for _ in range(20)]
    kn += [{"page": "b", "best_page": "c", "score": 0.4, "known": True, "has_text": True, "dup": False, "n_cand": 5} for _ in range(5)]
    nw = [{"page": f"n{i}", "best_page": "a", "score": 0.2, "known": False, "has_text": True, "dup": True, "n_cand": 5} for i in range(15)]
    return kn + nw


def test_threshold_separates_and_metrics_are_consistent():
    rows = rows_toy()
    t = pick_threshold(rows)
    assert 0.2 < t <= 0.9
    m = metrics(rows, t)
    assert m["top1_znani"] == 20 / 25 and m["przypięcie_znani"] == 20 / 25 and m["odrzucenie_nowych"] == 1.0
    assert m["AUROC_znany_vs_nowy"] > 0.9
    assert pick_threshold([r for r in rows if r["known"]]) == 0.5               # brak nowych: bezpieczny próg domyślny


def test_slices_and_cluster_bootstrap_brackets_point_estimate():
    rows = rows_toy()
    assert len(slices(rows)["z treścią, tekst nowy (bez identycznego w galerii)"]) == 25   # nowi mają dup=True
    t = 0.5
    ci = cluster_bootstrap(rows, t, ("top1_znani",), n=200)
    lo, hi = ci["top1_znani"]
    assert lo <= metrics(rows, t)["top1_znani"] <= hi + 1e-9


def test_retriever_finds_exact_key_match_and_known_creator_attaches():
    mk = lambda i, page, text, host=None, tg="t": Case(f"c{i}", text, {**({"host": {host}} if host else {}), "targeting": {tg}},
                                                       meta={"page_id": page})
    gal = [mk(0, "A", "kup teraz suplement na stawy promocja tylko dziś", "sklep-a.pl"),
           mk(1, "B", "wystawa sztuki nowoczesnej w galerii miejskiej w sobotę", "galeria.pl"),
           mk(2, "C", "pożyczka bez bik decyzja w kilka minut", "kredyt.pl")]
    ret = Retriever(gal, {"text_lex": 1.0, "host": 1.0, "targeting": 1.0})
    q = mk(9, "A", "zupełnie inny tekst", "sklep-a.pl", "inne")                        # tylko host zgodny
    assert 0 in ret.candidates(ret.corpus.prepare(q))
    rows = run_queries(gal, [mk(8, "A", "kup teraz suplement na stawy promocja tylko dzisiaj", "sklep-a.pl"),
                             mk(7, "Z", "pizza z piecem opalanym najlepsza w mieście zamów teraz", "pizza.pl")], {"text_lex": 1.0, "host": 1.0})
    assert rows[0]["known"] and rows[0]["best_page"] == "A" and not rows[1]["known"] and rows[0]["score"] > rows[1]["score"]
