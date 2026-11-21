"""Ablacja kanałów: ile traci jakość grupowania po wyłączeniu każdej grupy dowodów (pokazuje, które kanały naprawdę niosą wynik).

Pary liczymy raz (z pełnymi dowodami), a dla każdego wariantu filtrujemy dowody po kanale i przeliczamy wynik i relację.
Metryki: B-cubed (kampania i sieć) względem prawdy oraz liczba negatywów doklejonych do oszustw.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .evaluate import bcubed
from .material import Material
from .similar import Pair, all_pairs, campaigns, combine, relation

GROUPS = {
    "śledzenie (piksel, id reklamy)": {"śledzenie"},
    "domena": {"domena"},
    "adres (TDS, ścieżki, usługi)": {"adres"},
    "tekst (TF-IDF)": {"tekst"},
    "semantyka": {"semantyka"},
    "obraz": {"obraz"},
    "szablon strony": {"szablon strony"},
    "osoby i produkt": {"osoby", "produkt", "reklamodawca"},
    "infrastruktura": {"infrastruktura", "przekierowania"},
}


def _rescore(pairs: list[Pair], drop: set[str]) -> list[Pair]:
    out = []
    for p in pairs:
        ev = [e for e in p.evidence if e.channel not in drop]
        out.append(Pair(a=p.a, b=p.b, score=combine(ev), relation=relation(ev, p.text_sim if "tekst" not in drop else 0.0),
                        text_sim=p.text_sim, evidence=ev))
    return out


def _metrics(materials: list[Material], pairs: list[Pair], truth: dict, thr: float) -> dict:
    row = {}
    for level, key in (("kampania", "kampania"), ("sieć", "operator")):
        groups = campaigns(materials, pairs, thr, level)
        pred = {m: g.id for g in groups for m in g.members}
        gold = {m: v[key] for m, v in truth.items()}
        r = bcubed(pred, gold)
        row[f"{level} F1"] = r["f1"]
        row[f"{level} P"] = r["precision"]
        row[f"{level} R"] = r["recall"]
    groups = campaigns(materials, pairs, thr, "sieć")
    neg = 0
    for g in groups:
        kinds = [truth[m]["rodzaj"] for m in g.members if m in truth]
        if "negatyw" in kinds and "oszustwo" in kinds:
            neg += kinds.count("negatyw")
    row["negatywy doklejone"] = neg
    return row


def run(materials: list[Material], truth_path: Path, thr: float = 0.7) -> pd.DataFrame:
    truth = json.loads(Path(truth_path).read_text(encoding="utf-8"))
    pairs = all_pairs(materials)
    rows = [{"wariant": "wszystkie kanały", **_metrics(materials, pairs, truth, thr)}]
    for name, chans in GROUPS.items():
        rows.append({"wariant": f"bez: {name}", **_metrics(materials, _rescore(pairs, chans), truth, thr)})
    all_channels = {e.channel for p in pairs for e in p.evidence}
    for ch in sorted(all_channels):  # każdy kanał osobno: jak działałby sam
        rows.append({"wariant": f"tylko: {ch}", **_metrics(materials, _rescore(pairs, all_channels - {ch}), truth, thr)})
    return pd.DataFrame(rows)
