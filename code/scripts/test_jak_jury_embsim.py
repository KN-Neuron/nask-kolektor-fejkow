"""Test „jak jury” dla demonstratora embsim (`make demo`): cienki skrypt nad `embsim.jury` (opis w jego docstringu).

Uruchomienie (z katalogu code/): PYTHONPATH=src .venv/bin/python scripts/test_jak_jury_embsim.py [--campaign 0.95]
(domyślnie próg z config/embsim/demo_calibration.json, jak w interfejsie) → raport w artifacts/jury/raport_embsim.md
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from embsim import jury as J

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "jury"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--campaign", type=float, default=None, help="próg kampanii (domyślnie z konfiguracji, jak w interfejsie)")
    ap.add_argument("--out", default="raport_embsim.md")
    a = ap.parse_args()
    t0 = time.time()
    r = J.run_all(a.campaign)
    md = ["# Test jak jury: demonstrator embsim", "", f"Próg kampanii {r['próg']}; czas {time.time() - t0:.0f} s.", "",
          "## Podsumowanie wg kryteriów walidacji (opis wyzwania, pkt 6)", "", J.table(__import__("pandas").DataFrame(r["podsumowanie"])), ""]
    for k, title in (("A", "A. NASK, ukryty przypadek"), ("B", "B. Format, braki, duplikat"), ("C", "C. Syntetyka jako ukryty zbiór")):
        if r[k] is not None:
            md += [f"## {title}: {J.score(r[k])}", "", J.table(r[k]), ""]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / a.out).write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
