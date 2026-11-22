"""Wbudowany przykład dla interfejsu: mały świat syntetyczny (generator `synth2`), z którego część materiałów jest ukryta przed galerią.

Galeria to znane incydenty: 14 oszustw (po 3 warianty w kampaniach O2-K1, O2-K2, O3-K1, O3-K2 i 2 warianty O1-K1), bez legalnych stron.
Ukryte są trzy materiały, po jednym na każdy możliwy werdykt:
  wariant   trzeci wariant znanej kampanii O1-K1               -> oczekiwane: znana kampania
  operator  materiał nowej kampanii O1-K2 tego samego operatora -> oczekiwane: znany operator, nowa kampania
  obcy      legalna strona z tymi samymi osobami i trackerami   -> oczekiwane: nowy wzorzec

Materiały są zapisane tak jak dane z prawdziwego zgłoszenia (HTML + HAR w folderze), więc przykład przechodzi przez ten sam kod
wczytywania co własne dane użytkownika. To dane syntetyczne i tak są oznaczone w interfejsie.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from .synth2 import generate

SEED = 11

EXAMPLES = {
    "wariant": {
        "tytuł": "Nowy wariant znanej kampanii",
        "opis": "Trzeci wariant oferty, której dwa warianty już mamy w galerii: inny tekst i inna domena lądowania, ten sam zestaw zasobów strony.",
        "oczekiwane": "znana kampania",
    },
    "operator": {
        "tytuł": "Nowa kampania znanego operatora",
        "opis": "Inna oferta i inni bohaterowie, ale strona zbudowana na tej samej infrastrukturze co kampanie jednego operatora z galerii.",
        "oczekiwane": "znany operator, nowa kampania",
    },
    "obcy": {
        "tytuł": "Obcy materiał (legalna strona)",
        "opis": "Strona o tych samych osobach i z tymi samymi trackerami co oszustwa, ale bez ich infrastruktury i przekazu.",
        "oczekiwane": "nowy wzorzec (nie doklejamy do żadnej grupy)",
    },
}


def prepare(root: Path, seed: int = SEED) -> dict:
    """Generuje świat i dzieli go na galerię oraz trzy materiały zapytań. Zwraca ścieżki i prawdę generatora."""
    world = root / "swiat"
    generate(world, seed=seed, n_operators=3, campaigns_per_op=2, variants=3, missing_rate=0.0)
    truth = json.loads((world / "prawda.json").read_text(encoding="utf-8"))
    ids = sorted(truth)
    members: dict[str, list[str]] = {}
    for i in ids:
        members.setdefault(truth[i]["kampania"], []).append(i)
    queries = {"wariant": members["O1-K1"][-1], "operator": members["O1-K2"][0],
               "obcy": next(i for i in ids if truth[i]["rodzaj"] == "negatyw")}
    hidden = set(queries.values()) | set(members["O1-K2"])
    gal = root / "galeria"
    gal.mkdir()
    for i in ids:
        if i not in hidden and truth[i]["rodzaj"] != "negatyw":        # galeria to znane incydenty, bez legalnych stron
            shutil.copytree(world / i, gal / i)
    return {"galeria": gal, "zapytania": {k: world / v for k, v in queries.items()}, "prawda": truth}


def uploaded(case_dir: Path) -> list[tuple[str, bytes]]:
    """Pliki, które człowiek wskazałby w oknie wgrywania (bez folderów zasobów `*_files`)."""
    return [(f.name, f.read_bytes()) for f in sorted(case_dir.rglob("*"))
            if f.is_file() and not any(p.endswith("_files") for p in f.relative_to(case_dir).parts[:-1])]
