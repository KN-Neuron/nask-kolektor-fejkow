from fejki.demo import truth
from fejki.demo.similar import Campaign


def g(i, *m):
    return Campaign(id=i, name="", members=list(m), strength=1)


TRUTH = {"a": {"kampania": "K1", "rodzaj": "oszustwo"}, "b": {"kampania": "K1", "rodzaj": "oszustwo"},
         "c": {"kampania": "K2", "rodzaj": "oszustwo"}, "d": {"kampania": "K2", "rodzaj": "oszustwo"},
         "n": {"kampania": "neg:n", "rodzaj": "negatyw"}}


def test_perfect_grouping():
    s = truth.score([g("1", "a", "b"), g("2", "c", "d"), g("3", "n")], TRUTH, "kampania")
    assert s["precyzja"] == s["czułość"] == 1.0 and s["trafione"] == 2 == s["grup"] and s["negatywy_osobno"] == 1


def test_merged_groups_and_glued_negative_are_penalised():
    s = truth.score([g("1", "a", "b", "c", "d", "n")], TRUTH, "kampania")
    assert s["czułość"] == 1.0 and s["precyzja"] < 0.5 and s["trafione"] == 0 and s["negatywy_osobno"] == 0


def test_load_missing_file_returns_none(tmp_path):
    assert truth.load(tmp_path) is None and truth.load(None) is None
