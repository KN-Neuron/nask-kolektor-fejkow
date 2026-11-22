"""Pełny zestaw metryk dla stron (HTML, HAR, zrzuty): NASK-10 (nasz odczyt) i syntetyka v1 (prawda z generatora).

Uruchomienie (z katalogu code/, ok. 10 s; infra tylko z pamięci podręcznej):
    PYTHONPATH=src .venv/bin/python scripts/metryki.py            # -> artifacts/metryki/metryki.md i metryki.json

Prawda: NASK kampanie {1,2} i {48,61}, operator (sieć) {1,2,3,48,61}, reszta osobno (nasz odczyt, nie etykiety organizatora); syntetyka:
`kampania` i `operator` z prawda.json (negatywy każdy osobno). Opis metryk: README, sekcja „Metryki”.

1. Wyszukiwanie (galeria = reszta zbioru, kolejność wg wyniku kampanii / operatora): trafność@1, @3, @5 i MRR dla materiałów, które mają
   w galerii parę z tej samej kampanii (operatora).
2. Podobieństwo par: wynik kampanii każdej pary (z obu stron, średnia), AUROC i AP dla „ta sama kampania”; to samo dla wyniku operatora
   i „ten sam operator”; najlepsze F1 po progu i F1 przy progu z konfiguracji.
3. Decyzja „znana kampania” przy progu z konfiguracji (z wyników `scripts/prog_kampanii.py`, jeśli są): precyzja, czułość, F1,
   swoistość, zrównoważona trafność; przedziały 95% bootstrap po podmiotach.
4. Grupowanie (galeria z całego zbioru, drugi przebieg `regroup`, jak w interfejsie): precyzja, czułość i F1 par, ARI, AMI, V-measure,
   B-cubed (P, R, F1), liczba dokładnie odtworzonych grup, dla kampanii i operatora.
"""
from __future__ import annotations

import json
import time
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import numpy as np
from sklearn.metrics import (
    adjusted_mutual_info_score,
    adjusted_rand_score,
    average_precision_score,
    roc_auc_score,
    v_measure_score,
)

from embsim import infra
from embsim import jury as J
from embsim.api import demo_thresholds

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "metryki"
PROG = Path(__file__).resolve().parents[1] / "artifacts" / "prog" / "wyniki.json"
NET = {"1", "2", "3", "48", "61"}
NASK_CAMP = {"1": "nA", "2": "nA", "48": "nB", "61": "nB"}
THR = demo_thresholds().get("campaign", 0.70)


def truth() -> dict[str, dict]:
    """id -> {zbiór, kampania, operator, podmiot}."""
    t = {}
    for d in J._dirs(J.NASK):
        t[d.name] = {"zbiór": "nask", "dir": d, "kampania": NASK_CAMP.get(d.name, "n" + d.name),
                     "operator": "nSIEĆ" if d.name in NET else "n" + d.name}
    pr = json.loads((J.SYNTH / "prawda.json").read_text(encoding="utf-8"))
    for m, v in pr.items():
        t[m] = {"zbiór": "synth", "dir": J.SYNTH / m, "kampania": "s" + v["kampania"], "operator": "s" + v["operator"]}
    return t


# ---------------------------------------------------------------------------------------------------------------- 1 i 2
def pair_scores(ids: list[str], T: dict) -> tuple[dict, dict, object]:
    """Wynik kampanii i operatora dla każdej pary: galeria z całego zbioru, zapytanie z wykluczeniem samego siebie (jak `regroup`)."""
    g = J.build([T[i]["dir"] for i in ids])
    raw: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
    per_query: dict[str, list] = {}
    for it in g.items:
        q = it["case"]
        d = g.query(q, len(ids), exclude_id=q.id)
        per_query[q.id] = [(m.id, m.campaign_score, m.operator_score) for m in d.matches]
        for m in d.matches:
            raw[tuple(sorted((q.id, m.id)))].append((m.campaign_score, m.operator_score))
    pairs = {k: (float(np.mean([a for a, _ in v])), float(np.mean([b for _, b in v]))) for k, v in raw.items()}
    return pairs, per_query, g


