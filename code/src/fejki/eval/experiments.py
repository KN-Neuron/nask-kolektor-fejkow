"""Experiments E1 to E7. Each writes CSV/PNG/JSON to artifacts/ and a row to eval_runs."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from ..analyze.cluster import agglo, hash_cluster, hdbscan, tune_agglo, tune_hdbscan
from ..config import ROOT, git_hash, path
from ..embed.controls import random_k1, random_pca
from ..embed.encoder import embed_texts
from ..embed.erase import LABELER_VERSION, apply_leace, fit_leace, length_bucket, rule_label
from ..embed.probes import probe
from ..ingest.jsonl import read_jsonl
from ..process.pipeline import enrich
from ..schema import Ad
from .metrics import aux, bcubed_ci, campaign_weighted, cross_topic, cross_topic_recall_ci

CHANNELS = ["H0_simhash", "E0_raw", "E1_leace_topic", "E2_leace_name", "E3_leace_topic_len_lang", "E4_random_k1", "E5_random_pca"]
ART = ROOT / "artifacts"


@dataclass
class Ctx:
    cfg: dict
    ads: list[Ad]
    X: np.ndarray
    reps: dict[str, np.ndarray] = field(default_factory=dict)
    ranks: dict[str, int] = field(default_factory=dict)
    seed: int = 1

    @property
    def truth(self) -> np.ndarray:
        # non-campaign ads: identical creatives (same page and text) are one creative, not separate ground-truth groups
        return np.array([a.truth_campaign or f"single:{a.page_id}:{hash(a.text_norm)}" for a in self.ads], dtype=object)

    @property
    def is_camp(self) -> np.ndarray:
        return np.array([a.truth_campaign is not None for a in self.ads])

    @property
    def groups(self) -> np.ndarray:
        return self.truth


def load_ads(cfg: dict, fixtures: str | Path = "data/fixtures", extra: list[str] | None = None) -> list[Ad]:
    d = ROOT / fixtures
    files = [d / "ads_background.jsonl", d / "synth.jsonl"] + [Path(x) for x in (extra or [])]
    return [enrich(a, cfg) for f in files if f.exists() for a in read_jsonl(f)]


def name_labels(ads: list[Ad]) -> list[str]:
    return [a.named_entities[0] if a.named_entities else "none" for a in ads]


def build_ctx(cfg: dict, seed: int = 1, fixtures: str = "data/fixtures", ads: list[Ad] | None = None) -> Ctx:
    ads = ads or load_ads(cfg, fixtures)
    texts = [a.text_norm for a in ads]
    X = embed_texts(texts, cfg)
    ctx = Ctx(cfg, ads, X, seed=seed)
    fit = [i for i, a in enumerate(ads) if a.source == "synthetic_background" and a.meta.get("split") == "fit"]
    if not fit:  # real data: fit on a random 40% of non-campaign ads
        rng = np.random.default_rng(seed)
        fit = list(rng.choice(len(ads), int(0.4 * len(ads)), replace=False))
    ctx.meta_fit = fit  # type: ignore[attr-defined]
    labs = [rule_label(ads[i].text_norm) for i in fit]
    er, r1 = fit_leace(X[fit], labs)
    ctx.reps["E0_raw"] = X
    ctx.reps["E1_leace_topic"] = apply_leace(er, X)
    ctx.ranks["E1_leace_topic"] = r1
    nl = name_labels(ads)
    if len(set(nl[i] for i in fit)) > 1:
        er2, r2 = fit_leace(X[fit], [nl[i] for i in fit])
        ctx.reps["E2_leace_name"] = apply_leace(er2, X)
        ctx.ranks["E2_leace_name"] = r2
    else:
        ctx.reps["E2_leace_name"], ctx.ranks["E2_leace_name"] = X, 0
    comb = [f"{rule_label(ads[i].text_norm)}|{length_bucket(ads[i].text_norm)}|{ads[i].lang}" for i in fit]
    er3, r3 = fit_leace(X[fit], comb)
    ctx.reps["E3_leace_topic_len_lang"] = apply_leace(er3, X)
    ctx.ranks["E3_leace_topic_len_lang"] = r3
    ctx.reps["E4_random_k1"] = random_k1(X, r1, seed)
    ctx.reps["E5_random_pca"] = random_pca(X, r1, seed, cfg["erase"].get("pca_pool", 50))
    return ctx


def _save(name: str, df: pd.DataFrame, cfg: dict, seed: int, extra: dict | None = None) -> None:
    (ART / "tables").mkdir(parents=True, exist_ok=True)
    df.to_csv(ART / "tables" / f"{name}.csv", index=False)
    (ART / "tables" / f"{name}.config.json").write_text(json.dumps(
        {"config": cfg, "seed": seed, "git": git_hash(), "labeler": LABELER_VERSION, **(extra or {})}, default=str, indent=1))
    try:
        from ..config import load_config  # noqa: F401
        from ..db import connect, log_eval

        con = connect(path(cfg.get("db_path", "data/db.duckdb")))
        log_eval(con, name, cfg, seed, git_hash(), df.head(50).to_dict("records"))
        con.close()
    except Exception:
        pass


def cluster_channel(ctx: Ctx, channel: str, method: str, dev: np.ndarray, test: np.ndarray):
    """Tune on dev pool, cluster the test pool. Returns test labels and the chosen parameter."""
    truth = ctx.truth
    if channel == "H0_simhash":
        texts = [ctx.ads[i].text_norm for i in test]
        return hash_cluster(texts, ctx.cfg), "hamming<=3|jaccard>=0.6"
    X = ctx.reps[channel]
    ic = ctx.is_camp[dev]
    if method == "agglo":
        thr, _ = tune_agglo(X[dev], truth[dev], ctx.cfg["cluster"]["agglo_linkage"], ic)
        return agglo(X[test], thr, ctx.cfg["cluster"]["agglo_linkage"]), f"thr={thr}"
    m, _ = tune_hdbscan(X[dev], truth[dev], is_camp=ic)
    return hdbscan(X[test], m), f"min_cluster_size={m}"


def pool(ctx: Ctx, split: str) -> np.ndarray:
    return np.array([i for i, a in enumerate(ctx.ads) if a.meta.get("split") == split and not (a.source == "synthetic_background" and a.meta.get("split") == "fit")])


def eval_labels(ctx: Ctx, test: np.ndarray, lab: np.ndarray, n_boot: int) -> dict:
    truth, ads = ctx.truth[test], [ctx.ads[i] for i in test]
    is_c = np.array([a.truth_campaign is not None for a in ads])
    r = bcubed_ci(lab, truth, truth, n_boot=n_boot, seed=ctx.seed)
    r.update(campaign_weighted(lab, truth, is_c))
    r.update(cross_topic(lab, [a.truth_campaign for a in ads], [a.truth_topic for a in ads]))
    _, lo, hi = cross_topic_recall_ci(lab, [a.truth_campaign for a in ads], [a.truth_topic for a in ads], n_boot, ctx.seed)
    r["recall_x_ci"] = (lo, hi)
    r.update(aux(lab, truth))
    return r


def _fmt(v, ci):
    return f"{v:.3f} [{ci[0]:.3f}, {ci[1]:.3f}]"


def e1(ctx: Ctx) -> pd.DataFrame:
    dev, test = pool(ctx, "dev"), pool(ctx, "test")
    rows = []
    for method in ["agglo", "hdbscan"]:
        for ch in CHANNELS:
            if ch == "H0_simhash" and method == "hdbscan":
                continue
            lab, par = cluster_channel(ctx, ch, method, dev, test)
            r = eval_labels(ctx, test, lab, ctx.cfg["eval"]["bootstrap"])
            rows.append({"method": method if ch != "H0_simhash" else "components", "channel": ch, "param": par,
                         "rank_removed": ctx.ranks.get(ch, ""), "n_clusters": len(set(lab)),
                         "bcubed_P": r["P"], "bcubed_R": r["R"], "bcubed_F1": r["F1"], "F1_ci_lo": r["F1_ci"][0], "F1_ci_hi": r["F1_ci"][1],
                         "P_ci": _fmt(r["P"], r["P_ci"]), "R_ci": _fmt(r["R"], r["R_ci"]),
                         "campaign_F1": r["cF1"], "recall_cross_topic": r["recall_x"], "recall_x_ci_lo": r["recall_x_ci"][0], "recall_x_ci_hi": r["recall_x_ci"][1], "sep_cross_campaign_topic": r["sep_x"],
                         "ARI": r["ARI"], "NMI": r["NMI"]})
    df = pd.DataFrame(rows)
    _save("E1_campaign_recovery", df, ctx.cfg, ctx.seed)
    _plot_e1(df)
    return df


def _plot_e1(df: pd.DataFrame) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(9, 4.5))
    d = df[df.method.isin(["agglo", "components"])]
    err = np.array([d.bcubed_F1 - d.F1_ci_lo, d.F1_ci_hi - d.bcubed_F1])
    ax.bar(range(len(d)), d.bcubed_F1, yerr=err, capsize=3, color="#4c72b0")
    ax.set_xticks(range(len(d)))
    ax.set_xticklabels(d.channel, rotation=35, ha="right")
    ax.set_ylabel("B-cubed F1 (95% CI, bootstrap po kampaniach)")
    ax.set_title("E1: odzysk kampanii syntetycznych (test)")
    fig.tight_layout()
    (ART / "figures").mkdir(parents=True, exist_ok=True)
    fig.savefig(ART / "figures" / "E1_campaign_recovery.png", dpi=150)
    plt.close(fig)


def h1_verdict(df: pd.DataFrame) -> str:
    """Primary criterion (declared in SPEC before results): B-cubed F1 CI of a LEACE channel does not overlap E0, E4, E5.
    Secondary criterion (added after seeing results, therefore exploratory): same rule on cross-topic recall.
    """
    lines = []
    prim, sec = [], []
    for method in ["agglo", "hdbscan"]:
        d = df[df.method == method].set_index("channel")
        if "E0_raw" not in d.index:
            continue
        base = d.loc[["E0_raw", "E4_random_k1", "E5_random_pca"]]
        for ch in ["E1_leace_topic", "E2_leace_name", "E3_leace_topic_len_lang"]:
            r = d.loc[ch]
            if r.F1_ci_lo > base.F1_ci_hi.max():
                prim.append(f"{ch}/{method}")
            if r.recall_x_ci_lo > base.recall_x_ci_hi.max():
                sec.append(f"{ch}/{method}")
    lines.append("Kryterium główne (B-cubed F1, CI nienakładające się z E0, E4, E5): " + (
        "SPEŁNIONE przez " + ", ".join(prim) if prim else "NIESPEŁNIONE."))
    lines.append("Kryterium wtórne, eksploracyjne, dodane po obejrzeniu wyników (recall między-tematowy, te same zasady CI): " + (
        "SPEŁNIONE przez " + ", ".join(sec) if sec else "NIESPEŁNIONE."))
    verdict = ("H1 POTWIERDZONA (kryterium główne) na syntetyce." if prim else
               "H1 w wersji głównej NIEPOTWIERDZONA; LEACE podnosi recall między-tematowy ponad kontrole (wynik eksploracyjny), ale kosztem precyzji, więc F1 się nie poprawia." if sec else
               "H1 NIEPOTWIERDZONA: LEACE nie bije kontroli losowej projekcji. Raportujemy wynik negatywny; wartość projektu opiera się na części operacyjnej.")
    return verdict + " " + " ".join(lines)


def e2(ctx: Ctx) -> pd.DataFrame:
    fit_set = set(ctx.meta_fit)  # type: ignore[attr-defined]
    idx = [i for i in range(len(ctx.ads)) if ctx.ads[i].source != "synthetic_control" or True]
    idx = [i for i in idx if i not in fit_set]  # evaluate probes on data NOT used to fit the eraser
    y = [ctx.ads[i].truth_topic or rule_label(ctx.ads[i].text_norm) for i in idx]
    g = [ctx.ads[i].truth_campaign or f"s{i}" for i in idx]
    rows = []
    for ch in ["E0_raw", "E1_leace_topic", "E4_random_k1", "E5_random_pca"]:
        for kind in ["linear", "mlp"]:
            r = probe(ctx.reps[ch][idx], y, g, kind, ctx.seed)
            rows.append({"channel": ch, "probe": kind, "acc": r["acc"], "majority_chance": r["chance"], "uniform_chance": r["uniform_chance"]})
    # sanity on FIT split: linear probe after LEACE should be near chance
    fi = sorted(fit_set)
    yf = [rule_label(ctx.ads[i].text_norm) for i in fi]
    for ch in ["E0_raw", "E1_leace_topic"]:
        r = probe(ctx.reps[ch][fi], yf, [f"f{i}" for i in fi], "linear", ctx.seed)
        rows.append({"channel": ch + "@FIT", "probe": "linear", "acc": r["acc"], "majority_chance": r["chance"], "uniform_chance": r["uniform_chance"]})
    df = pd.DataFrame(rows)
    _save("E2_topic_probes", df, ctx.cfg, ctx.seed)
    return df


def e3(ctx: Ctx, n_texts: int = 50) -> pd.DataFrame:
    """Paraphrase robustness: level-2 rewrites of 50 test campaign ads; pair retention original<->paraphrase."""
    import random

    from ..synth.campaigns import SYNONYMS, TEMPLATES, TOPIC_POOL, _fill

    rng = random.Random(ctx.seed + 7)
    dev, test = pool(ctx, "dev"), pool(ctx, "test")
    camp = [i for i in test if ctx.ads[i].truth_campaign]
    src = rng.sample(camp, min(n_texts, len(camp)))
    new_ads = []
    for k, i in enumerate(src):
        a = ctx.ads[i]
        frames = TEMPLATES[a.truth_template][1]
        order = TEMPLATES[a.truth_template][0]
        pool_t = TOPIC_POOL[a.truth_topic]
        name = a.named_entities[0] if a.named_entities else "Osoba Publiczna A"
        slots = dict(name=name, obj=rng.choice(pool_t["obj"]), gain=rng.choice(pool_t["gain"]), domain="para-x.example")
        txt = " ".join(_fill(frames[m][1], slots) for m in order)
        for w, s in SYNONYMS.items():
            txt = txt.replace(w, s)
        b = a.model_copy(deep=True)
        b.ad_id = a.ad_id + "~para2"
        b.body, b.title, b.description, b.link_caption = txt, None, None, "para-x.example"
        b.meta = {**a.meta, "kind": "para2"}
        new_ads.append(enrich(b, ctx.cfg))
    all_ads = ctx.ads + new_ads
    ctx2 = build_ctx(ctx.cfg, ctx.seed, ads=all_ads)
    n0 = len(ctx.ads)
    rows = []
    test2 = np.concatenate([test, np.arange(n0, n0 + len(new_ads))])
    dev2 = dev
    for ch in ["H0_simhash", "E0_raw", "E1_leace_topic", "E4_random_k1"]:
        lab, _ = cluster_channel(ctx2, ch, "agglo", dev2, test2)
        pos = {i: k for k, i in enumerate(test2)}
        kept = sum(lab[pos[i]] == lab[pos[n0 + k]] for k, i in enumerate(src)) / len(src)
        # baseline for the same channel: pairs of originals from the same campaign that share the paraphrase's campaign
        rows.append({"channel": ch, "pair_retention_orig_vs_para2": kept, "n_pairs": len(src)})
    df = pd.DataFrame(rows)
    _save("E3_paraphrase_robustness", df, ctx.cfg, ctx.seed)
    return df


def e4(ctx: Ctx) -> pd.DataFrame:
    """Style control: C1 share in campaign clusters, and synthetic-vs-background classifier AUC."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import GroupKFold, cross_val_predict

    dev, test = pool(ctx, "dev"), pool(ctx, "test")
    rows = []
    for ch in ["E0_raw", "E1_leace_topic"]:
        lab, _ = cluster_channel(ctx, ch, "agglo", dev, test)
        kinds = np.array([ctx.ads[i].meta.get("kind") for i in test])
        camp_mask = np.array([ctx.ads[i].truth_campaign is not None for i in test])
        c1_in = []
        for j in np.where(kinds == "c1")[0]:
            members = lab == lab[j]
            c1_in.append(members.sum() >= ctx.cfg["coordination"]["min_ads"] and camp_mask[members].mean() >= 0.5)
        real = np.array([ctx.ads[i].source in ("synthetic_background", "meta", "file") for i in range(len(ctx.ads))])
        syn = np.array([ctx.ads[i].source in ("synthetic_campaign", "synthetic_control") for i in range(len(ctx.ads))])
        m = real | syn
        X, y = ctx.reps[ch][m], syn[m].astype(int)
        g = np.arange(m.sum())
        p = cross_val_predict(LogisticRegression(max_iter=500), X, y, cv=GroupKFold(5), groups=g, method="predict_proba")[:, 1]
        rows.append({"channel": ch, "c1_share_in_campaign_clusters": float(np.mean(c1_in)) if c1_in else float("nan"),
                     "n_c1": len(c1_in), "synthetic_vs_real_auc": float(roc_auc_score(y, p)),
                     "note": "'real' = background fixtures if no real ads loaded (offline proxy)"})
    df = pd.DataFrame(rows)
    _save("E4_style_control", df, ctx.cfg, ctx.seed)
    return df


