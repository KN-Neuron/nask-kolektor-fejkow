"""Testy zachowania na zbiorze bez etykiet organizatora.

1. Pomiń-jeden: każdy przypadek usuwamy ze zbioru, budujemy grupy z reszty i dopasowujemy go jako nowy. Sprawdzamy, czy trafia
   tam, gdzie przy pełnym zbiorze (spójność) i czy przypadki pojedyncze zostają „nowym wzorcem” (nie są doklejane na siłę).
2. Braki danych: ten sam przypadek wczytany tylko z części plików (sam HTML, sam HAR, same zrzuty). Sprawdzamy, czy nadal trafia
   do tej samej grupy, a jeśli nie, którego kanału zabrakło.

Uwaga: nie mamy etykiet kampanii od organizatora. „Prawda” to wynik na pełnym zbiorze, więc test mierzy stabilność i odporność,
nie trafność względem ich podziału.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .material import HTML_EXT, IMG_EXT, VID_EXT, build_material, is_har, load_persons
from .similar import all_pairs, campaigns, match


def _group_of(mid: str, groups) -> set[str]:
    for g in groups:
        if mid in g.members:
            return set(g.members) - {mid}
    return set()


def leave_one_out(materials, thr: float = 0.7) -> pd.DataFrame:
    pairs = all_pairs(materials)
    full_c = campaigns(materials, pairs, thr, "kampania")
    full_n = campaigns(materials, pairs, thr, "sieć")
    rows = []
    for m in materials:
        rest = [x for x in materials if x.id != m.id]
        rp = all_pairs(rest)
        rc, rn = campaigns(rest, rp, thr, "kampania"), campaigns(rest, rp, thr, "sieć")
        r = match(m, rest, rc, rn, thr=thr)
        exp_c, exp_n = _group_of(m.id, full_c), _group_of(m.id, full_n)
        got_c = set(next((c.members for c in rc if c.id == r.best_campaign), []))
        top = r.ranking[0] if r.ranking else None
        got_n = set(next((n.members for n in rn if top and n.id == top.get("network")), [])) if top and top["score"] >= thr else set()
        rows.append({
            "przypadek": m.id,
            "oczekiwana kampania": ",".join(sorted(exp_c)) or "(nowa)",
            "decyzja": r.decision,
            "kampania OK": (got_c == exp_c) if exp_c else (r.best_campaign is None),
            "sieć OK": (bool(got_n & exp_n) if exp_n else not got_n),
            "najlepszy wynik": r.best_score,
        })
    return pd.DataFrame(rows)


def partial_inputs(case_dirs: list[Path], materials, thr: float = 0.7, ocr: bool = False) -> pd.DataFrame:
    persons = load_persons()
    pairs = all_pairs(materials)
    nets = campaigns(materials, pairs, thr, "sieć")
    rows = []
    for d in case_dirs:
        files = [p for p in d.rglob("*") if p.is_file()]
        exp = _group_of(d.name, nets)
        if not exp:
            continue
        subsets = {
            "tylko HTML (z zasobami)": [f for f in files if f.suffix.lower() in HTML_EXT or "_files" in str(f)],
            "tylko HAR": [f for f in files if is_har(f)],
            "tylko zrzuty/nagrania": [f for f in files if (f.suffix.lower() in IMG_EXT | VID_EXT) and "_files" not in str(f)],
        }
        rest = [x for x in materials if x.id != d.name]
        rp = all_pairs(rest)
        rc, rn = campaigns(rest, rp, thr, "kampania"), campaigns(rest, rp, thr, "sieć")
        for name, fs in subsets.items():
            if not fs:
                rows.append({"przypadek": d.name, "wejście": name, "wynik": "brak takich plików w przypadku", "trafia do swojej sieci": None,
                             "najlepszy wynik": None})
                continue
            m = build_material(f"{d.name}-czesc", f"{d.name} ({name})", "folder", files=fs, ocr=ocr, persons=persons, base=d)
            r = match(m, rest, rc, rn, thr=thr)
            top = r.ranking[0] if r.ranking else None
            got = set(next((n.members for n in rn if top and n.id == top.get("network")), [])) if top else set()
            ok = bool(top and top["score"] >= 0.4 and got & exp)
            rows.append({"przypadek": d.name, "wejście": name, "wynik": r.decision, "trafia do swojej sieci": ok,
                         "najlepszy wynik": r.best_score})
    return pd.DataFrame(rows)
