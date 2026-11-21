"""Metryki oceny: pary, grupowanie, przypisanie nowego materiału (z otwartym zbiorem), błędne łączenie.

Wszystkie funkcje biorą macierz wyników S (n×n, symetryczna, wyższy = bardziej podobne) i etykiety grup (lista długości n).
Etykieta `None` oznacza materiał bez grupy (negatyw, solo): nigdy nie jest pozytywem w parze.
"""
from __future__ import annotations

import warnings
from collections import Counter, defaultdict

import numpy as np
from sklearn.metrics import adjusted_rand_score, average_precision_score, normalized_mutual_info_score, roc_auc_score

# sklearn ostrzega, gdy etykiet jest >50% liczby próbek (u nas: wielu twórców z jednym tekstem), co jest zamierzone
warnings.filterwarnings("ignore", message=".*unique classes is greater.*")


def _unique_labels(labels: list) -> list:
    """None -> unikalna etykieta (solo), żeby miary grupowania traktowały to jako jednoelementową grupę."""
    return [l if l is not None else f"__solo{i}" for i, l in enumerate(labels)]


def pair_labels(labels: list) -> np.ndarray:
    l = np.array([x if x is not None else f"__solo{i}" for i, x in enumerate(labels)], dtype=object)
    return l[:, None] == l[None, :]


def pairwise(S: np.ndarray, labels: list) -> dict:
    """AUC, AP i precyzja przy zadanej czułości po wszystkich parach i<j."""
    iu = np.triu_indices(len(S), 1)
    y = pair_labels(labels)[iu]
    s = S[iu]
    if y.sum() == 0 or y.sum() == len(y):
        return {"AUC": float("nan"), "AP": float("nan"), "n_poz": int(y.sum())}
    o = np.argsort(-s)
    tp = np.cumsum(y[o])
    prec = tp / np.arange(1, len(o) + 1)
    rec = tp / y.sum()
    out = {"AUC": float(roc_auc_score(y, s)), "AP": float(average_precision_score(y, s)), "n_poz": int(y.sum())}
    for r in (0.5, 0.9):
        ok = rec >= r
        out[f"P@R{int(r * 100)}"] = float(prec[ok].max()) if ok.any() else 0.0
    return out


def bcubed(pred: np.ndarray, truth: list) -> dict:
    truth = _unique_labels(truth)
    n = len(pred)
    P = R = 0.0
    by_pred, by_truth = defaultdict(set), defaultdict(set)
    for i in range(n):
        by_pred[pred[i]].add(i); by_truth[truth[i]].add(i)
    for i in range(n):
        cp, ct = by_pred[pred[i]], by_truth[truth[i]]
        inter = len(cp & ct)
        P += inter / len(cp); R += inter / len(ct)
    P, R = P / n, R / n
    return {"B3_P": P, "B3_R": R, "B3_F": 2 * P * R / (P + R) if P + R else 0.0}


def cluster_at(S: np.ndarray, threshold: float) -> np.ndarray:
    """Grupowanie hierarchiczne ze średnim łączeniem, cięcie przy wyniku S >= próg."""
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import squareform

    if len(S) < 2:
        return np.ones(len(S), int)
    Z = linkage(squareform(1 - S, checks=False), method="average")
    return fcluster(Z, 1 - threshold, criterion="distance")


def clustering(S: np.ndarray, labels: list, threshold: float) -> dict:
    pred = cluster_at(S, threshold)
    t = _unique_labels(labels)
    return {"ARI": float(adjusted_rand_score(t, pred)), "NMI": float(normalized_mutual_info_score(t, pred)),
            "grup": int(len(set(pred))), **{k: float(v) for k, v in bcubed(pred, labels).items()}}


def assignment(S: np.ndarray, labels: list, threshold: float) -> dict:
    """Nowy materiał względem znanych grup (każda grupa = jej pozostałe materiały).

    - top1: czy najbliższa grupa (po maksimum wyniku do jej członków) jest właściwa; tylko dla materiałów z ≥1 towarzyszem;
    - znany vs nowy (AUROC): wynik najbliższego sąsiada dla materiałów ze znaną grupą (leave-one-out) kontra materiałów z grupą
      całkowicie wstrzymaną (cała grupa usunięta z galerii) = zdolność odróżnienia „nowego wzorca”;
    - przy progu: przypisano_poprawnie (czułość) i błędnie_połączone (odsetek materiałów z wstrzymaną grupą i negatywów, które
      mimo to przekroczyły próg).
    """
    n = len(S)
    lab = np.array(_unique_labels(labels), dtype=object)
    cnt = Counter(lab)
    S = S.copy(); np.fill_diagonal(S, -np.inf)
    known_max, new_max, top1_ok, top1_n, assigned_ok = [], [], 0, 0, 0
    for i in range(n):
        if cnt[lab[i]] >= 2:
            row = S[i].copy()                       # leave-one-out: i zostaje poza galerią, jego grupa ma jeszcze członków
            j = int(np.argmax(row))
            known_max.append(row[j])
            top1_n += 1
            top1_ok += lab[j] == lab[i]
            assigned_ok += (row[j] >= threshold) and (lab[j] == lab[i])
            row2 = S[i].copy(); row2[lab == lab[i]] = -np.inf   # cała grupa wstrzymana: materiał to „nowy wzorzec”
            if np.isfinite(row2).any():
                new_max.append(row2.max())
        else:
            row = S[i]
            if np.isfinite(row).any():
                new_max.append(row.max())
    out = {"top1": top1_ok / top1_n if top1_n else float("nan"), "n_znanych": top1_n, "n_nowych": len(new_max)}
    if known_max and new_max:
        y = np.r_[np.ones(len(known_max)), np.zeros(len(new_max))]
        out["znany_vs_nowy_AUC"] = float(roc_auc_score(y, np.r_[known_max, new_max]))
        out["przypisano_poprawnie"] = assigned_ok / top1_n
        out["błędnie_połączone"] = float(np.mean(np.array(new_max) >= threshold))
    return out


def evaluate_level(S: np.ndarray, labels: list, threshold: float) -> dict:
    return {**pairwise(S, labels), **clustering(S, labels, threshold), **assignment(S, labels, threshold)}
