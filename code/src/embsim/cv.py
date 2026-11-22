"""Ewaluacja według protokołu N-LNSO (zagnieżdżone „leave-N-subjects-out”), przeniesionego na nasz problem.

    python -m embsim.cv [--worlds 80] [--workers 4]

Protokół (adaptacja):
  * PODMIOT = niezależny świat syntetyczny (jeden korpus: operatorzy, kampanie, warianty; embsim/synth2.py). Wynik punktowania zależy
    od statystyk korpusu (idf śladów, μ kosinusów, PCA), więc świat jest naturalną jednostką niezależności. Światów jest tyle, ile
    zażądamy (nie jak w badaniach na ludziach), co pozwala na wąskie przedziały ufności.
  * 5 zewnętrznych foldów; każdy świat jest testowy DOKŁADNIE RAZ i oceniany przez progi, które go nie widziały. Podział robiony przed
    jakimkolwiek przetwarzaniem.
  * Dobór zagnieżdżony w światach treningowych: 3 grupy wewnętrzne; kandydat dostaje progi z 2 grup i jest oceniany na 3.; najlepszy
    dostaje progi z całego treningu i jest oceniany na teście JEDEN raz („wariant dostrojony”).
  * Normalizacje bez etykiet: stała e_ref (typowa dostępność dowodu) z zebranych, nieetykietowanych statystyk dostępności; PCA i TF-IDF
    dopasowywane na korpusie danego świata (jak normalizacja per podmiot).
  * 3 różne losowe podziały zamiast „3 ziaren”; wynik świata = średnia z podziałów, w których jest testowy (w każdym dokładnie raz).
  * Podmiot jest niezależną jednostką dla WSZYSTKICH przedziałów: bootstrap po światach; porównania parami testem Wilcoxona na
    różnicach per świat z korektą Holma.
Ograniczenia: to wciąż syntetyka z generatora pisanego przez nas; protokół chroni przed przeuczeniem progów i wyborów, nie przed
rozbieżnością generatora względem rzeczywistości. Ocena na prawdziwych danych (Meta, NASK) jest osobnym zadaniem.
"""
from __future__ import annotations

import argparse
import copy
import json
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from itertools import combinations
from pathlib import Path

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform
from scipy.stats import wilcoxon
from sklearn.metrics import adjusted_rand_score

from .bench import ART, Config, Dataset, _synth, corpus, vectors
from .metrics import _unique_labels, assignment, bcubed, pairwise

GRID = sorted({round(float(x), 2) for x in np.arange(0.05, 0.96, 0.05)} | {round(float(x), 2) for x in np.arange(0.96, 1.0, 0.01)})
LEVELS = ("campaign", "operator")
N_FOLDS, N_INNER, N_PARTITIONS = 5, 3, 3


def candidates() -> dict[str, Config]:
    """Kandydaci (progi uzupełnia protokół). Ablacje względem konfiguracji domyślnej `mixed`."""
    adj = ["campaign"]
    mixed = dict(adjust_levels=adj, lexical=True, trace_mode="overlap", trace_mode_operator="contain", embed_fix="abtt1")
    return {
        "base (v1: Jaccard, średnia)": Config(),
        "lex (v1: Jaccard + leksyka + korekta)": Config(adjust_levels=adj, lexical=True),
        "contain + PCA": Config(adjust_levels=adj, lexical=True, trace_mode="contain", embed_fix="abtt1"),
        "overlap + PCA": Config(adjust_levels=adj, lexical=True, trace_mode="overlap", embed_fix="abtt1"),
        "mixed (domyślna)": Config(**mixed),
        "mixed bez PCA": Config(**{**mixed, "embed_fix": "none"}),
        "mixed bez leksyki": Config(**{**mixed, "lexical": False}),
    }


REFERENCE = "mixed (domyślna)"


# --------------------------------------------------------------------------------------------------------------------
# podział (czysta logika, testowana)


def outer_folds(n_subjects: int, seed: int, k: int = N_FOLDS) -> list[np.ndarray]:
    """Podział indeksów podmiotów na k rozłącznych foldów testowych (każdy podmiot w teście dokładnie raz)."""
    return [np.sort(f) for f in np.array_split(np.random.default_rng(seed).permutation(n_subjects), k)]


def inner_groups(train: np.ndarray, seed: int, k: int = N_INNER) -> list[np.ndarray]:
    return [np.sort(g) for g in np.array_split(np.random.default_rng(seed).permutation(train), k)]


