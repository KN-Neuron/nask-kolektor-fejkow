"""Clustering: agglomerative (average, cosine) with dev-tuned threshold, HDBSCAN, hash components."""
from __future__ import annotations

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import pdist

from ..eval.metrics import bcubed_items, f1
from ..process.hashing import components, hash_edges

THRESHOLDS = [0.01, 0.02, 0.03, 0.05, 0.08, 0.1, 0.12, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.7]


def agglo(X: np.ndarray, threshold: float, linkage_m: str = "average") -> np.ndarray:
    if len(X) < 2:
        return np.zeros(len(X), dtype=int)
    Z = linkage(pdist(X, "cosine"), linkage_m)
    return fcluster(Z, threshold, "distance") - 1


def agglo_multi(X: np.ndarray, thresholds=THRESHOLDS, linkage_m: str = "average") -> dict[float, np.ndarray]:
    Z = linkage(pdist(X, "cosine"), linkage_m)
    return {t: fcluster(Z, t, "distance") - 1 for t in thresholds}


def hdbscan(X: np.ndarray, min_cluster_size: int = 5) -> np.ndarray:
    from sklearn.cluster import HDBSCAN

    lab = HDBSCAN(min_cluster_size=min_cluster_size, min_samples=2).fit_predict(X)
    nxt = lab.max() + 1
    out = lab.copy()
    for i in np.where(lab < 0)[0]:  # noise points become singletons
        out[i] = nxt
        nxt += 1
    return out


def hash_cluster(texts: list[str], cfg: dict) -> np.ndarray:
    h = cfg["hash"]
    edges = hash_edges(texts, h["simhash_hamming_max"], h["lsh_threshold"], h["minhash_perm"], h["shingle_char_n"])
    return np.asarray(components(len(texts), edges))


def _objective(lab: np.ndarray, truth: np.ndarray, is_camp: np.ndarray | None) -> float:
    """Dev tuning objective: F1 of overall B-cubed precision and campaign-averaged recall.

    Plain B-cubed F1 is dominated by background singletons and degenerates to 'no merging'.
    """
    P, R = bcubed_items(lab, truth)
    if is_camp is None or not is_camp.any():
        return f1(P.mean(), R.mean())
    rc = np.mean([R[truth == c].mean() for c in np.unique(truth[is_camp])])
    return f1(P.mean(), rc)


def tune_agglo(X_dev: np.ndarray, truth_dev: np.ndarray, linkage_m: str = "average", is_camp: np.ndarray | None = None) -> tuple[float, float]:
    best = (-1.0, THRESHOLDS[0])
    for t, lab in agglo_multi(X_dev, THRESHOLDS, linkage_m).items():
        s = _objective(lab, truth_dev, is_camp)
        if s > best[0]:
            best = (s, t)
    return best[1], best[0]


def tune_hdbscan(X_dev: np.ndarray, truth_dev: np.ndarray, grid=(3, 5, 10), is_camp: np.ndarray | None = None) -> tuple[int, float]:
    best = (-1.0, grid[0])
    for m in grid:
        s = _objective(hdbscan(X_dev, m), truth_dev, is_camp)
        if s > best[0]:
            best = (s, m)
    return best[1], best[0]
