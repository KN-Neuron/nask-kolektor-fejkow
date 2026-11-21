"""Chronological replay in daily ticks: windowed clustering, burst gate, coordination score, detection time."""
from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd

from ..analyze.bursts import daily_counts, detect, fit_regions
from ..analyze.cluster import agglo
from ..analyze.coordination import features, score


def _utc(d) -> datetime:
    return d if getattr(d, "tzinfo", None) else d.replace(tzinfo=UTC)


def replay(ads, X, thr: float, cfg: dict, cert: dict | None = None, start=None, end=None, window_days: int = 14, step: int = 1):
    order = np.argsort([a.t for a in ads])
    times = [ads[i].t for i in order]
    start = start or times[0]
    end = end or times[-1]
    bc = cfg["bursts"]
    ref = [i for i in order if ads[i].t <= start + timedelta(days=bc["reference_days"])]
    km = fit_regions(X[ref], bc["n_regions"], cfg["seed"])
    reg = km.predict(X)
    cnt = daily_counts([ads[i].t for i in range(len(ads))], reg[[i for i in range(len(ads))]])
    bursts = detect(cnt, bc["baseline_days"], bc["p_threshold"])
    flagged = {(r, d) for r, d, b in zip(bursts.region, bursts.day, bursts.burst) if b}
    w, tau, min_ads = cfg["coordination"]["weights"], cfg["coordination"]["tau"], cfg["coordination"]["min_ads"]
    tracks: list[dict] = []
    tick = _utc(start).replace(hour=0, minute=0, second=0, microsecond=0)
    log = []
    while tick <= end:
        tick_end = tick + timedelta(days=1)
        idx = np.array([i for i in order if tick_end - timedelta(days=window_days) < ads[i].t <= tick_end])
        if len(idx) >= min_ads:
            lab = agglo(X[idx], thr, cfg["cluster"]["agglo_linkage"])
            for c, n in Counter(lab).items():
                if n < min_ads:
                    continue
                members = idx[lab == c]
                dom_reg = Counter(reg[members]).most_common(1)[0][0]
                recent = [(dom_reg, (tick - timedelta(days=k)).date()) for k in range(3)]
                if not any(r in flagged for r in recent):
                    continue
                f = features([ads[i] for i in members], X[members], cert, cert_asof=tick_end)
                s = score(f, w, with_cert=False)
                if s < tau:
                    continue
                ms = set(members.tolist())
                for tr in tracks:
                    if len(ms & tr["members"]) / len(ms | tr["members"]) >= 0.3:
                        tr["members"] |= ms
                        tr["last"] = tick
                        tr["score"] = max(tr["score"], s)
                        break
                else:
                    tracks.append({"id": f"K{len(tracks):03d}", "detect_time": tick_end, "last": tick, "members": ms, "score": s, "region": int(dom_reg)})
        log.append({"tick": tick.date(), "n_window": len(idx), "n_tracks": len(tracks)})
        tick += timedelta(days=step)
    return tracks, pd.DataFrame(log), bursts, reg


def lead_times(tracks, ads, cert: dict, simulated: bool) -> pd.DataFrame:
    """lead_days = cert_insert_date - detection_time (positive: detected earlier than CERT)."""
    det: dict[str, datetime] = {}
    for tr in tracks:
        truths = Counter(ads[i].truth_campaign for i in tr["members"] if ads[i].truth_campaign)
        if not truths:
            continue
        camp, n = truths.most_common(1)[0]
        if n / len(tr["members"]) >= 0.5:
            det[camp] = min(det.get(camp, tr["detect_time"]), tr["detect_time"])
    rows = []
    for camp, t in det.items():
        doms = {d for a in ads if a.truth_campaign == camp for d in a.domains}
        for d in sorted(doms):
            e = cert.get(d)
            if e and e.get("insert_date"):
                rows.append({"campaign": camp, "domain": d, "detection_time": t, "cert_insert": e["insert_date"],
                             "lead_days": (_utc(e["insert_date"]) - _utc(t)).total_seconds() / 86400, "simulated": simulated})
    return pd.DataFrame(rows)
