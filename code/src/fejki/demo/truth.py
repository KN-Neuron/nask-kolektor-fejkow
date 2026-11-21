"""Porównanie grup z prawdą (zbiór syntetyczny ma `prawda.json`: kampania, operator, rodzaj każdego materiału).

Dla zbioru organizatora prawdy nie ma, więc te liczby pokazujemy tylko tam, gdzie plik istnieje.
"""
from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path

from sklearn.metrics import adjusted_rand_score

from fejki.demo.similar import Campaign


def load(data_dir: str | Path | None) -> dict[str, dict] | None:
    p = Path(data_dir or "") / "prawda.json"
    return json.loads(p.read_text(encoding="utf-8")) if data_dir and p.is_file() else None


def score(groups: list[Campaign], truth: dict[str, dict], key: str) -> dict:
    """Zgodność grup z prawdą na poziomie `key` („kampania” albo „operator”).

    - precyzja par: z par, które połączyliśmy, ile naprawdę jest razem (mało fałszywych połączeń);
    - czułość par: z par, które naprawdę są razem, ile połączyliśmy (mało przeoczeń);
    - trafione grupy: ile prawdziwych grup odtworzyliśmy dokładnie (ani materiału za dużo, ani za mało);
    - negatywy osobno: ile materiałów spoza kampanii zostało samych (zdolność do niełączenia).
    """
    pred = {m: g.id for g in groups for m in g.members if m in truth}
    ids = sorted(pred)
    true = {m: truth[m][key] for m in ids}
    tp = fp = fn = 0
    for a, b in combinations(ids, 2):
        same_p, same_t = pred[a] == pred[b], true[a] == true[b]
        tp += same_p and same_t
        fp += same_p and not same_t
        fn += same_t and not same_p
    tgroups: dict[str, set] = {}
    for m, t in true.items():
        tgroups.setdefault(t, set()).add(m)
    pgroups = {frozenset(m for m in g.members if m in truth) for g in groups}
    real = [s for s in tgroups.values() if len(s) > 1]
    neg = [m for m in ids if truth[m].get("rodzaj") != "oszustwo"]
    size = {m: len(g.members) for g in groups for m in g.members}
    return {
        "precyzja": tp / (tp + fp) if tp + fp else 1.0,
        "czułość": tp / (tp + fn) if tp + fn else 1.0,
        "ARI": adjusted_rand_score([true[m] for m in ids], [pred[m] for m in ids]) if ids else 0.0,
        "trafione": sum(frozenset(s) in pgroups for s in real),
        "grup": len(real),
        "negatywy_osobno": sum(size[m] == 1 for m in neg),
        "negatywów": len(neg),
    }
