"""Wektory przypadków i podobieństwo kosinusowe. Cała „logika” to średnia i iloczyn skalarny."""
from __future__ import annotations

import numpy as np

from .embed import Embedder
from .material import Material

CHANNELS = ("image", "text", "both")


def _unit(v: np.ndarray) -> np.ndarray:
    return v / max(float(np.linalg.norm(v)), 1e-12)


def case_vectors(emb: Embedder, m: Material) -> dict[str, np.ndarray | None]:
    """Średnia wektorów obrazów, średnia wektorów tekstów i ich średnia (`both`). Brak kanału = None."""
    img = _unit(emb.images(m.images).mean(0)) if m.images else None
    txt = _unit(emb.texts(m.texts).mean(0)) if m.texts else None
    parts = [v for v in (img, txt) if v is not None]
    return {"image": img, "text": txt, "both": _unit(np.mean(parts, 0)) if parts else None}


def sim_matrix(vecs: list[np.ndarray | None]) -> np.ndarray:
    """Macierz kosinusów; NaN tam, gdzie któryś przypadek nie ma tego kanału."""
    n = len(vecs)
    S = np.full((n, n), np.nan, np.float32)
    for i in range(n):
        for j in range(n):
            if vecs[i] is not None and vecs[j] is not None:
                S[i, j] = float(vecs[i] @ vecs[j])
    return S


def clusters(S: np.ndarray, threshold: float) -> list[list[int]]:
    """Składowe spójne grafu „kosinus >= próg” (single-linkage)."""
    n, parent = len(S), list(range(len(S)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for i in range(n):
        for j in range(i + 1, n):
            if S[i, j] >= threshold:
                parent[find(i)] = find(j)
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())
