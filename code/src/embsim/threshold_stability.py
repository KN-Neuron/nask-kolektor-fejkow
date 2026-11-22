"""Stabilność progu kampanii: czy próg dobrany na tych samych materiałach, na których go mierzymy, zachowuje się poza nimi?

    python -m embsim.threshold_stability

Zbiera wyniki kampanii z testu na zbiorze ukrytym (A: NASK ukryty po kolei, B: inne formaty, C: syntetyka) i dla każdego materiału zna oczekiwaną
decyzję „znana kampania” albo nie. Liczy trafność przy progu z konfiguracji, zrównoważoną trafność dla siatki progów (plateau optimum) oraz
leave-one-out: próg dobierany na wszystkich materiałach poza jednym i sprawdzany na tym jednym. Oczekiwania to nasz odczyt danych NASK, nie etykiety.
"""
from __future__ import annotations

import numpy as np

from . import jury


def collect() -> list[tuple[str, float, bool]]:
    t = jury.run_all()
    items = []
    for _, r in t["A"].iterrows():
        items.append(("A", r["wynik kampanii"], r["oczekiwane"] == "kampania"))
    for _, r in t["B"].iterrows():
        items.append(("B-zrzut" if "zrzut (OCR)" in r["wejście"] and "znanej" not in r["wejście"] else "B", r["wynik kampanii"], True))
    for _, r in t["C"].iterrows():
        items.append(("C", r["wynik kampanii"], r["oczekiwane"] == "kampania"))
    return items


def run(items, label):
    sc = np.array([i[1] for i in items]); y = np.array([i[2] for i in items])
    grid = np.round(np.arange(0.30, 0.96, 0.01), 2)
    def bal(t, idx):
        p = sc[idx] >= t; yy = y[idx]
        return (p[yy].mean() if yy.any() else 1) * 0.5 + ((~p[~yy]).mean() if (~yy).any() else 1) * 0.5
    allidx = np.arange(len(items))
    full = np.array([bal(t, allidx) for t in grid]); best = full.max(); plateau = grid[full >= best - 1e-9]
    loo_hits = 0; chosen = []
    for k in allidx:
        tr = np.delete(allidx, k)
        cur = np.array([bal(t, tr) for t in grid]); pl = grid[cur >= cur.max() - 1e-9]; t = float(np.median(pl)); chosen.append(t)
        loo_hits += int((sc[k] >= t) == y[k])
    neg_max = sc[~y].max(); pos_min_all = sc[y].min()
    print(f"{label}: n={len(items)} (pozytywnych {y.sum()}), najlepsza zrównoważona trafność {best:.3f} na progach {plateau.min():.2f}–{plateau.max():.2f}; "
          f"leave-one-out: trafność {loo_hits/len(items):.3f}, progi wybrane {min(chosen):.2f}–{max(chosen):.2f}; najsilniejszy negatyw {neg_max:.2f}; "
          f"trafność przy 0,62: {np.mean((sc>=0.62)==y):.3f}")

def main() -> None:
    from .runinfo import provenance

    print("pochodzenie:", provenance("strony"))
    items = collect()
    run(items, "wszystko")
    run([i for i in items if i[0] != "B-zrzut"], "bez zrzutów bez tekstu (B)")
    run([i for i in items if i[0] in ("A", "C")], "tylko A i C")


if __name__ == "__main__":
    main()
