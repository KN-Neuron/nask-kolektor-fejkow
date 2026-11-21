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
    if model.get("kind") == "hgb":
        return float(_estimator(model).predict_proba(pair_features(ev, text_sim).reshape(1, -1))[0, 1])
    named = dict(zip(FEATURES, pair_features(ev, text_sim), strict=True))
    z = model["intercept"] + sum(model["coef"].get(f, 0.0) * named.get(f, 0.0) for f in model["features"])
    return float(1 / (1 + np.exp(-z)))


# --- uczenie na wielu zbiorach z etykietami ---------------------------------------------------------------------------

def labelled_sets(urlscan_dir: Path | None = None, synth_dir: Path | None = None, progress=None):
    """Zbiory z prawdą: (nazwa, materiały, grupa_materiału). Pary liczymy tylko w obrębie zbioru, nigdy między zbiorami.

    - urlscan: etykieta pivotu (labels.csv); negatywy to osobne grupy jednoelementowe,
    - synteza: operator z prawda.json (poziom sieci, bo wynik pary mówi „ten sam operator lub kampania”).
    """
    import csv

    from . import store

    out = []
    if urlscan_dir and (Path(urlscan_dir) / "labels.csv").exists():
        labels = {r["case_id"]: r for r in csv.DictReader((Path(urlscan_dir) / "labels.csv").open(encoding="utf-8"))}
        idx = store.build(Path(urlscan_dir), ocr=False, progress=progress)
        group = {m.id: (labels[m.id]["label"] if labels[m.id].get("kind") != "negatyw" else f"neg:{m.id}")
                 for m in idx.materials if m.id in labels}
        out.append(("urlscan", [m for m in idx.materials if m.id in group], group))
    if synth_dir and (Path(synth_dir) / "prawda.json").exists():
        truth = json.loads((Path(synth_dir) / "prawda.json").read_text(encoding="utf-8"))
        idx = store.build(Path(synth_dir), ocr=False, progress=progress)
        group = {m.id: truth[m.id]["operator"] if truth[m.id]["rodzaj"] != "negatyw" else f"neg:{m.id}"
                 for m in idx.materials if m.id in truth}
        out.append(("synteza", [m for m in idx.materials if m.id in group], group))
    return out


def fit_hgb(X: np.ndarray, y: np.ndarray):
    """Gradient boosting z ograniczeniem monotoniczności: więcej dowodu w dowolnym kanale nigdy nie obniża wyniku."""
    from sklearn.ensemble import HistGradientBoostingClassifier

    m = HistGradientBoostingClassifier(monotonic_cst=[1] * X.shape[1], max_depth=3, learning_rate=0.1, max_iter=150,
                                       class_weight="balanced", random_state=0)
    return m.fit(X, y)


_LOADED: dict[str, object] = {}


def _estimator(model: dict):
    f = model["file"]
    if f not in _LOADED:
        import joblib

        from ..config import ROOT

        _LOADED[f] = joblib.load(ROOT / f)
    return _LOADED[f]


def train_sets(sets, path: Path) -> dict:
    """Uczy model par na wszystkich zbiorach i mierzy go walidacją leave-one-group-out (grupa testowa nigdy nie jest w treningu).
    Porównuje: ręczne noisy-OR, regresję logistyczną (zapisywana) i monotoniczny gradient boosting."""
    from sklearn.metrics import average_precision_score, roc_auc_score

    Xs, ys, hs, ds, gp = [], [], [], [], []
    counts: dict[str, int] = {}
    for name, mats, group in sets:
        X, y, hand, ab = build_pairs(mats, group)
        Xs.append(X); ys.append(y); hs.append(hand)
        ds += [name] * len(y)
        gp += [(f"{name}:{group[a]}", f"{name}:{group[b]}") for a, b in ab]
        for v in group.values():
            counts[f"{name}:{v}"] = counts.get(f"{name}:{v}", 0) + 1
    X, y, hand, ds = np.vstack(Xs), np.concatenate(ys), np.concatenate(hs), np.array(ds)
    multi = sorted(g for g, c in counts.items() if c > 1)
    makers = {"logistyczna": fit, "gradient_boosting_monotoniczny": fit_hgb}
    pred = {k: np.zeros(len(y)) for k in makers}
    tested = np.zeros(len(y), bool)
    for g in multi:
        test = np.array([a == g or b == g for a, b in gp])
        if test.sum() == 0 or len(set(y[~test])) < 2:
            continue
        for k, mk in makers.items():
            pred[k][test] = mk(X[~test], y[~test]).predict_proba(X[test])[:, 1]
        tested |= test
    metrics = {"pary": int(len(y)), "pozytywne": int(y.sum()), "grupy_wieloelementowe": len(multi),
               "zbiory": {n: len(m) for n, m, _ in sets}}

    def score(p, mask):
        return {"roc_auc": round(roc_auc_score(y[mask], p[mask]), 3), "avg_precision": round(average_precision_score(y[mask], p[mask]), 3)}

    val = {"pary_testowe": int(tested.sum())}
    for part in ["razem", *sorted(set(ds))]:
        mask = tested if part == "razem" else tested & (ds == part)
        if mask.sum() and len(set(y[mask])) == 2:
            val[part] = {"reczne_noisy_or": score(hand, mask), **{k: score(p, mask) for k, p in pred.items()}}
    metrics["walidacja_leave_one_group_out"] = val
    lr = fit(X, y)  # domyślny: logistyczna (wyjaśnialna: wkład dowodu = współczynnik × siła); boosting tylko w porównaniu
    model = {"kind": "logistyczna", "features": FEATURES, "n_pairs": int(len(y)), "n_pos": int(y.sum()),
             "intercept": float(lr.intercept_[0]), "coef": {f: round(float(c), 4) for f, c in zip(FEATURES, lr.coef_[0], strict=True)},
             "metrics": metrics}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(model, indent=1, ensure_ascii=False), encoding="utf-8")
    return model


_DEFAULT: dict[str, dict | None] = {}


def default_model() -> dict | None:
    """Model uczony przez `fejki demo train` (artifacts/demo/pair_model.json); None, gdy nie został wytrenowany."""
    from ..config import ROOT

    if "m" not in _DEFAULT:
        f = ROOT / "artifacts" / "demo" / "pair_model.json"
        _DEFAULT["m"] = json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
    return _DEFAULT["m"]


def resolve(model):
    """None → model domyślny (jeśli jest), False → ręczne wagi noisy-OR, słownik → ten model."""
    if model is False:
        return None
    return default_model() if model is None else model
