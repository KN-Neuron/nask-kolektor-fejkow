import numpy as np

from fejki.eval.metrics import bcubed, bcubed_ci, bcubed_items, cross_topic


def test_bcubed_perfect_and_edge_cases():
    t = {"a": 1, "b": 1, "c": 2}
    assert bcubed(t, t) == (1.0, 1.0, 1.0)
    P, R, F = bcubed({"a": 0, "b": 0, "c": 0}, t)  # everything merged
    assert abs(R - 1.0) < 1e-9
    assert abs(P - (2 / 3 + 2 / 3 + 1 / 3) / 3) < 1e-9
    P, R, F = bcubed({"a": 0, "b": 1, "c": 2}, t)  # everything split
    assert P == 1.0 and abs(R - (0.5 + 0.5 + 1) / 3) < 1e-9


def test_vectorized_matches_reference():
    rng = np.random.default_rng(0)
    pred, truth = rng.integers(0, 5, 60), rng.integers(0, 4, 60)
    P, R, _ = bcubed({i: int(p) for i, p in enumerate(pred)}, {i: int(t) for i, t in enumerate(truth)})
    Pi, Ri = bcubed_items(pred, truth)
    assert abs(Pi.mean() - P) < 1e-9 and abs(Ri.mean() - R) < 1e-9


def test_bootstrap_ci_contains_point_and_is_deterministic():
    pred = np.array([0, 0, 1, 1, 2, 2, 3, 3])
    truth = np.array(["a", "a", "a", "b", "b", "c", "c", "c"], dtype=object)
    r1 = bcubed_ci(pred, truth, truth, n_boot=200, seed=3)
    r2 = bcubed_ci(pred, truth, truth, n_boot=200, seed=3)
    assert r1 == r2 and r1["F1_ci"][0] <= r1["F1"] <= r1["F1_ci"][1] + 1e-9


def test_cross_topic():
    pred = [0, 0, 1, 1]
    camp = ["c", "c", None, None]
    topic = ["x", "y", "x", "x"]
    r = cross_topic(pred, camp, topic)
    assert r["recall_x"] == 1.0
