"""Dobór progu kampanii dla stron (HTML, HAR, zrzuty) z podziałem po PODMIOTACH. Opis i wyniki: docs/POMIAR_RYGOR.md §3a.

Uruchomienie (z katalogu code/, ok. 10 min; infra tylko z pamięci podręcznej, bez zapytań sieciowych):
    PYTHONPATH=src .venv/bin/python scripts/prog_kampanii.py zbierz      # wyniki kampanii -> artifacts/prog/wyniki.json
    PYTHONPATH=src .venv/bin/python scripts/prog_kampanii.py dobierz     # dobór i porównanie progów stałych

Trzy układy galerii (rozkład wyniku zależy od składu galerii: idf śladów, tło tekstu), w każdym pytanie = najlepsze dopasowanie:
  * „jury”: galeria jak w teście jury (A: NASK ukryty po kolei, C: zbiór ukryty syntetyki);
  * „pełna”: zostaw-jeden-materiał, galeria = cała reszta (NASK + syntetyka);
  * „mieszane”: losowe galerie (każdy materiał z prawdopodobieństwem U(0,4; 0,95)), pytania o materiały spoza galerii w losowym formacie
    (komplet / sam HTML / sam HAR). HAR-y syntetyki to atrapy (ok. 600 B, same adresy), więc pytania samym HAR-em syntetyki pomijamy.
Pozytyw = w galerii jest materiał tej samej kampanii; poprawnie, gdy wynik >= próg i najbliższy jest z tej kampanii. Negatyw: poprawnie, gdy < próg.

Podmiot (jednostka podziału): operator syntetyki z prawda.json (każdy negatyw osobno); w NASK sieć {1,2,3,48,61} (wspólna infrastruktura)
jako jeden podmiot, pozostałe przypadki osobno. Dobór zagnieżdżony: próg = środek najszerszego przedziału z maksymalną zrównoważoną
trafnością na podmiotach treningowych, ocena na odłożonych (zostaw-jeden-podmiot i 200 podziałów 70/30). Progi stałe oceniane na tych samych pytaniach.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "prog" / "wyniki.json"
NET = {"1", "2", "3", "48", "61"}
NASK_CAMP = {"1": "nA", "2": "nA", "48": "nB", "61": "nB"}
FIXED = (0.62, 0.665, 0.70, 0.725, 0.745)
GRID = np.round(np.arange(0.50, 0.851, 0.005), 3)


def collect(trials: int = 105, per_trial: int = 8, seed: int = 0) -> None:
    from embsim import analyze as A
    from embsim import infra
    from embsim import jury as J

    truth = json.loads((J.SYNTH / "prawda.json").read_text(encoding="utf-8"))
    items = [(d, "nask", NASK_CAMP.get(d.name, "n" + d.name)) for d in J._dirs(J.NASK)]
    items += [(J.SYNTH / m, "synth", "s" + truth[m]["kampania"]) for m in sorted(truth)]
    fmt = {"komplet": lambda f: True, "sam HTML": lambda f: f.suffix.lower() in {".html", ".htm"},
           "sam HAR": lambda f: f.suffix.lower() == ".har"}
    rows = []   # (układ, zbiór, id, format, pozytyw, dobra grupa, wynik)

    def ask(layout, g, gal, d, src, camp, form="komplet"):
        files = J.uploaded(d, fmt[form])
        if not files:
            return
        m = g.query(A.case_from_inputs(files, ocr=False)[0], 1).matches[0]
        camp_of = {x.name: c for x, _, c in gal}
        rows.append((layout, src, d.name, form, camp in camp_of.values(), camp_of.get(m.id) == camp, float(m.campaign_score)))

    with infra.forced("cache"):
        r = J.run_all()
        for _, x in r["A"].iterrows():
            rows.append(("jury", "nask", str(x["przypadek"]), "komplet", x["oczekiwane"] == "kampania", bool(x["_grupa"]), float(x["wynik kampanii"])))
        for _, x in r["C"].iterrows():
            rows.append(("jury", "synth", str(x["materiał"]), "komplet", x["oczekiwane"] == "kampania", bool(x["_grupa"]), float(x["wynik kampanii"])))
        for it in items:
            gal = [x for x in items if x is not it]
            ask("pełna", J.build([x for x, _, _ in gal]), gal, *it)
        rnd = random.Random(seed)
        for _ in range(trials):
            keep = rnd.uniform(0.4, 0.95)
            gal = [x for x in items if rnd.random() < keep]
            rest = [x for x in items if x not in gal]
            if len(gal) < 3 or not rest:
                continue
            g = J.build([x for x, _, _ in gal])
            for d, src, camp in rnd.sample(rest, min(per_trial, len(rest))):
                form = rnd.choices(list(fmt), weights=(2, 1, 1))[0]
                if not (src == "synth" and form == "sam HAR"):
                    ask("mieszane", g, gal, d, src, camp, form)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    print(f"zapisano {len(rows)} pytań -> {OUT}")


def subject(src: str, mid: str, truth: dict) -> str:
    if src == "synth":
        return truth[mid]["operator"]
    return "NASK-sieć" if mid in NET else f"NASK-{mid}"


def ba(rs, t=None, ts=None) -> float:
    ok = [((r[3] >= (ts[i] if ts else t)) and r[2]) if r[1] else (r[3] < (ts[i] if ts else t)) for i, r in enumerate(rs)]
    pos = [o for o, r in zip(ok, rs) if r[1]]
    neg = [o for o, r in zip(ok, rs) if not r[1]]
    return float(np.nanmean([np.mean(pos) if pos else np.nan, np.mean(neg) if neg else np.nan]))


def choose(rs) -> float:
    v = np.array([ba(rs, t) for t in GRID])
    top = np.flatnonzero(np.isclose(v, v.max()))
    runs = np.split(top, np.flatnonzero(np.diff(top) > 1) + 1)
    run = max(runs, key=len)
    return float(GRID[run[len(run) // 2]])


def select() -> None:
    from embsim import jury as J

    truth = json.loads((J.SYNTH / "prawda.json").read_text(encoding="utf-8"))
    rows = json.loads(OUT.read_text(encoding="utf-8"))
    best = {}
    for lay in ("jury", "pełna", "mieszane"):
        rs = [(subject(r[1], r[2], truth), r[4], r[5], r[6]) for r in rows if r[0] == lay]
        subs = sorted({r[0] for r in rs})
        ts, chosen = [0.0] * len(rs), []
        for s in subs:
            t = choose([r for r in rs if r[0] != s]); chosen.append(t)
            for i, r in enumerate(rs):
                if r[0] == s:
                    ts[i] = t
        fixed = {t: ba(rs, t) for t in FIXED}
        best[lay] = fixed
        print(f"\n{lay}: {len(rs)} pytań, {sum(r[1] for r in rs)} pozytywów, {len(subs)} podmiotów")
        print(f"  zostaw-jeden-podmiot: progi {min(chosen):.3f}–{max(chosen):.3f}, zrównoważona trafność na odłożonych {ba(rs, ts=ts):.3f}")
        print("  stałe: " + ", ".join(f"{t}: {v:.3f}" for t, v in fixed.items()))
    print("\nnajwiększa strata do najlepszego progu stałego w układzie (minimaks):")
    for t in FIXED:
        print(f"  {t}: {max(max(best[l].values()) - best[l][t] for l in best):.3f}")


if __name__ == "__main__":
    {"zbierz": collect, "dobierz": select}[sys.argv[1] if len(sys.argv) > 1 else "dobierz"]()
