"""Burst per region: Poisson tail against a trailing 14-day baseline (regions from the erased space)."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import poisson
from sklearn.cluster import KMeans


def fit_regions(X_ref: np.ndarray, k: int, seed: int = 1) -> KMeans:
    return KMeans(n_clusters=min(k, len(X_ref)), n_init=5, random_state=seed).fit(X_ref)


def daily_counts(times: list, regions: np.ndarray) -> pd.DataFrame:
    df = pd.DataFrame({"day": [t.date() for t in times], "region": regions})
    c = df.groupby(["region", "day"]).size().rename("count").reset_index()
    full = pd.date_range(df.day.min(), df.day.max()).date
    idx = pd.MultiIndex.from_product([sorted(df.region.unique()), full], names=["region", "day"])
    return c.set_index(["region", "day"]).reindex(idx, fill_value=0).reset_index()


def detect(counts: pd.DataFrame, baseline_days: int = 14, p_threshold: float = 1e-3, min_mu: float = 0.5) -> pd.DataFrame:
    out = []
    for r, g in counts.groupby("region"):
        g = g.sort_values("day").copy()
        c = g["count"].to_numpy()
        mu = np.array([c[max(0, t - baseline_days) : t].mean() if t > 0 else np.nan for t in range(len(c))])
        mu = np.where(np.isnan(mu), np.nan, np.maximum(mu, min_mu))
        p = np.where(np.isnan(mu), 1.0, poisson.sf(c - 1, np.nan_to_num(mu, nan=1.0)))
        g["mu"], g["p"], g["burst"] = mu, p, p < p_threshold
        out.append(g)
    return pd.concat(out, ignore_index=True)
