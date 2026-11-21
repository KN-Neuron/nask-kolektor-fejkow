"""Topic probes (linear and MLP), GroupKFold by campaign."""
from __future__ import annotations

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.neural_network import MLPClassifier


def probe(X: np.ndarray, y: list[str], groups: list[str], kind: str = "linear", seed: int = 1, folds: int = 5) -> dict:
    y = np.unique(np.asarray(y), return_inverse=True)[1]  # int labels (sklearn MLP early stopping breaks on str)
    groups = np.asarray(groups)
    n_groups = len(set(groups))
    folds = max(2, min(folds, n_groups))
    accs = []
    for tr, te in GroupKFold(folds).split(X, y, groups):
        if len(set(y[tr])) < 2:
            continue
        clf = (LogisticRegression(max_iter=500) if kind == "linear"
               else MLPClassifier((128,), max_iter=300, random_state=seed, early_stopping=True))
        clf.fit(X[tr], y[tr])
        accs.append(float((clf.predict(X[te]) == y[te]).mean()))
    classes, counts = np.unique(y, return_counts=True)
    return {"acc": float(np.mean(accs)), "chance": float(counts.max() / len(y)), "uniform_chance": float(1 / len(classes))}
