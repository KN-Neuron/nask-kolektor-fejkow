"""Ocena podobieństwa ważonego (bez uczenia) na syntetyku z niezależną prawdą (data/synth/prawda.json).

    python -m embsim.eval_synth ../data/synth [--model paraphrase-multilingual-MiniLM-L12-v2]

Prawda ma dwa poziomy: kampania (ten sam przekaz) i operator (ta sama infrastruktura). Wagi nie są dopasowywane do prawdy.
Mierzymy AUC progowo-niezależnie, średnie wyniki dla relacji i grupowanie przy progu z rozkładu zerowego (bez etykiet).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from sklearn.metrics import adjusted_rand_score, roc_auc_score

from .embed import text_vectors
from .features import load_case
from .score import DEFAULT_WEIGHTS, Corpus
from .similarity import clusters


def relations(truth: dict, ids: list[str]):
    n = len(ids)
    camp = np.zeros((n, n), bool); op = np.zeros((n, n), bool)
    for i, a in enumerate(ids):
        for j, b in enumerate(ids):
            ta, tb = truth[a], truth[b]
            camp[i, j] = ta["kampania"] == tb["kampania"]
            op[i, j] = ta["operator"] == tb["operator"] and not ta["operator"].startswith("neg")
    return camp, op


def auc(S, pos, mask):
    iu = np.triu_indices(len(S), 1)
    m = mask[iu]
    y, s = pos[iu][m], S[iu][m]
    return float(roc_auc_score(y, s)) if 0 < y.sum() < len(y) else float("nan")


def report(name, S, camp, op):
    iu = np.triu_indices(len(S), 1)
    allp = np.ones_like(camp)
    same_op_diff_camp = op & ~camp
    diff_op = ~op & ~camp
    mean = lambda m: float(S[iu][m[iu]].mean())
    print(f"\n== {name}")
    print(f"  średni wynik: ta sama kampania {mean(camp):.3f} | ten sam operator, inna kampania {mean(same_op_diff_camp):.3f} "
          f"| różni operatorzy {mean(diff_op):.3f}")
    print(f"  AUC kampania vs reszta {auc(S, camp, allp):.3f} | operator vs inny operator {auc(S, op, ~camp):.3f}")
    return {"camp": auc(S, camp, allp), "op": auc(S, op, ~camp)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("synth", type=Path)
    ap.add_argument("--model", default="paraphrase-multilingual-MiniLM-L12-v2")
    a = ap.parse_args()
    truth = json.loads((a.synth / "prawda.json").read_text())
    cases = [load_case(a.synth / k) for k in sorted(truth)]
    ids = [c.id for c in cases]
    camp, op = relations(truth, ids)
    V = text_vectors(a.model, [c.text or " " for c in cases])
    print(f"przypadków: {len(cases)}, model tekstu: {a.model}")
    sym = Corpus(cases, V, rotating=set())
    report("wszystkie kanały, wszystkie ślady symetryczne (brak śladu = 0)", sym.matrix()[0], camp, op)
    allpos = Corpus(cases, V, rotating=set(DEFAULT_WEIGHTS) - {"text"})
    report("wszystkie kanały, wszystkie ślady tylko wzmacniają", allpos.matrix()[0], camp, op)
    full = Corpus(cases, V)
    S, E = full.matrix()
    report("wszystkie kanały, host i piksel rotujące (domyślnie)", S, camp, op)
    for ch in DEFAULT_WEIGHTS:
        w = {k: (1.0 if k == ch else 0.0) for k in DEFAULT_WEIGHTS}
        Sc, _ = Corpus(cases, V, w).matrix()
        report(f"tylko kanał: {ch}", Sc, camp, op)
    for ch in DEFAULT_WEIGHTS:
        w = {k: (0.0 if k == ch else 1.0) for k in DEFAULT_WEIGHTS}
        Sc, _ = Corpus(cases, V, w).matrix()
        report(f"bez kanału: {ch}", Sc, camp, op)
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import squareform

    truth_c = [truth[i]["kampania"] for i in ids]; truth_o = [truth[i]["operator"] for i in ids]
    Z = linkage(squareform(1 - S, checks=False), method="average")
    print("\n== grupowanie (średnie łączenie), cięcie przy wyniku S >= próg; wyniki dla całego przeglądu, bez wyboru najlepszego")
    for t in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9):
        lab = fcluster(Z, 1 - t, criterion="distance")
        print(f"  próg={t:.1f} grup={len(set(lab)):>2}  ARI(kampania)={adjusted_rand_score(truth_c, lab):.3f}  "
              f"ARI(operator)={adjusted_rand_score(truth_o, lab):.3f}")
    print("\n== poziom operatora: wynik tylko ze śladów infrastruktury (bez tekstu), osobno od poziomu kampanii")
    Wi = {k: (0.0 if k == "text" else 1.0) for k in DEFAULT_WEIGHTS}
    So, _ = Corpus(cases, V, Wi, rotating={"host", "pixel"}).matrix()
    report("wynik operatora (ślady)", So, camp, op)
    Zo = linkage(squareform(1 - So, checks=False), method="average")
    for t in (0.2, 0.3, 0.4, 0.5, 0.6, 0.7):
        lab = fcluster(Zo, 1 - t, criterion="distance")
        print(f"  próg={t:.1f} grup={len(set(lab)):>2}  ARI(operator)={adjusted_rand_score(truth_o, lab):.3f}  "
              f"ARI(kampania)={adjusted_rand_score(truth_c, lab):.3f}")
    # przykład przesłanek
    i, j = 0, 1
    r = full.score(cases[i], cases[j])
    print(f"\nprzykład {ids[i]} vs {ids[j]}: S={r.value:.3f} dowód={r.evidence:.2f} kanały={r.channels} wspólne={r.shared}")


if __name__ == "__main__":
    main()