def e5(ctx: Ctx) -> pd.DataFrame:
    """Cross-modal agreement: content clusters (no infra) vs. domain/CERT pseudo-labels; writes annotation sheet."""
    from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score

    from ..analyze.coordination import domain_components

    dev, test = pool(ctx, "dev"), pool(ctx, "test")
    rows = []
    sel = [i for i in test if ctx.ads[i].domains]
    pseudo = domain_components([ctx.ads[i] for i in sel])
    for ch in ["E0_raw", "E1_leace_topic"]:
        lab, _ = cluster_channel(ctx, ch, "agglo", dev, test)
        pos = {i: k for k, i in enumerate(test)}
        l = [lab[pos[i]] for i in sel]
        rows.append({"channel": ch, "ARI_vs_domain_pseudo": adjusted_rand_score(pseudo, l),
                     "NMI_vs_domain_pseudo": normalized_mutual_info_score(pseudo, l), "n_ads": len(sel),
                     "note": "agreement, not accuracy; pseudo-labels = connected components of shared domain"})
    df = pd.DataFrame(rows)
    _save("E5_crossmodal_agreement", df, ctx.cfg, ctx.seed)
    # annotation sheet: 150 pairs, mix of close pairs from E1 channel
    rng = np.random.default_rng(ctx.seed)
    X = ctx.reps["E1_leace_topic"][test]
    pairs = []
    for _ in range(150):
        i = rng.integers(len(test))
        s = X @ X[i]
        s[i] = -1
        j = int(rng.choice(np.argsort(-s)[:20]))
        pairs.append({"ad_a": ctx.ads[test[i]].ad_id, "text_a": ctx.ads[test[i]].text_norm, "ad_b": ctx.ads[test[j]].ad_id,
                      "text_b": ctx.ads[test[j]].text_norm, "same_campaign_human_label": ""})
    path("artifacts/annotation/pairs.csv")
    pd.DataFrame(pairs).to_csv(ART / "annotation" / "pairs.csv", index=False)
    return df


def run_all(cfg: dict, seed: int = 1, fixtures: str = "data/fixtures") -> dict:
    ctx = build_ctx(cfg, seed, fixtures)
    out = {"E1": e1(ctx)}
    out["verdict"] = h1_verdict(out["E1"])
    out["E2"] = e2(ctx)
    out["E3"] = e3(ctx)
    out["E4"] = e4(ctx)
    out["E5"] = e5(ctx)
    from .report import e6, e7

    out["E6"] = e6(ctx)
    out["E7"] = e7(ctx)
    (ART / "tables" / "H1_verdict.txt").write_text(out["verdict"] + "\n")
    return out
