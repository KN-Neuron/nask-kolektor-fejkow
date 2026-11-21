"""Faza uczenia: klasyfikator par „ta sama grupa?” zamiast ręcznych wag noisy-OR.

Cechy pary = najsilniejszy dowód w każdym kodzie dowodu (0, gdy brak) + podobieństwo tekstu. Model: regresja logistyczna
z wagami nieujemnymi (więcej dowodu nie może obniżać wyniku), więc nadal jest wyjaśnialny: wkład dowodu = współczynnik × siła.

Walidacja bez wycieku: podział po GRUPACH (leave-one-group-out). Wszystkie pary dotykające grupy testowej idą do testu,
pary w obrębie pozostałych grup i między nimi do treningu. Negatywy (kind=negatyw) to osobne grupy jednoelementowe.
Porównujemy z ręcznym noisy-OR na tych samych parach testowych (ROC AUC, average precision).
"""
from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path

import numpy as np

from .material import Material
from .similar import W, TextSpace, combine, doc_freq, evidence

CODES = sorted(set(W) | {"text", "dom", "person", "infra"})


def pair_features(ev, text_sim: float) -> np.ndarray:
    v = dict.fromkeys(CODES, 0.0)
    for e in ev:
        v[e.code] = max(v.get(e.code, 0.0), e.weight)
    return np.array([v[c] for c in CODES] + [text_sim], dtype=float)


FEATURES = CODES + ["text_sim"]


def build_pairs(materials: list[Material], group_of: dict[str, str], infra=None):
    """X (cechy), y (1 = ta sama grupa), hand (wynik ręczny), pary (a, b), grupy pary."""
    ts, df = TextSpace(materials), doc_freq(materials)
    X, y, hand, ab = [], [], [], []
    for a, b in combinations(materials, 2):
        if a.id not in group_of or b.id not in group_of:
            continue
        ev, s = evidence(a, b, ts, df, infra)
        X.append(pair_features(ev, s))
        y.append(int(group_of[a.id] == group_of[b.id]))
        hand.append(combine(ev))
        ab.append((a.id, b.id))
    return np.array(X), np.array(y), np.array(hand), ab


def fit(X: np.ndarray, y: np.ndarray, C: float = 1.0):
    from sklearn.linear_model import LogisticRegression

    m = LogisticRegression(C=C, class_weight="balanced", max_iter=2000)
    m.fit(X, y)
    m.coef_ = np.maximum(m.coef_, 0)  # monotoniczność: dowód nie może obniżać wyniku
    return m


def evaluate(materials: list[Material], group_of: dict[str, str], infra=None) -> dict:
    """Leave-one-group-out po grupach wieloelementowych; zwraca metryki modelu i ręcznego noisy-OR na parach testowych."""
    from sklearn.metrics import average_precision_score, roc_auc_score

    X, y, hand, ab = build_pairs(materials, group_of, infra)
    groups = sorted({g for g in group_of.values() if list(group_of.values()).count(g) > 1})
    pred, ref, true = np.zeros(len(y)), hand.copy(), y.copy()
    tested = np.zeros(len(y), bool)
    for g in groups:
        test = np.array([group_of[a] == g or group_of[b] == g for a, b in ab])
        if test.sum() == 0 or len(set(y[~test])) < 2:
            continue
        m = fit(X[~test], y[~test])
        pred[test] = m.predict_proba(X[test])[:, 1]
        tested |= test
    out = {"pary": int(len(y)), "pary_testowe": int(tested.sum()), "pozytywne_testowe": int(y[tested].sum())}
    if tested.sum() and len(set(true[tested])) == 2:
        out["model"] = {"roc_auc": round(roc_auc_score(true[tested], pred[tested]), 3),
                        "avg_precision": round(average_precision_score(true[tested], pred[tested]), 3)}
        out["reczne_wagi"] = {"roc_auc": round(roc_auc_score(true[tested], ref[tested]), 3),
                              "avg_precision": round(average_precision_score(true[tested], ref[tested]), 3)}
    return out


def train_and_save(materials: list[Material], group_of: dict[str, str], path: Path, infra=None) -> dict:
    X, y, _, _ = build_pairs(materials, group_of, infra)
    m = fit(X, y)
    coef = {f: round(float(c), 4) for f, c in zip(FEATURES, m.coef_[0], strict=True)}
    model = {"features": FEATURES, "coef": coef, "intercept": float(m.intercept_[0]), "n_pairs": int(len(y)),
             "n_pos": int(y.sum())}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(model, indent=1, ensure_ascii=False), encoding="utf-8")
    return model


def score_with(model: dict, ev, text_sim: float) -> float:
    """Wynik z modelu; cechy dobierane po nazwach, więc model starszy od kodu (brak nowych kanałów) nadal działa."""
    named = dict(zip(FEATURES, pair_features(ev, text_sim), strict=True))
    z = model["intercept"] + sum(model["coef"].get(f, 0.0) * named.get(f, 0.0) for f in model["features"])
    return float(1 / (1 + np.exp(-z)))