def holm(p: list[float]) -> list[float]:
    """Korekta Holma–Bonferroniego (wartości p skorygowane, w oryginalnej kolejności)."""
    m = len(p)
    order = np.argsort(p)
    adj = np.empty(m)
    run = 0.0
    for rank, i in enumerate(order):
        run = max(run, (m - rank) * p[i])
        adj[i] = min(1.0, run)
    return adj.tolist()


def bootstrap_ci(x: np.ndarray, n: int = 4000, seed: int = 0) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    means = rng.choice(x, size=(n, len(x)), replace=True).mean(1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


# --------------------------------------------------------------------------------------------------------------------
# światy i wstępne liczenie


def world_params(i: int) -> dict:
    r = np.random.default_rng(10_000 + i)
    return dict(n_operators=int(r.integers(5, 11)), campaigns_per_op=int(r.integers(2, 4)), variants=int(r.integers(3, 6)),
                missing_rate=float(r.uniform(0.2, 0.45)))


def make_worlds(n: int, base_seed: int = 101) -> list[Dataset]:
    from .synth2 import generate

    out = []
    for i in range(n):
        seed = base_seed + i
        d = ART / "cv_worlds" / f"w{seed}"
        if not (d / "prawda.json").exists():
            d.mkdir(parents=True, exist_ok=True)
            generate(d, seed=seed, **world_params(i))
        out.append(_synth(f"w{seed}", "cv", d))
    return out


def _strip_har(cases):
    cs = copy.deepcopy(cases)
    for c in cs:
        for ch in ("kit", "scheme", "host"):
            c.sets.pop(ch, None)
    return cs


def raw_and_avail(cfg: Config, lv: str, cases, V) -> tuple[np.ndarray, np.ndarray]:
    """Surowa macierz wyników (bez korekty o dostępność) i macierz dostępności dowodu."""
    c = corpus(replace(cfg, adjust_levels=[]), lv, cases, V)
    n = len(c.cases)
    S, E = np.eye(n, dtype=np.float32), np.ones((n, n), dtype=np.float32)
    for i in range(n):
        for j in range(i + 1, n):
            S[i, j] = S[j, i] = c.score(c.cases[i], c.cases[j]).raw
            E[i, j] = E[j, i] = c.availability(c.cases[i], c.cases[j])
    return S, E


def _world_task(args):
    ds, cfgs = args
    out = {}
    V = vectors(next(iter(cfgs.values())), ds.cases)          # ten sam model tekstu dla wszystkich kandydatów
    for name, cfg in cfgs.items():
        for lv in LEVELS:
            out[(name, lv, "baza")] = raw_and_avail(cfg, lv, ds.cases, V)
        out[(name, "campaign", "bez_HAR")] = raw_and_avail(cfg, "campaign", _strip_har(ds.cases), V)
    return out


def adjust(S, E, e_ref):
    if not e_ref:
        return S
    lam = np.minimum(1.0, E / e_ref)
    return np.where(lam > 1e-9, np.maximum(0.0, 1.0 - (1.0 - S) / np.maximum(lam, 1e-9)), 0.0)


def cut(S: np.ndarray, t: float, Z=None) -> np.ndarray:
    if Z is None:
        Z = linkage(squareform(1 - S, checks=False), method="average")
    return fcluster(Z, 1 - t, criterion="distance")


def precompute(worlds: list[Dataset], cfgs: dict[str, Config], workers: int) -> dict:
    t0 = time.time()
    cfg0 = next(iter(cfgs.values()))
    for w in worlds:                                          # rozgrzej cache wektorów tekstu w procesie głównym (jeden model)
        vectors(cfg0, w.cases)
    print(f"wektory tekstu gotowe: {time.time() - t0:.0f}s", flush=True)
    with ProcessPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(_world_task, [(w, cfgs) for w in worlds], chunksize=1))
    print(f"wstępne liczenie macierzy: {time.time() - t0:.0f}s", flush=True)
    # stała e_ref (kampania, dla konfiguracji z korektą): mediana po światach z mediany dostępności par; statystyka bez etykiet
    e_ref, world_meds = {}, {}
    for name, cfg in cfgs.items():
        for lv in cfg.adjust_levels:
            meds = [float(np.median(r[(name, lv, "baza")][1][np.triu_indices(len(w.cases), 1)])) for r, w in zip(results, worlds)]
            e_ref[(name, lv)] = float(np.median(meds))
            world_meds[(name, lv)] = np.array(meds)
    pre = {}
    for wi, (r, w) in enumerate(zip(results, worlds)):
        n = len(w.cases)
        for name in cfgs:
            for lv in LEVELS:
                S = adjust(r[(name, lv, "baza")][0], r[(name, lv, "baza")][1], e_ref.get((name, lv)))
                np.fill_diagonal(S, 1.0)
                Z = linkage(squareform(1 - S, checks=False), method="average")
                lab = _unique_labels(w.labels[lv])
                curve = np.array([adjusted_rand_score(lab, cut(S, t, Z)) for t in GRID])
                pre[(wi, name, lv)] = {"S": S, "Z": Z, "curve": curve, "auc": pairwise(S, w.labels[lv])["AUC"]}
            Sh = adjust(r[(name, "campaign", "bez_HAR")][0], r[(name, "campaign", "bez_HAR")][1], e_ref.get((name, "campaign")))
            np.fill_diagonal(Sh, 1.0)
            pre[(wi, name, "campaign_bezHAR")] = {"S": Sh, "Z": linkage(squareform(1 - Sh, checks=False), method="average")}
    return pre, e_ref, world_meds


