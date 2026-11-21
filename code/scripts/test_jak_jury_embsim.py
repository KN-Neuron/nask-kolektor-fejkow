"""Test „jak jury” (opis wyzwania, pkt 6) dla demonstratora embsim (`make demo`, src/embsim/app.py).

Odtwarza to, co jury zrobi w interfejsie: buduje galerię z folderów przypadków („Dodaj przypadki z folderów”, bez OCR jak domyślnie),
potem każdy nowy materiał wgrywa jako pliki (HTML, HAR, zrzuty; bez folderów zasobów `_files`, bo uploader przyjmuje tylko pliki)
i czyta werdykt: znana kampania / znany operator, nowa kampania / nowy wzorzec.

  A. NASK, ukryty przypadek: galeria z 9 przypadków, dziesiąty jako nowy.
  B. Format i braki: sam HTML / sam HAR / sam zrzut (OCR) / ten sam materiał drugi raz.
  C. Syntetyka jako ukryty zbiór: trzeci materiał każdej kampanii, cała kampania O6-K2, 6 negatywów (prawda: data/synth/prawda.json).

Oczekiwania dla NASK to nasz odczyt danych (kampanie {1,2} i {48,61}, przypadek 3 w tej samej sieci), nie etykiety organizatora.
Uruchomienie (z katalogu code/): PYTHONPATH=src .venv/bin/python scripts/test_jak_jury_embsim.py [--campaign 0.95]
(domyślnie próg z config/embsim/demo_calibration.json, jak w interfejsie)
→ raport w artifacts/jury/raport_embsim.md
"""
from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path

import pandas as pd

from embsim import analyze as A
from embsim.api import Gallery, demo_thresholds

ROOT = Path(__file__).resolve().parents[2]
NASK = ROOT / "data" / "dane" / "do_udostępnienia"
SYNTH = ROOT / "data" / "synth"
OUT = ROOT / "code" / "artifacts" / "jury"

NASK_EXPECT = {"1": ("kampania", {"2"}), "2": ("kampania", {"1"}), "48": ("kampania", {"61"}), "61": ("kampania", {"48"}),
               "3": ("sieć", {"1", "2", "48", "61"})}
NASK_NET = {"1", "2", "3", "48", "61"}
KIND = {"znana_kampania": "kampania", "znany_operator_nowa_kampania": "sieć", "nowy_wzorzec": "nowy"}
IMG = {".png", ".jpg", ".jpeg", ".webp"}


def uploaded(case_dir: Path, pick=lambda f: True) -> list[tuple[str, bytes]]:
    """Pliki, które człowiek wybrałby w oknie wgrywania: wszystko poza folderami zasobów strony (`*_files`)."""
    return [(f.name, f.read_bytes()) for f in sorted(case_dir.rglob("*"))
            if f.is_file() and not any(p.endswith("_files") for p in f.relative_to(case_dir).parts[:-1]) and pick(f)]


def build(dirs: list[Path], cfg_thr: float | None) -> Gallery:
    g = Gallery(thresholds=demo_thresholds())  # jak w interfejsie
    if cfg_thr is not None:
        g.cfg.thresholds["campaign"] = cfg_thr
    with tempfile.TemporaryDirectory() as td:
        for d in dirs:
            (Path(td) / d.name).symlink_to(d, target_is_directory=True)
        A.build_from_folders(g, Path(td))
    return g


def verdict(got: str, via: str, want: str, ok_via: set[str], net: set[str] = frozenset()) -> str:
    if want == "nowy":
        return "OK" if got == "nowy" else "BŁĄD: połączono obce"
    if got == want and via in ok_via:
        return "OK"
    if got in ("kampania", "sieć") and via in ok_via:
        return "częściowo (dobra grupa, inny poziom)"
    if got == "sieć" and via in net:
        return "częściowo (dobra sieć)"
    if got == "kampania" and via in net:
        return "częściowo (zła kampania, dobra sieć)"
    return "BŁĄD: " + ("nie rozpoznano" if got == "nowy" else "zła grupa")


def ask(g: Gallery, files, ocr: bool = False) -> tuple[str, str, float, float]:
    case, _ = A.case_from_inputs(files, ocr=ocr)
    d = g.query(case, 5)
    if d.verdict == "znany_operator_nowa_kampania":  # werdykt sieci uzasadnia materiał z najwyższym wynikiem operatora
        via = max(d.matches, key=lambda m: m.operator_score).id
    else:
        via = d.matches[0].id if d.matches else ""
    return KIND.get(d.verdict, d.verdict), via, round(d.campaign_score, 3), round(d.operator_score, 3)


def test_a(thr) -> pd.DataFrame:
    cases = sorted((d for d in NASK.iterdir() if d.is_dir()), key=lambda d: (len(d.name), d.name))
    rows = []
    for held in cases:
        g = build([d for d in cases if d != held], thr)
        got, via, sc, so = ask(g, uploaded(held))
        want, ok_via = NASK_EXPECT.get(held.name, ("nowy", set()))
        rows.append({"przypadek": held.name, "oczekiwane": want, "wynik": got, "najbliższy": via, "wynik kampanii": sc,
                     "wynik operatora": so, "ocena": verdict(got, via, want, ok_via, NASK_NET)})
    return pd.DataFrame(rows)


