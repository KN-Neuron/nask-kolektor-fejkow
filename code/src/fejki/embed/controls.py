"""Random-direction controls with the same removed rank as LEACE (E4 random_k1, E5 random_pca)."""
from __future__ import annotations

import numpy as np

from .encoder import l2


def _project_out(X: np.ndarray, Q: np.ndarray) -> np.ndarray:
    return l2(X - (X @ Q) @ Q.T)


def random_k1(X: np.ndarray, rank: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    Q, _ = np.linalg.qr(rng.standard_normal((X.shape[1], max(rank, 1))))
    return _project_out(X, Q)


def random_pca(X: np.ndarray, rank: int, seed: int, pool: int = 50) -> np.ndarray:
    rng = np.random.default_rng(seed)
    Xc = X - X.mean(0)
    _, _, Vt = np.linalg.svd(Xc, full_matrices=False)
    m = min(max(pool, 2 * rank), Vt.shape[0])
    B = Vt[:m].T  # (d, m) orthonormal basis of the top PCA subspace
    C, _ = np.linalg.qr(rng.standard_normal((m, max(rank, 1))))
    return _project_out(X, B @ C)
