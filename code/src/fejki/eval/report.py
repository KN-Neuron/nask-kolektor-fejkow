"""E6 (operational value) and E7 (complexity ablation), plus the final Markdown report."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..analyze.cards import build_cards
from ..analyze.cluster import agglo, tune_agglo
from ..analyze.coordination import tune_tau
from ..analyze.graph import build_graph, communities, export
from ..analyze.replay import lead_times, replay
from ..config import ROOT
from ..ingest.cert import load_cert_file
from .experiments import ART, Ctx, _save, eval_labels, pool


def load_cert(ctx: Ctx, fixtures: str = "data/fixtures") -> tuple[dict, bool]:
    from ..config import path
    from ..db import connect
    from ..ingest.cert import load_cert_db

    try:
        con = connect(path(ctx.cfg.get("db_path", "data/db.duckdb")))
        d = load_cert_db(con)
        con.close()
        if d:
            return d, False
    except Exception:
        pass
    f = ROOT / fixtures / "cert_sample.json"
    ents = load_cert_file(f) if f.exists() else []
    return {e["domain"]: e for e in ents}, True


def e6(ctx: Ctx) -> pd.DataFrame:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cert, simulated = load_cert(ctx)
    dev = pool(ctx, "dev")
    X = ctx.reps["E1_leace_topic"]
    keep = np.array([i for i, a in enumerate(ctx.ads) if not (a.source == "synthetic_background" and a.meta.get("split") == "fit")])
    thr, _ = tune_agglo(X[dev], ctx.truth[dev], ctx.cfg["cluster"]["agglo_linkage"], ctx.is_camp[dev])
    ads_k = [ctx.ads[i] for i in keep]
    # tau is a starting point in the config; tune it on the dev pool only (no test leakage)
    lab_dev = agglo(X[dev], thr, ctx.cfg["cluster"]["agglo_linkage"])
    tau, tau_f1 = tune_tau([ctx.ads[i] for i in dev], X[dev], lab_dev, ctx.cfg)
    ctx.cfg = {**ctx.cfg, "coordination": {**ctx.cfg["coordination"], "tau": tau}}
    tracks, log, bursts, reg = replay(ads_k, X[keep], thr, ctx.cfg, cert)
    lt = lead_times(tracks, ads_k, cert, simulated)
    ART.joinpath("replay").mkdir(parents=True, exist_ok=True)
    lt.to_csv(ART / "replay" / "lead_times.csv", index=False)
    log.to_csv(ART / "replay" / "replay_log.csv", index=False)
    bursts.to_csv(ART / "replay" / "bursts.csv", index=False)
    camp_ids = {a.truth_campaign for a in ads_k if a.truth_campaign}
    found = {c for c in lt.campaign.unique()} if len(lt) else set()
    detected_campaigns = {max(__import__("collections").Counter(ads_k[i].truth_campaign for i in t["members"]).items(), key=lambda kv: (kv[0] is not None, kv[1]))[0] for t in tracks}
    pur = [__import__("collections").Counter(ads_k[i].truth_campaign for i in t["members"]).most_common(1)[0] for t in tracks]
    precision = float(np.mean([c is not None and n / len(t["members"]) >= 0.5 for (c, n), t in zip(pur, tracks)])) if tracks else float("nan")
    # removed-ads statistics (E6): only meaningful with real ingestion history
    removed = [a for a in ctx.ads if a.removed_after_seen]
    days_removed = [(__import__("datetime").datetime.fromisoformat(a.meta["removed_detected_at"]) - a.first_seen_at).days for a in removed if a.meta.get("removed_detected_at")]
    delisted = [d for d, e in cert.items() if e.get("delete_date")]
    proposed_delisted = [d for t in tracks for i in t["members"] for d in ads_k[i].domains if d in delisted]
    row = {"tau_dev_tuned": tau, "tau_dev_f1": tau_f1, "n_tracks": len(tracks), "track_precision_majority_campaign": precision, "campaigns_total": len(camp_ids),
           "campaigns_detected": len({c for c in detected_campaigns if c}), "bursts_flagged": int(bursts.burst.sum()),
           "lead_days_median": float(lt.lead_days.median()) if len(lt) else float("nan"),
           "lead_frac_positive": float((lt.lead_days > 0).mean()) if len(lt) else float("nan"),
           "n_lead_domains": len(lt), "lead_is_simulation": simulated,
           "removed_after_seen_n": len(removed), "removed_median_days": float(np.median(days_removed)) if days_removed else float("nan"),
           "proposed_domains_delisted_by_cert": len(set(proposed_delisted)), "delisted_total": len(delisted)}
    df = pd.DataFrame([row])
    _save("E6_operational_value", df, ctx.cfg, ctx.seed, {"simulation": simulated})
    if len(lt):
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.hist(lt.lead_days, bins=15, color="#55a868")
        ax.axvline(0, color="k", lw=1)
        ax.set_xlabel("lead time [dni] (dodatnie = wykryte przed Listą CERT)" + ("  [SYMULACJA]" if simulated else ""))
        ax.set_title("E6: czas wyprzedzenia względem Listy Ostrzeżeń")
        fig.tight_layout()
        fig.savefig(ART / "figures" / "E6_lead_time.png", dpi=150)
        plt.close(fig)
    # campaign cards + graph on the full (non-FIT) pool
    lab = agglo(X[keep], thr, ctx.cfg["cluster"]["agglo_linkage"])
    cards = build_cards(ads_k, X[keep], lab, ctx.cfg, cert, with_cert_in_score=False)
    G, _ = build_graph(ads_k, X[keep], lab, ctx.cfg)
    memb = communities(G, ctx.cfg["graph"]["leiden_resolution"], ctx.seed)
    export(G, memb, ART / "graph", f"run-{ctx.seed}")
    return df


def _union_labels(n: int, *label_sets: np.ndarray) -> np.ndarray:
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for lab in label_sets:
        first: dict[int, int] = {}
        for i, l in enumerate(lab):
            if l in first:
                ra, rb = find(i), find(first[l])
                if ra != rb:
                    parent[ra] = rb
            else:
                first[l] = i
    roots: dict[int, int] = {}
    return np.array([roots.setdefault(find(i), len(roots)) for i in range(n)])


def e7(ctx: Ctx) -> pd.DataFrame:
    """Complexity ablation on the real graph machinery (Leiden): infra only, +SimHash, +E0 content, +E1 content."""
    import copy

    test = pool(ctx, "test")
    ads = [ctx.ads[i] for i in test]
    camp = np.array([a.truth_campaign for a in ads], dtype=object)
    dom = [set(a.domains) for a in ads]
    dummy = np.zeros(len(ads), dtype=int)
    variants = {
        "infra_only": ("E0_raw", False, False),
        "infra+simhash": ("E0_raw", True, False),
        "infra+E0": ("E0_raw", True, True),
        "infra+E1": ("E1_leace_topic", True, True),
    }
    rows = []
    for name, (ch, use_hash, use_content) in variants.items():
        cfg = copy.deepcopy(ctx.cfg)
        G, _ = build_graph(ads, ctx.reps[ch][test], dummy, cfg, use_hash=use_hash, use_content=use_content)
        memb = communities(G, cfg["graph"]["leiden_resolution"], ctx.seed)
        lab = np.array([memb[v.index] for v in G.vs if v["kind"] == "creative"])
        r = eval_labels(ctx, test, lab, ctx.cfg["eval"]["bootstrap"])
        by: dict = {}
        for i, c in enumerate(camp):
            if c is not None:
                by.setdefault(c, []).append(i)
        rng = np.random.default_rng(ctx.seed)
        hit = tot = 0
        for c, ids in by.items():
            for _ in range(min(200, len(ids) * 3)):
                x, y = rng.choice(ids, 2, replace=False)
                if not dom[x] & dom[y]:
                    tot += 1
                    hit += lab[x] == lab[y]
        rows.append({"variant": name, "bcubed_P": r["P"], "bcubed_R": r["R"], "bcubed_F1": r["F1"], "F1_ci_lo": r["F1_ci"][0],
                     "F1_ci_hi": r["F1_ci"][1], "campaign_F1": r["cF1"], "recall_cross_topic": r["recall_x"],
                     "recall_rotated_domains": hit / tot if tot else float("nan"), "n_rotation_pairs": tot})
    df = pd.DataFrame(rows)
    _save("E7_complexity_ablation", df, ctx.cfg, ctx.seed)
    return df


def write_report(out: dict, path_=None) -> str:
    def md(df):
        return df.round(3).to_markdown(index=False) if hasattr(df, "to_markdown") else df.round(3).to_string(index=False)

    parts = ["# Raport eksperymentów", "", "Wynik na syntetyce dowodzi tylko, że metoda odzyskuje podłożony szablon, a nie że prawdziwe kampanie go mają.", "",
             f"**Werdykt H1:** {out['verdict']}", ""]
    for k in ["E1", "E2", "E3", "E4", "E5", "E6", "E7"]:
        if k in out:
            parts += [f"## {k}", md(out[k]), ""]
    text = "\n".join(parts)
    (ART / "tables" / "REPORT.md").write_text(text)
    return text