def test_b(thr) -> pd.DataFrame:
    cases = sorted((d for d in NASK.iterdir() if d.is_dir()), key=lambda d: (len(d.name), d.name))
    rows = []
    for cid in ("1", "48", "61"):
        held = NASK / cid
        g = build([d for d in cases if d != held], thr)
        want, ok_via = NASK_EXPECT[cid]
        for name, pick, ocr in (("sam HTML", lambda f: f.suffix.lower() in {".html", ".htm"}, False),
                                ("sam HAR", lambda f: f.suffix.lower() == ".har", False),
                                ("sam zrzut (OCR)", lambda f: f.suffix.lower() in IMG, True)):
            files = uploaded(held, pick)
            got, via, sc, _ = ask(g, files, ocr)
            rows.append({"przypadek": cid, "wejście": name, "wynik": got, "najbliższy": via, "wynik kampanii": sc,
                         "ocena": verdict(got, via, want, ok_via, NASK_NET)})
    g = build(cases, thr)  # duplikat: znany materiał drugi raz
    for cid in ("1", "48"):
        got, via, sc, _ = ask(g, uploaded(NASK / cid))
        rows.append({"przypadek": cid, "wejście": "ten sam materiał drugi raz", "wynik": got, "najbliższy": via, "wynik kampanii": sc,
                     "ocena": "OK" if got == "kampania" and via in {cid} | ok_dup(cid) else verdict(got, via, "kampania", {cid}, NASK_NET)})
        got, via, sc, _ = ask(g, uploaded(NASK / cid, lambda f: f.suffix.lower() in IMG), True)
        rows.append({"przypadek": cid, "wejście": "zrzut znanej reklamy (OCR)", "wynik": got, "najbliższy": via, "wynik kampanii": sc,
                     "ocena": "OK" if got == "kampania" and via in {cid} | ok_dup(cid) else verdict(got, via, "kampania", {cid}, NASK_NET)})
    return pd.DataFrame(rows)


def ok_dup(cid: str) -> set[str]:
    """Znany materiał drugi raz: poprawne jest wskazanie jego samego albo innego materiału tej samej kampanii."""
    return NASK_EXPECT.get(cid, ("", set()))[1] if NASK_EXPECT.get(cid, ("",))[0] == "kampania" else set()


def test_c(thr) -> pd.DataFrame:
    truth = json.loads((SYNTH / "prawda.json").read_text(encoding="utf-8"))
    camp: dict[str, list[str]] = {}
    for m, t in sorted(truth.items()):
        camp.setdefault(t["kampania"], []).append(m)
    held_variant = {ms[-1] for c, ms in camp.items() if not c.startswith("neg") and c != "O6-K2"}
    held_campaign, held_neg = set(camp["O6-K2"]), {m for m, t in truth.items() if t["rodzaj"] != "oszustwo"}
    held = held_variant | held_campaign | held_neg
    g = build([SYNTH / m for m in sorted(truth) if m not in held], thr)
    rows = []
    for m in sorted(held):
        t = truth[m]
        got, via, sc, so = ask(g, uploaded(SYNTH / m))
        if m in held_neg:
            want, ok, typ = "nowy", set(), "inna kampania (negatyw)"
        elif m in held_campaign:
            want, ok, typ = "sieć", {x for x, y in truth.items() if y["operator"] == t["operator"]}, "nowa kampania znanego operatora"
        else:
            want, ok, typ = "kampania", {x for x, y in truth.items() if y["kampania"] == t["kampania"]}, "nowy wariant znanej kampanii"
        rows.append({"materiał": m, "typ": typ, "prawda": t["kampania"], "oczekiwane": want, "wynik": got, "najbliższy": via,
                     "prawda najbliższego": truth.get(via, {}).get("kampania", ""), "wynik kampanii": sc, "wynik operatora": so,
                     "ocena": verdict(got, via, want, ok)})
    return pd.DataFrame(rows)


def table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    return "\n".join(["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
                     + ["| " + " | ".join(str(r[c]).replace("|", "/") for c in cols) + " |" for _, r in df.iterrows()])


def score(df: pd.DataFrame) -> str:
    n, ok = len(df), int((df["ocena"] == "OK").sum())
    part = int(df["ocena"].str.startswith("częściowo").sum())
    return f"{ok}/{n} OK, {part} częściowo, {n - ok - part} błędów"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--campaign", type=float, default=None, help="próg kampanii (domyślnie z konfiguracji, jak w interfejsie)")
    ap.add_argument("--out", default="raport_embsim.md")
    a = ap.parse_args()
    t0 = time.time()
    ra, rb, rc = test_a(a.campaign), test_b(a.campaign), test_c(a.campaign)
    thr = a.campaign if a.campaign is not None else Gallery(thresholds=demo_thresholds()).cfg.thresholds.get("campaign")
    md = ["# Test jak jury: demonstrator embsim", "", f"Próg kampanii {thr}; czas {time.time() - t0:.0f} s.", "",
          f"## A. NASK, ukryty przypadek: {score(ra)}", "", table(ra), "",
          f"## B. Format, braki, duplikat: {score(rb)}", "", table(rb), "",
          f"## C. Syntetyka jako ukryty zbiór: {score(rc)}", "", table(rc), ""]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / a.out).write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