def e_ref_sensitivity(world_meds: dict, n: int) -> dict:
    """Czy wspólne e_ref (liczone po wszystkich światach, bez etykiet) zmieniłoby się, gdyby liczyć je tylko na światach treningowych każdego
    foldu zewnętrznego? Zwraca maksymalne odchylenie i liczbę foldów, w których e_ref różni się od wspólnego (dla każdej konfiguracji i poziomu)."""
    out = {}
    for key, meds in world_meds.items():
        glob = float(np.median(meds))
        devs = [abs(float(np.median(meds[np.setdiff1d(np.arange(n), test)])) - glob)
                for part in range(N_PARTITIONS) for test in outer_folds(n, seed=part)]
        out[key] = {"e_ref": glob, "max_odchylenie": max(devs), "foldów_z_różnicą": int(sum(d > 1e-9 for d in devs)), "foldów": len(devs)}
    return out


# --------------------------------------------------------------------------------------------------------------------
# dobór progu i ocena


def fit_threshold(pre, name, lv, train_idx) -> float:
    curve = np.mean([pre[(i, name, lv)]["curve"] for i in train_idx], axis=0)
    best = curve.max()
    plateau = [t for t, v in zip(GRID, curve) if v >= best - 0.02]
    return float(np.median(plateau))


def curve_at(pre, i, name, lv, t) -> float:
    return float(pre[(i, name, lv)]["curve"][int(np.argmin(np.abs(np.array(GRID) - t)))])


def evaluate_world(pre, worlds, i, name, thr) -> dict:
    w = worlds[i]
    out = {}
    for lv in LEVELS:
        p = pre[(i, name, lv)]
        lab = pred = cut(p["S"], thr[lv], p["Z"])
        out[f"{lv}_ARI"] = float(adjusted_rand_score(_unique_labels(w.labels[lv]), pred))
        out[f"{lv}_B3_F"] = bcubed(pred, w.labels[lv])["B3_F"]
        out[f"{lv}_AUC"] = p["auc"]
    a = assignment(pre[(i, name, "campaign")]["S"], w.labels["campaign"], thr["campaign"])
    out["campaign_błędne"] = a.get("błędnie_połączone", float("nan"))
    h = pre[(i, name, "campaign_bezHAR")]
    out["campaign_bezHAR_ARI"] = float(adjusted_rand_score(_unique_labels(w.labels["campaign"]), cut(h["S"], thr["campaign"], h["Z"])))
    return out


def run_cv(worlds, pre, names: list[str]) -> dict:
    n = len(worlds)
    per = {m: [[] for _ in range(n)] for m in names + ["dostrojony (nested)"]}
    chosen = []
    for part in range(N_PARTITIONS):
        for test in outer_folds(n, seed=part):
            train = np.setdiff1d(np.arange(n), test)
            thr = {nm: {lv: fit_threshold(pre, nm, lv, train) for lv in LEVELS} for nm in names}
            # wewnętrzny dobór kandydata (3 grupy): progi z 2 grup, ocena na 3.; cel = ARI kampanii + ARI operatora
            groups = inner_groups(train, seed=100 + part)
            score = {nm: 0.0 for nm in names}
            for g, val in enumerate(groups):
                fit = np.concatenate([x for j, x in enumerate(groups) if j != g])
                for nm in names:
                    for lv in LEVELS:
                        t = fit_threshold(pre, nm, lv, fit)
                        score[nm] += np.mean([curve_at(pre, i, nm, lv, t) for i in val]) / N_INNER
            best = max(score, key=score.get)
            chosen.append(best)
            for i in test:
                for nm in names:
                    per[nm][i].append(evaluate_world(pre, worlds, i, nm, thr[nm]))
                per["dostrojony (nested)"][i].append(evaluate_world(pre, worlds, i, best, thr[best]))
    # wynik świata = średnia z podziałów
    keys = list(per[names[0]][0][0])
    res = {m: {k: np.array([np.mean([d[k] for d in per[m][i]]) for i in range(n)]) for k in keys} for m in per}
    return {"per_world": res, "chosen": chosen}


