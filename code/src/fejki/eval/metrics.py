"""B-cubed, ARI/NMI, cross-topic pair metrics, bootstrap over campaigns."""
from __future__ import annotations

import warnings

import numpy as np
from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score

warnings.filterwarnings("ignore", message="The number of unique classes", category=UserWarning)


def bcubed(pred: dict, truth: dict):
    from collections import defaultdict

    ids = list(pred.keys())
    by_pred, by_truth = defaultdict(set), defaultdict(set)
    for i in ids:
        by_pred[pred[i]].add(i)
        by_truth[truth[i]].add(i)
    P = R = 0.0
    for i in ids:
        cp, ct = by_pred[pred[i]], by_truth[truth[i]]
        inter = len(cp & ct)
        P += inter / len(cp)
        R += inter / len(ct)
    P /= len(ids)
    R /= len(ids)
    return P, R, (2 * P * R / (P + R) if P + R else 0.0)


def bcubed_items(pred: np.ndarray, truth: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per-item B-cubed precision and recall (vectorized via contingency counts)."""
    n = len(pred)
    _, p = np.unique(pred, return_inverse=True)
    _, t = np.unique(truth, return_inverse=True)
    cp = np.bincount(p)
    ct = np.bincount(t)
    joint = {}
    for a, b in zip(p, t):
        joint[(a, b)] = joint.get((a, b), 0) + 1
    inter = np.array([joint[(a, b)] for a, b in zip(p, t)], dtype=float)
    return inter / cp[p], inter / ct[t]


def f1(P: float, R: float) -> float:
    return 2 * P * R / (P + R) if P + R else 0.0


def bcubed_ci(pred, truth, groups, n_boot: int = 1000, seed: int = 1, weights=None) -> dict:
    """Bootstrap over campaigns: resample groups (campaigns; non-campaign ads are singleton groups)."""
    pred, truth, groups = np.asarray(pred), np.asarray(truth), np.asarray(groups)
    Pi, Ri = bcubed_items(pred, truth)
    P0, R0 = Pi.mean(), Ri.mean()
    ug, inv = np.unique(groups, return_inverse=True)
    sums_P = np.bincount(inv, Pi)
    sums_R = np.bincount(inv, Ri)
    cnt = np.bincount(inv).astype(float)
    rng = np.random.default_rng(seed)
    Ps, Rs, Fs = [], [], []
    for _ in range(n_boot):
        s = rng.integers(0, len(ug), len(ug))
        c = cnt[s].sum()
        P, R = sums_P[s].sum() / c, sums_R[s].sum() / c
        Ps.append(P)
        Rs.append(R)
        Fs.append(f1(P, R))
    q = lambda a: (float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5)))
    return {"P": float(P0), "R": float(R0), "F1": f1(P0, R0), "P_ci": q(Ps), "R_ci": q(Rs), "F1_ci": q(Fs)}


def campaign_weighted(pred, truth, is_campaign) -> dict:
    """B-cubed over campaign ads only, with each campaign weighted equally."""
    pred, truth, is_c = np.asarray(pred), np.asarray(truth), np.asarray(is_campaign, bool)
    Pi, Ri = bcubed_items(pred, truth)
    out_P, out_R = [], []
    for c in np.unique(truth[is_c]):
        m = truth == c
        out_P.append(Pi[m].mean())
        out_R.append(Ri[m].mean())
    P, R = float(np.mean(out_P)), float(np.mean(out_R))
    return {"cP": P, "cR": R, "cF1": f1(P, R)}


def cross_topic(pred, camp, topic) -> dict:
    """Template recall across topics and topic separation across campaigns.

    recall_x: same campaign, different topic -> same cluster.
    sep_x: different campaign (or no campaign), same topic -> different cluster.
    """
    pred = np.asarray(pred)
    camp = np.asarray(camp, dtype=object)
    topic = np.asarray(topic, dtype=object)
    same_cl = pred[:, None] == pred[None, :]
    has_c = np.array([c is not None for c in camp])
    same_c = (camp[:, None] == camp[None, :]) & has_c[:, None] & has_c[None, :]
    same_t = topic[:, None] == topic[None, :]
    iu = np.triu(np.ones_like(same_cl, dtype=bool), 1)
    pos = same_c & ~same_t & iu
    neg = ~same_c & same_t & iu
    return {"recall_x": float(same_cl[pos].mean()) if pos.any() else float("nan"),
            "sep_x": float((~same_cl[neg]).mean()) if neg.any() else float("nan")}


def aux(pred, truth) -> dict:
    return {"ARI": float(adjusted_rand_score(truth, pred)), "NMI": float(normalized_mutual_info_score(truth, pred))}


def cross_topic_recall_ci(pred, camp, topic, n_boot: int = 1000, seed: int = 1) -> tuple[float, float, float]:
    """Cross-topic template recall with a bootstrap over campaigns (pairs are grouped by campaign)."""
    pred = np.asarray(pred)
    camp = np.asarray(camp, dtype=object)
    topic = np.asarray(topic, dtype=object)
    hits, tots = [], []
    for c in sorted({c for c in camp if c is not None}):
        idx = np.where(camp == c)[0]
        sc = pred[idx][:, None] == pred[idx][None, :]
        dt = topic[idx][:, None] != topic[idx][None, :]
        m = np.triu(dt, 1)
        hits.append(float(sc[m].sum()))
        tots.append(float(m.sum()))
    hits, tots = np.array(hits), np.array(tots)
    if not len(hits) or tots.sum() == 0:
        return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    bs = []
    for _ in range(n_boot):
        s = rng.integers(0, len(hits), len(hits))
        bs.append(hits[s].sum() / max(tots[s].sum(), 1))
    return float(hits.sum() / tots.sum()), float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))
