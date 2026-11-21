"""Rule-based coordination signals for candidate campaigns (weights in config)."""
from __future__ import annotations

import math
from collections import Counter
from datetime import timedelta

import numpy as np

from ..process.hashing import hamming, simhash
from ..schema import Ad


def _entropy_low(values: list) -> float:
    vals = [v for v in values if v]
    if len(vals) < 2:
        return 0.0 if not vals else 1.0
    c = Counter(vals)
    p = np.array(list(c.values())) / len(vals)
    h = float(-(p * np.log(p)).sum())
    return 1.0 - h / math.log(len(vals))


def domain_components(ads: list[Ad], use_page: bool = False) -> list[int]:
    """Connected components over shared domain (optionally page_id): the infrastructure-only baseline."""
    parent = list(range(len(ads)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    owner: dict[str, int] = {}
    for i, a in enumerate(ads):
        keys = [f"d:{d}" for d in a.domains] + ([f"p:{a.page_id}"] if use_page and a.page_id else [])
        for k in keys:
            if k in owner:
                ra, rb = find(i), find(owner[k])
                if ra != rb:
                    parent[ra] = rb
            else:
                owner[k] = i
    roots: dict[int, int] = {}
    return [roots.setdefault(find(i), len(roots)) for i in range(len(ads))]


def features(ads: list[Ad], X: np.ndarray, cert: dict | None = None, cert_asof=None, sample: int = 250) -> dict:
    n = len(ads)
    rng = np.random.default_rng(1)
    idx = np.arange(n) if n <= sample else rng.choice(n, sample, replace=False)
    S = X[idx] @ X[idx].T
    iu = np.triu_indices(len(idx), 1)
    sims = [simhash(ads[i].text_norm) for i in idx]
    near = 0
    tot = max(len(iu[0]), 1)
    for a, b in zip(*iu):
        if S[a, b] > 0.95 or hamming(sims[a], sims[b]) <= 3:
            near += 1
    times = sorted(a.t for a in ads)
    best = 0
    j = 0
    for i in range(n):
        while times[i] - times[j] > timedelta(hours=24):
            j += 1
        best = max(best, i - j + 1)
    doms = sorted({d for a in ads for d in a.domains})
    page = [a.page_id for a in ads]
    dom_flat = [d for a in ads for d in a.domains[:1]]
    hits = []
    if cert:
        for d in doms:
            e = cert.get(d)
            if e and e.get("insert_date") and (cert_asof is None or e["insert_date"] <= cert_asof):
                hits.append(d)
    span = (times[-1] - times[0]).days + 1
    return {"n_ads": n, "near_dup": near / tot, "adv_entropy_low": _entropy_low(page), "domain_entropy_low": _entropy_low(dom_flat),
            "domain_novelty": min(1.0, len(doms) / 5) if n >= 2 else 0.0, "start_sync": best / n, "cert_hit": float(bool(hits)),
            "n_domains": len(doms), "n_advertisers": len({p for p in page if p}), "span_days": span, "cert_domains": hits}


def score(f: dict, weights: dict, with_cert: bool = True) -> float:
    w = dict(weights)
    if not with_cert:
        w.pop("cert_hit", None)
    z = sum(w.values()) or 1.0
    return sum(w[k] * f.get(k, 0.0) for k in w) / z


def tune_tau(ads: list[Ad], X: np.ndarray, labels: np.ndarray, cfg: dict) -> tuple[float, float]:
    """Pick tau on the dev pool: F1 of 'cluster is campaign-majority (purity >= 0.5)' vs score >= tau (cert signal excluded)."""
    m = cfg["coordination"]["min_ads"]
    sc, y = [], []
    for c, n in Counter(labels).items():
        if n < m:
            continue
        idx = np.where(labels == c)[0]
        sub = [ads[i] for i in idx]
        top = Counter(a.truth_campaign for a in sub).most_common(1)[0]
        y.append(top[0] is not None and top[1] / n >= 0.5)
        sc.append(score(features(sub, X[idx]), cfg["coordination"]["weights"], with_cert=False))
    sc, y = np.array(sc), np.array(y)
    best = (-1.0, cfg["coordination"]["tau"])
    for t in np.unique(np.round(sc, 3)):
        pred = sc >= t
        tp = (pred & y).sum()
        p_, r_ = tp / max(pred.sum(), 1), tp / max(y.sum(), 1)
        f = 2 * p_ * r_ / (p_ + r_) if p_ + r_ else 0.0
        if f > best[0]:
            best = (float(f), float(t))
    return best[1], best[0]