def retrieval(per_query: dict, T: dict, key: str, which: int) -> dict:
    ranks = []
    for q, ms in per_query.items():
        mates = {m for m, *_ in ms if T[m][key] == T[q][key]}
        if not mates:
            continue
        order = [m for m, *_ in sorted(ms, key=lambda x: -x[which])]
        ranks.append(next(i for i, m in enumerate(order, 1) if m in mates))
    r = np.array(ranks)
    return {"zapytań": len(r), "trafność@1": float(np.mean(r <= 1)), "trafność@3": float(np.mean(r <= 3)),
            "trafność@5": float(np.mean(r <= 5)), "MRR": float(np.mean(1 / r))}


def pair_metrics(pairs: dict, T: dict, key: str, which: int, thr: float | None) -> dict:
    ks = sorted(pairs)
    y = np.array([T[a][key] == T[b][key] for a, b in ks])
    s = np.array([pairs[k][which] for k in ks])
    out = {"par": len(ks), "par pozytywnych": int(y.sum())}
    if y.any() and (~y).any():
        out |= {"AUROC": float(roc_auc_score(y, s)), "AP": float(average_precision_score(y, s))}
        best = (0.0, None)
        for t in np.unique(s):
            p = s >= t
            tp = (p & y).sum()
            f1 = 2 * tp / (p.sum() + y.sum()) if p.sum() + y.sum() else 0
            best = max(best, (float(f1), float(t)), key=lambda x: x[0])
        out |= {"najlepsze F1": best[0], "przy progu": best[1]}
        if thr is not None:
            p = s >= thr
            tp = int((p & y).sum())
            out |= {f"precyzja przy {thr}": tp / p.sum() if p.sum() else 1.0, f"czułość przy {thr}": tp / y.sum(),
                    f"F1 przy {thr}": 2 * tp / (p.sum() + y.sum())}
        pos, neg = s[y], s[~y]
        out |= {"średni wynik: te same": float(pos.mean()), "średni wynik: różne": float(neg.mean()),
                "najwyższy wynik różnych": float(neg.max()), "najniższy wynik tych samych": float(pos.min())}
    return out


# ---------------------------------------------------------------------------------------------------------------- 3
def decisions(rows: list, T: dict, thr: float, layout: str, boot: int = 1000) -> dict:
    """rows: (układ, zbiór, id, format, pozytyw, dobra grupa, wynik) z prog_kampanii.py."""
    rs = [r for r in rows if r[0] == layout]

    def m(sub):
        tp = sum(r[4] and r[5] and r[6] >= thr for r in sub)
        fp = sum(r[6] >= thr and not (r[4] and r[5]) for r in sub)
        P = sum(r[4] for r in sub)
        N = len(sub) - P
        tn = sum((not r[4]) and r[6] < thr for r in sub)
        prec = tp / (tp + fp) if tp + fp else 1.0
        rec = tp / P if P else 1.0
        spec = tn / N if N else 1.0
        return {"pytań": len(sub), "precyzja": prec, "czułość": rec, "F1": 2 * prec * rec / (prec + rec) if prec + rec else 0.0,
                "swoistość": spec, "zrównoważona trafność": (rec + spec) / 2, "fałszywe połączenia": fp}

    out = m(rs)
    subj = defaultdict(list)
    for r in rs:
        subj[T[r[2]]["operator"]].append(r)
    keys = list(subj)
    rng = np.random.default_rng(0)
    bs = [m([r for k in rng.choice(keys, len(keys)) for r in subj[k]]) for _ in range(boot)]
    for k in ("precyzja", "czułość", "F1", "zrównoważona trafność"):
        lo, hi = np.percentile([b[k] for b in bs], [2.5, 97.5])
        out[k + " 95%"] = [float(lo), float(hi)]
    return out


