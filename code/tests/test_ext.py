import hashlib
import json

import numpy as np

from embsim import ext


def fake_vectors(texts, dim=256):
    """Worek słów z haszowaniem: bez modelu, teksty o wspólnym słownictwie są bliskie."""
    V = np.zeros((len(texts), dim))
    for i, t in enumerate(texts):
        for w in t.lower().split():
            V[i, int(hashlib.md5(w.encode()).hexdigest(), 16) % dim] += 1
    return V / np.maximum(np.linalg.norm(V, axis=1, keepdims=True), 1e-9)


def make_dataset(root, n_creators=24, per=8):
    d = root / "toy"
    d.mkdir()
    lines = []
    rng = np.random.default_rng(0)
    for c in range(n_creators):
        vocab = [f"słowo{c}_{k}" for k in range(12)]
        for _ in range(per):
            lines.append(f"id\tprawda\t{' '.join(rng.choice(vocab, 9))} wspólne tło\tt\tautor{c}\tx")
    (d / "train.tsv").write_text("\n".join(lines), encoding="utf-8")
    (d / "spec.json").write_text(json.dumps({"file": "train.tsv", "sep": "\t", "header": False, "text": [2], "creator": 4,
                                             "min_per_creator": 5}))


def test_loader_split_and_creator_recovery(tmp_path, monkeypatch):
    monkeypatch.setattr(ext, "EXT", tmp_path)
    make_dataset(tmp_path)
    texts, creators = ext.load("toy", cap_creators=24, per_creator=8)
    assert len(texts) == len(creators) == 24 * 8
    assert {ext.half(c) for c in creators} == {"dev", "test"}
    assert all(ext.half(c) == ext.half(c) for c in creators)       # stabilny podział
    res = ext.evaluate(texts, creators, vectors=fake_vectors)
    assert res["test"]["AUC"] > 0.95 and res["test"]["top1"] > 0.9
    assert 0 < res["dev"]["próg"] < 1                               # próg z dev, użyty na test
    assert res["test"]["próg"] == res["dev"]["próg"]


def test_cross_link_separates_disjoint_vocab():
    a = fake_vectors([f"alfa{i} beta{i} gamma" for i in range(20)])
    b = fake_vectors([f"delta{i} epsilon{i} zeta" for i in range(20)])
    r = ext.cross_link(a, b, tau=0.5)
    assert r["odsetek_połączonych_międzyklasowo"] < 0.05
    assert r["AUC_ta_sama_klasa_vs_międzyklasowa"] > 0.9
