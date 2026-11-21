"""Frozen encoders. `char-tfidf` is a deterministic offline fallback (no download)."""
from __future__ import annotations

import hashlib

import numpy as np

from ..config import path, pick_device


def l2(x: np.ndarray) -> np.ndarray:
    return x / np.maximum(np.linalg.norm(x, axis=1, keepdims=True), 1e-12)


def encode_tfidf(texts: list[str], dim: int = 192, seed: int = 1) -> np.ndarray:
    from sklearn.decomposition import TruncatedSVD
    from sklearn.feature_extraction.text import TfidfVectorizer

    X = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2, sublinear_tf=True).fit_transform(texts)
    d = min(dim, X.shape[1] - 1)
    return l2(TruncatedSVD(d, random_state=seed).fit_transform(X).astype(np.float32))


def encode_st(texts: list[str], name: str, max_length: int, batch_size: int, prefix: str, device: str) -> np.ndarray:
    from sentence_transformers import SentenceTransformer

    m = SentenceTransformer(name, device=pick_device(device))
    m.max_seq_length = max_length
    e = m.encode([prefix + t for t in texts], batch_size=batch_size, normalize_embeddings=True, show_progress_bar=False)
    return np.asarray(e, dtype=np.float32)


def embed_texts(texts: list[str], cfg: dict, cache_key: str = "") -> np.ndarray:
    ec = cfg["encoder"]
    name = ec["name"]
    h = hashlib.sha1(("\n".join(texts) + name + cache_key).encode()).hexdigest()[:16]
    slug = name.replace("/", "_")
    f = path(f"data/emb/{slug}/{h}.npy")
    if f.exists():
        return np.load(f)
    if name == "char-tfidf":
        emb = encode_tfidf(texts, seed=cfg.get("seed", 1))
    else:
        emb = encode_st(texts, name, ec.get("max_length", 256), ec.get("batch_size", 64), ec.get("prefix", ""), cfg.get("device", "auto"))
    np.save(f, emb)
    return emb
