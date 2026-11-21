"""Test „jak jury” (opis wyzwania, pkt 6): ukryty zbiór testowy z nowymi wariantami znanych kampanii i materiałami innych kampanii.

Używa tej samej ścieżki co zakładka „Nowy zbiór” (batch.materials_from + batch.analyze), więc sprawdza to, co jury kliknie.

  A. NASK, ukryty przypadek: każdy z 10 przypadków po kolei wyjmujemy ze zbioru i podajemy jako nowy materiał.
  B. Format i braki: ten sam przypadek jako sam HTML / sam HAR / sam zrzut / zip / płaski folder / duplikat.
  C. Syntetyka jako ukryty zbiór: trzeci materiał każdej kampanii (nowy wariant), cała kampania O6-K2 (nowa kampania znanego
     operatora) i 6 negatywów (inne kampanie, nie wolno ich łączyć). Prawda: data/synth/prawda.json.

Oczekiwania dla NASK to nasz odczyt danych (docs/11_WZORCE_KAMPANII.md), nie etykiety organizatora.

Uruchomienie (z katalogu code/): .venv/bin/python scripts/test_jak_jury.py  → raport w artifacts/jury/raport.md
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

import pandas as pd

from fejki.config import ROOT
from fejki.demo import batch, store
from fejki.demo.material import HTML_EXT, IMG_EXT, VID_EXT, is_har

NASK = ROOT.parent / "data" / "dane" / "do_udostępnienia"
SYNTH = ROOT.parent / "data" / "synth"
OUT = ROOT / "artifacts" / "jury"

# nasz odczyt zbioru organizatora: kampanie {1,2} i {48,61}, przypadek 3 w tej samej sieci (domena healthlinkq.pro), reszta osobno
NASK_EXPECT = {"1": ("kampania", {"2"}), "2": ("kampania", {"1"}), "48": ("kampania", {"61"}), "61": ("kampania", {"48"}),
               "3": ("sieć", {"1", "2", "48", "61"})}
NASK_NET = {"1", "2", "3", "48", "61"}  # jedna sieć operatora


def kind(decision: str) -> str:
    if decision.startswith("przypisano"):
        return "kampania"
    if decision.startswith("nowy przekaz"):
        return "sieć"
    if decision.startswith("możliwe"):
        return "do weryfikacji"
    return "nowy"


def verdict(got: str, via: str, want: str, ok_via: set[str], net: set[str] = frozenset()) -> str:
    """OK / częściowo / BŁĄD z perspektywy jury. `net`: materiały tej samej sieci (dobra sieć, gdy kampanii nie da się ustalić)."""
    if want == "nowy":
        return {"nowy": "OK", "do weryfikacji": "częściowo (analityk odrzuci)"}.get(got, "BŁĄD: połączono obce")
    if got == want and via in ok_via:
        return "OK"
    if got in ("kampania", "sieć") and via in ok_via:
        return "częściowo (dobra grupa, inny poziom)"
    if got == "do weryfikacji" and via in ok_via:
        return "częściowo (do weryfikacji)"
    if got == "sieć" and via in net:
        return "częściowo (dobra sieć; bez treści kampanii nie da się ustalić)"
    if got == "do weryfikacji" and via in net:
        return "częściowo (dobra sieć, do weryfikacji)"
    return "BŁĄD: " + ("nie rozpoznano" if got in ("nowy", "do weryfikacji") else "zła grupa")


def run_batch(known: list, path: Path, ocr: bool = False) -> pd.DataFrame:
    idx = store.Index(built_at="", data_dir="", materials=known)
    df, _ = batch.analyze(idx, batch.materials_from(path, ocr=ocr))
    return df


def subset_dir(case: Path, pick, dest: Path) -> Path:
    """Kopia przypadku z wybranymi plikami (struktura zachowana), żeby wejście szło tą samą drogą co folder od jury."""
    out = dest / case.name
    for f in case.rglob("*"):
        if f.is_file() and pick(f):
            t = out / f.relative_to(case)
            t.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, t)
    return out


def test_a(idx) -> pd.DataFrame:
    rows = []
    for m in idx.materials:
        known = [x for x in idx.materials if x.id != m.id]
        with tempfile.TemporaryDirectory() as tmp:
            src = subset_dir(NASK / m.id, lambda f: True, Path(tmp))
            r = run_batch(known, src.parent).iloc[0]
        want, ok_via = NASK_EXPECT.get(m.id, ("nowy", set()))
        got = kind(r["decyzja"])
        rows.append({"przypadek": m.id, "oczekiwane": want, "wynik": got, "przez": r["przez materiał"], "wynik pary": r["najlepszy wynik"],
                     "ocena": verdict(got, r["przez materiał"], want, ok_via), "decyzja narzędzia": r["decyzja"]})
    return pd.DataFrame(rows)


def test_b(idx) -> pd.DataFrame:
    rows = []
    for cid in ("1", "48", "61"):
        case = NASK / cid
        known = [x for x in idx.materials if x.id != cid]
        want, ok_via = NASK_EXPECT[cid]
        variants = {
            "pełny folder": (lambda f: True, False),
            "tylko HTML (z zasobami)": (lambda f: f.suffix.lower() in HTML_EXT or "_files" in str(f), False),
            "tylko HAR": (is_har, False),
            "tylko zrzut / reklama (OCR)": (lambda f: f.suffix.lower() in IMG_EXT | VID_EXT and "_files" not in str(f), True),
        }
        for name, (pick, ocr) in variants.items():
            with tempfile.TemporaryDirectory() as tmp:
                src = subset_dir(case, pick, Path(tmp))
                if not any(src.rglob("*")):
                    rows.append({"przypadek": cid, "wejście": name, "ocena": "brak takich plików w przypadku"})
                    continue
                t = time.time()
                df = run_batch(known, src.parent, ocr)
            rows += [{"przypadek": cid, "wejście": name, "materiałów": len(df), "wynik": kind(r["decyzja"]), "przez": r["przez materiał"],
                      "ocena": verdict(kind(r["decyzja"]), r["przez materiał"], want, ok_via, NASK_NET), "s": round(time.time() - t, 1)}
                     for _, r in df.iterrows()]
        with tempfile.TemporaryDirectory() as tmp:  # zip z folderem przypadku
            src = subset_dir(case, lambda f: True, Path(tmp) / "x")
            z = Path(shutil.make_archive(str(Path(tmp) / f"jury_{cid}"), "zip", src.parent))
            df = run_batch(known, z)
            rows += [{"przypadek": cid, "wejście": "archiwum .zip", "materiałów": len(df), "wynik": kind(r["decyzja"]),
                      "przez": r["przez materiał"], "ocena": verdict(kind(r["decyzja"]), r["przez materiał"], want, ok_via, NASK_NET)}
                     for _, r in df.iterrows()]
        with tempfile.TemporaryDirectory() as tmp:  # płaski folder: same pliki główne, bez podfolderu przypadku
            flat = Path(tmp) / "plaski"
            flat.mkdir()
            for f in case.iterdir():
                if f.is_file():
                    shutil.copy2(f, flat / f.name)
            df = run_batch(known, flat)
            rows += [{"przypadek": cid, "wejście": "płaski folder z plikami", "materiałów": len(df), "wynik": kind(r["decyzja"]),
                      "przez": r["przez materiał"], "ocena": verdict(kind(r["decyzja"]), r["przez materiał"], want, ok_via, NASK_NET)}
                     for _, r in df.iterrows()]
    # ten sam zrzut reklamy, którą już znamy (np. ponowne zgłoszenie tej samej reklamy): ma ją rozpoznać po obrazie
    for cid in ("1", "48", "61"):
        with tempfile.TemporaryDirectory() as tmp:
            src = subset_dir(NASK / cid, lambda f: f.suffix.lower() in IMG_EXT and "_files" not in str(f) and "strona_" not in str(f),
                             Path(tmp))
            src.rename(src.parent / f"zrzut_{cid}")
            df = run_batch(idx.materials, Path(tmp), ocr=True)
            r = df.iloc[0]
            rows.append({"przypadek": f"{cid} (sam zrzut, reklama znana)", "wejście": "zrzut znanej reklamy", "materiałów": len(df),
                         "wynik": kind(r["decyzja"]), "przez": r["przez materiał"],
                         "ocena": "OK" if r["przez materiał"] == cid and kind(r["decyzja"]) == "kampania"
                         else verdict(kind(r["decyzja"]), r["przez materiał"], "kampania", {cid}, NASK_NET)})
    # duplikat: znany przypadek podany jeszcze raz (pod inną nazwą) ma trafić do swojej kampanii jako duplikat
    with tempfile.TemporaryDirectory() as tmp:
        src = subset_dir(NASK / "1", lambda f: True, Path(tmp))
        src.rename(src.parent / "kopia_1")
        df = run_batch(idx.materials, Path(tmp))
        r = df.iloc[0]
        rows.append({"przypadek": "1 (kopia)", "wejście": "duplikat znanego", "materiałów": len(df), "wynik": kind(r["decyzja"]),
                     "przez": r["przez materiał"], "ocena": "OK" if r["relacja"] == "duplikat" and kind(r["decyzja"]) == "kampania"
                     else f"BŁĄD: {r['relacja']}"})
    return pd.DataFrame(rows)


def test_c() -> tuple[pd.DataFrame, list[dict]]:
    truth = json.loads((SYNTH / "prawda.json").read_text(encoding="utf-8"))
    idx = store.load(ROOT / "artifacts" / "demo" / "index_synth.json")
    camp: dict[str, list[str]] = {}
    for m, t in sorted(truth.items()):
        camp.setdefault(t["kampania"], []).append(m)
    held_variant = {ms[-1] for c, ms in camp.items() if not c.startswith("neg") and c != "O6-K2"}
    held_campaign = set(camp["O6-K2"])
    held_neg = {m for m, t in truth.items() if t["rodzaj"] != "oszustwo"}
    held = held_variant | held_campaign | held_neg
    known = [m for m in idx.materials if m.id not in held]
    with tempfile.TemporaryDirectory() as tmp:
        for m in sorted(held):
            shutil.copytree(SYNTH / m, Path(tmp) / m)
        df, props = batch.analyze(store.Index(built_at="", data_dir="", materials=known), batch.materials_from(Path(tmp), ocr=False))
    rows = []
    for _, r in df.iterrows():
        m, via, got = r["materiał"], r["przez materiał"], kind(r["decyzja"])
        t = truth[m]
        if m in held_neg:
            want, ok_via, typ = "nowy", set(), "inna kampania (negatyw)"
        elif m in held_campaign:
            want, typ = "sieć", "nowa kampania znanego operatora"
            ok_via = {x for x, y in truth.items() if y["operator"] == t["operator"]}
        else:
            want, typ = "kampania", "nowy wariant znanej kampanii"
            ok_via = {x for x, y in truth.items() if y["kampania"] == t["kampania"]}
        rows.append({"materiał": m, "typ": typ, "prawda": t["kampania"], "oczekiwane": want, "wynik": got, "przez": via,
                     "prawda 'przez'": truth.get(via, {}).get("kampania", ""), "ocena": verdict(got, via, want, ok_via)})
    return pd.DataFrame(rows), props


def table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    cell = lambda v: "" if pd.isna(v) else str(v).replace("|", "/").replace("\n", " ")
    return "\n".join(["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
                     + ["| " + " | ".join(cell(r[c]) for c in cols) + " |" for _, r in df.iterrows()])


def score(df: pd.DataFrame) -> str:
    n = len(df)
    ok = (df["ocena"] == "OK").sum()
    part = df["ocena"].str.startswith("częściowo").sum()
    return f"{ok}/{n} OK, {part} częściowo, {n - ok - part} błędów"


def main() -> None:
    idx = store.load()
    if not idx or not NASK.exists() or not SYNTH.exists():
        sys.exit("brak indeksu NASK, danych organizatora albo data/synth")
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    a, b = test_a(idx), test_b(idx)
    c, props = test_c()
    md = ["# Test jak jury (pkt 6 opisu wyzwania)", "",
          (f"Czas: {time.time() - t0:.0f} s. Silnik: ten sam co demo (zakładka „Nowy zbiór”), próg 0.7, do weryfikacji 0.4, "
           "bez OCR poza wariantem „tylko zrzut”."), "",
          f"## A. NASK, ukryty przypadek: {score(a)}", "", table(a), "",
          f"## B. Inny format, braki, duplikat: {score(b[b['ocena'] != 'brak takich plików w przypadku'])}", "",
          table(b), "",
          f"## C. Syntetyka jako ukryty zbiór: {score(c)}", "", table(c), "",
          "Propozycje nowych kampanii z nieprzypisanych: " + ("; ".join(f"{p['id']}: {', '.join(p['materiały'])}" for p in props) or "brak"),
          ""]
    (OUT / "raport.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