def summarize(res: dict, ref: str) -> None:
    pw = res["per_world"]
    names = list(pw)
    metrics = [("campaign_ARI", "kampania ARI"), ("campaign_B3_F", "kampania B3_F"), ("campaign_AUC", "kampania AUC"),
               ("campaign_błędne", "błędne łączenie"), ("campaign_bezHAR_ARI", "kampania ARI bez HAR"), ("operator_ARI", "operator ARI"),
               ("operator_AUC", "operator AUC")]
    n = len(next(iter(pw[ref].values())))
    print(f"\n== N-LNSO: {n} światów, {N_FOLDS} foldów zewnętrznych, {N_PARTITIONS} podziały; średnia [95% CI bootstrap po światach]")
    print(f"{'konfiguracja':<40}" + "".join(f"{lab:>26}" for _, lab in metrics))
    for nm in names:
        row = ""
        for k, _ in metrics:
            x = pw[nm][k]; lo, hi = bootstrap_ci(x)
            row += f"{x.mean():>9.3f} [{lo:.3f},{hi:.3f}]"[:26].rjust(26)
        print(f"{nm:<40}{row}")
    print(f"\nwybór wewnętrzny (nested) wskazał: " + ", ".join(f"{k}: {v}" for k, v in
                                                          sorted(__import__('collections').Counter(res['chosen']).items(), key=lambda kv: -kv[1])))
    print(f"\n== porównania parami z '{ref}': różnica średnich per świat [CI], Wilcoxon, p po korekcie Holma (rodzina = wszystkie porównania danej miary)")
    for k, lab in metrics[:2] + metrics[3:6]:
        others = [nm for nm in names if nm != ref]
        ps, ds = [], []
        for nm in others:
            d = pw[ref][k] - pw[nm][k]
            ds.append(d)
            try:
                ps.append(float(wilcoxon(d, zero_method="wilcox").pvalue) if np.any(d != 0) else 1.0)
            except ValueError:
                ps.append(1.0)
        pa = holm(ps)
        print(f"  {lab}")
        for nm, d, p in zip(others, ds, pa):
            lo, hi = bootstrap_ci(d)
            print(f"    {ref} − {nm:<38} Δ={d.mean():+.3f} [{lo:+.3f},{hi:+.3f}]  p_Holm={p:.4f}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--worlds", type=int, default=80)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    cfgs = candidates()
    worlds = make_worlds(a.worlds)
    print(f"światów: {len(worlds)}, przypadków łącznie: {sum(len(w.cases) for w in worlds)}, kandydatów: {len(cfgs)}", flush=True)
    pre, e_ref, world_meds = precompute(worlds, cfgs, a.workers)
    sens = e_ref_sensitivity(world_meds, len(worlds))
    worst = max(v["max_odchylenie"] for v in sens.values())
    print(f"\nwrażliwość e_ref na podział (liczone tylko na światach treningowych foldu): maksymalne odchylenie {worst:.4f}; "
          f"foldów z różnicą: {sum(v['foldów_z_różnicą'] for v in sens.values())} z {sum(v['foldów'] for v in sens.values())}", flush=True)
    res = run_cv(worlds, pre, list(cfgs))
    summarize(res, REFERENCE)
    out = ART.parent / "cv"
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps({"worlds": a.worlds, "e_ref": {f"{k[0]}|{k[1]}": v for k, v in e_ref.items()},
                                                 "e_ref_wrażliwość": {f"{k[0]}|{k[1]}": v for k, v in sens.items()},
                                                 "per_world": {m: {k: v.tolist() for k, v in d.items()} for m, d in res["per_world"].items()},
                                                 "chosen": res["chosen"]}, ensure_ascii=False))
    print("\nzapisano:", out / "report.json")


if __name__ == "__main__":
    main()
