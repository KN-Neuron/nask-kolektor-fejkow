import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "graph"))
from subjects import assign_folds, audit, components, hubs  # noqa: E402

IDS = ["a1", "a2", "a3", "a4", "a5", "solo"]
EDGES = [("a1", "PAID_BY:P"), ("a2", "PAID_BY:P"), ("a2", "LINKS_TO:d.pl"), ("a3", "LINKS_TO:d.pl"),
         ("a4", "BY:X"), ("a5", "BY:X")]


def test_components_transitive_and_solo():
    sub = components(IDS, EDGES, hub_cap=None)
    assert sub["a1"] == sub["a2"] == sub["a3"]       # przez płatnika i domenę
    assert sub["a4"] == sub["a5"] != sub["a1"]
    assert len({sub[i] for i in IDS}) == 3 and sub["solo"] not in (sub["a1"], sub["a4"])


def test_hub_does_not_glue():
    edges = EDGES + [(f"h{i}", "LINKS_TO:youtube.com") for i in range(5)] + [("a1", "LINKS_TO:youtube.com")]
    ids = IDS + [f"h{i}" for i in range(5)]
    assert "LINKS_TO:youtube.com" in hubs(edges, 3)
    glued = components(ids, edges, hub_cap=None)
    cut = components(ids, edges, hub_cap=3)
    assert glued["a1"] == glued["h0"] and cut["a1"] != cut["h0"]


def test_split_keeps_subjects_whole_and_audit_clean():
    sub = components(IDS, EDGES, hub_cap=None)
    fold_sub = assign_folds(sub, seed=3)
    fold_of = {i: fold_sub[sub[i]] for i in IDS}
    assert len({fold_of[i] for i in ("a1", "a2", "a3")}) == 1
    assert audit(fold_of, EDGES, None)["leaks"] == []


def test_audit_detects_leak():
    bad = {"a1": "train", "a2": "test", "a3": "train", "a4": "val", "a5": "val", "solo": "val"}
    assert "PAID_BY:P" in audit(bad, EDGES, None)["leaks"]
