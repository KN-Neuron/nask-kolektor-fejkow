import json

from embsim.features import load_case
from embsim.synth2 import generate


def test_deterministic_truth_and_real_like_noise(tmp_path):
    t1 = generate(tmp_path / "a", seed=5, n_operators=4, campaigns_per_op=2, variants=3, missing_rate=0.0)
    t2 = generate(tmp_path / "b", seed=5, n_operators=4, campaigns_per_op=2, variants=3, missing_rate=0.0)
    assert t1 == t2 and json.loads((tmp_path / "a" / "prawda.json").read_text()) == t1
    assert sum(v["rodzaj"] == "oszustwo" for v in t1.values()) == 24 and sum(v["rodzaj"] == "negatyw" for v in t1.values()) == 4
    cs = [load_case(tmp_path / "a" / k) for k, v in t1.items() if v["rodzaj"] == "oszustwo"]
    # kształt jak w prawdziwych przypadkach NASK: wiele prefiksów/parametrów/hostów na przypadek, nie 1-3
    assert sum(len(c.sets.get("kit", ())) >= 5 for c in cs) > len(cs) * 0.6
    assert sum(len(c.sets.get("host", ())) >= 5 for c in cs) > len(cs) * 0.6
    # wszechobecne trackery występują w prawie wszystkich zrzutach (i u operatorów, i u negatywów)
    assert sum("facebook.net" in c.sets.get("host", ()) for c in cs) > len(cs) * 0.5


def test_variants_of_one_campaign_are_not_identical_captures(tmp_path):
    t = generate(tmp_path, seed=3, n_operators=3, campaigns_per_op=1, variants=4, missing_rate=0.0)
    by = {}
    for k, v in t.items():
        if v["rodzaj"] == "oszustwo":
            by.setdefault(v["kampania"], []).append(load_case(tmp_path / k))
    for cs in by.values():
        assert len({frozenset(c.sets.get("kit", ())) for c in cs}) > 1       # różne podzbiory zasobów zestawu