# ---------------------------------------------------------------------------------------------------------------- 4
def clustering(g, T: dict, key: str, field: str) -> dict:
    ids = [it["case"].id for it in g.items]
    pred = {it["case"].id: it[field] for it in g.items}
    true = {i: T[i][key] for i in ids}
    tp = fp = fn = 0
    for a, b in combinations(ids, 2):
        sp, st = pred[a] == pred[b], true[a] == true[b]
        tp += sp and st
        fp += sp and not st
        fn += st and not sp
    pg, tg = defaultdict(set), defaultdict(set)
    for i in ids:
        pg[pred[i]].add(i)
        tg[true[i]].add(i)
    bp = np.mean([len(pg[pred[i]] & tg[true[i]]) / len(pg[pred[i]]) for i in ids])
    br = np.mean([len(pg[pred[i]] & tg[true[i]]) / len(tg[true[i]]) for i in ids])
    real = [s for s in tg.values() if len(s) > 1]
    pp = tp / (tp + fp) if tp + fp else 1.0
    pr = tp / (tp + fn) if tp + fn else 1.0
    yt, yp = [true[i] for i in ids], [pred[i] for i in ids]
    return {"materiałów": len(ids), "grup prawdziwych (≥2)": len(real), "grup przewidzianych": len(pg),
            "odtworzone dokładnie": sum(frozenset(s) in {frozenset(v) for v in pg.values()} for s in real),
            "precyzja par": pp, "czułość par": pr, "F1 par": 2 * pp * pr / (pp + pr) if pp + pr else 0.0,
            "ARI": float(adjusted_rand_score(yt, yp)), "AMI": float(adjusted_mutual_info_score(yt, yp)),
            "V-measure": float(v_measure_score(yt, yp)), "B-cubed P": float(bp), "B-cubed R": float(br),
            "B-cubed F1": float(2 * bp * br / (bp + br))}


# ---------------------------------------------------------------------------------------------------------------- raport
def fmt(v):
    if isinstance(v, float):
        return f"{v:.3f}".replace(".", ",")
    if isinstance(v, list):
        return "[" + "; ".join(fmt(x) for x in v) + "]"
    return str(v)


def table(d: dict[str, dict]) -> str:
    cols = list(dict.fromkeys(k for v in d.values() for k in v))
    lines = ["| | " + " | ".join(cols) + " |", "|---" * (len(cols) + 1) + "|"]
    lines += [f"| {name} | " + " | ".join(fmt(v.get(c, "–")) for c in cols) + " |" for name, v in d.items()]
    return "\n".join(lines)


def main() -> None:
    t0 = time.time()
    T = truth()
    res: dict = {"próg": THR}
    with infra.forced("cache"):
        sets = {"NASK": [i for i in T if T[i]["zbiór"] == "nask"], "syntetyka": [i for i in T if T[i]["zbiór"] == "synth"]}
        for name, ids in sets.items():
            pairs, per_query, g = pair_scores(ids, T)
            res[name] = {
                "wyszukiwanie": {"kampania (wynik kampanii)": retrieval(per_query, T, "kampania", 1),
                                 "operator (wynik operatora)": retrieval(per_query, T, "operator", 2)},
                "pary": {"ta sama kampania (wynik kampanii)": pair_metrics(pairs, T, "kampania", 0, THR),
                         "ten sam operator (wynik operatora)": pair_metrics(pairs, T, "operator", 1, demo_thresholds().get("operator", 0.25))},
                "grupowanie": {"kampanie": clustering(g, T, "kampania", "group"), "operatorzy": clustering(g, T, "operator", "operator")},
            }
            print(name, "gotowe", round(time.time() - t0), "s", flush=True)
    if PROG.exists():
        rows = json.loads(PROG.read_text(encoding="utf-8"))
        res["decyzje"] = {lay: decisions(rows, T, THR, lay) for lay in ("jury", "pełna", "mieszane")}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "metryki.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    md = [f"# Metryki demonstratora (strony), próg kampanii {fmt(THR)}", ""]
    for name in ("NASK", "syntetyka"):
        r = res[name]
        md += [f"## {name}", "", "### Wyszukiwanie najbliższego materiału", "", table(r["wyszukiwanie"]), "",
               "### Podobieństwo par", "", table(r["pary"]), "", "### Grupowanie (galeria z całego zbioru, drugi przebieg)", "",
               table(r["grupowanie"]), ""]
    if "decyzje" in res:
        md += ["## Decyzja „znana kampania” (układy z scripts/prog_kampanii.py; 95% bootstrap po podmiotach)", "", table(res["decyzje"]), ""]
    (OUT / "metryki.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))
    print(f"\n{time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
