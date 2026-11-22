"""Test na zbiorze ukrytym (walidacja z opisu wyzwania, pkt 6) jako moduł: ten sam kod uruchamia skrypt i zakładka „Wzór i wyniki” w interfejsie.

Odtwarza przebieg użytkownika w interfejsie: buduje galerię z folderów przypadków, potem każdy nowy materiał wgrywa jako pliki (HTML, HAR,
zrzuty; bez folderów zasobów `_files`, bo uploader przyjmuje tylko pliki) i czyta werdykt: znana kampania / znany operator, nowa
kampania / nowy wzorzec.

  A. NASK, ukryty przypadek: galeria z pozostałych przypadków, ukryty jako nowy.
  B. Format i braki: sam HTML / sam HAR / sam zrzut (OCR) / ten sam materiał drugi raz.
  C. Syntetyka jako ukryty zbiór: trzeci materiał każdej kampanii, cała kampania O6-K2, negatywy (prawda: prawda.json).

Oczekiwania dla NASK to nasz odczyt danych (kampanie {1,2} i {48,61}, przypadek 3 w tej samej sieci), nie etykiety organizatora.
`summary()` zbiera wyniki wg kryteriów walidacji z opisu wyzwania (skuteczność, poprawność przypisania, niełączenie, odporność,
interpretowalność), z precyzją i czułością decyzji „znana kampania”.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pandas as pd

from . import analyze as A
from .api import Gallery, demo_thresholds

ROOT = Path(__file__).resolve().parents[3]
NASK = ROOT / "data" / "dane" / "do_udostępnienia"
SYNTH = ROOT / "data" / "synth"

NASK_EXPECT = {"1": ("kampania", {"2"}), "2": ("kampania", {"1"}), "48": ("kampania", {"61"}), "61": ("kampania", {"48"}),
               "3": ("sieć", {"1", "2", "48", "61"})}
NASK_NET = {"1", "2", "3", "48", "61"}
KIND = {"znana_kampania": "kampania", "znany_operator_nowa_kampania": "sieć", "nowy_wzorzec": "nowy"}
IMG = {".png", ".jpg", ".jpeg", ".webp"}
HIDDEN = ("_grupa", "_powody")                      # kolumny pomocnicze, nie do tabel


def uploaded(case_dir: Path, pick=lambda f: True) -> list[tuple[str, bytes]]:
    """Pliki, które człowiek wybrałby w oknie wgrywania: wszystko poza folderami zasobów strony (`*_files`)."""
    return [(f.name, f.read_bytes()) for f in sorted(case_dir.rglob("*"))
            if f.is_file() and not any(p.endswith("_files") for p in f.relative_to(case_dir).parts[:-1]) and pick(f)]


def build(dirs: list[Path], cfg_thr: float | None = None) -> Gallery:
    g = Gallery(profile="strony")                       # jak w interfejsie
    if cfg_thr is not None:
        g.cfg.thresholds["campaign"] = cfg_thr
    with tempfile.TemporaryDirectory() as td:
        for d in dirs:
            (Path(td) / d.name).symlink_to(d.resolve(), target_is_directory=True)
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


def ask(g: Gallery, files, ocr: bool = False) -> tuple[str, str, float, float, int]:
    """(poziom, materiał uzasadniający, wynik kampanii, wynik operatora, liczba przesłanek)."""
    case, _ = A.case_from_inputs(files, ocr=ocr)
    d = g.query(case, 5)
    m = d.key_match()
    reasons = len(A.top_reasons(m)) if m else 0
    return KIND.get(d.verdict, d.verdict), (m.id if m else ""), round(d.campaign_score, 3), round(d.operator_score, 3), reasons


def _dirs(root: Path) -> list[Path]:
    return sorted((d for d in root.iterdir() if d.is_dir()), key=lambda d: (len(d.name), d.name))


def test_a(thr=None, nask: Path = NASK) -> pd.DataFrame:
    cases, rows = _dirs(nask), []
    for held in cases:
        g = build([d for d in cases if d != held], thr)
        got, via, sc, so, nr = ask(g, uploaded(held))
        want, ok_via = NASK_EXPECT.get(held.name, ("nowy", set()))
        rows.append({"przypadek": held.name, "oczekiwane": want, "wynik": got, "najbliższy": via, "wynik kampanii": sc,
                     "wynik operatora": so, "ocena": verdict(got, via, want, ok_via, NASK_NET),
                     "_grupa": via in ok_via, "_powody": nr})
    return pd.DataFrame(rows)


def _ok_dup(cid: str) -> set[str]:
    """Znany materiał drugi raz: poprawne jest wskazanie jego samego albo innego materiału tej samej kampanii."""
    return NASK_EXPECT[cid][1] if NASK_EXPECT.get(cid, ("",))[0] == "kampania" else set()


def test_b(thr=None, nask: Path = NASK) -> pd.DataFrame:
    cases, rows = _dirs(nask), []
    for cid in ("1", "48", "61"):
        held = nask / cid
        g = build([d for d in cases if d != held], thr)
        want, ok_via = NASK_EXPECT[cid]
        for name, pick, ocr in (("sam HTML", lambda f: f.suffix.lower() in {".html", ".htm"}, False),
                                ("sam HAR", lambda f: f.suffix.lower() == ".har", False),
                                ("sam zrzut (OCR)", lambda f: f.suffix.lower() in IMG, True)):
            got, via, sc, _, nr = ask(g, uploaded(held, pick), ocr)
            rows.append({"przypadek": cid, "wejście": name, "wynik": got, "najbliższy": via, "wynik kampanii": sc,
                         "ocena": verdict(got, via, want, ok_via, NASK_NET), "_grupa": via in ok_via, "_powody": nr})
    g = build(cases, thr)  # duplikat: znany materiał drugi raz
    for cid in ("1", "48"):
        for name, pick, ocr in (("ten sam materiał drugi raz", lambda f: True, False),
                                ("zrzut znanej reklamy (OCR)", lambda f: f.suffix.lower() in IMG, True)):
            got, via, sc, _, nr = ask(g, uploaded(nask / cid, pick), ocr)
            good = {cid} | _ok_dup(cid)
            rows.append({"przypadek": cid, "wejście": name, "wynik": got, "najbliższy": via, "wynik kampanii": sc,
                         "ocena": "OK" if got == "kampania" and via in good else verdict(got, via, "kampania", {cid}, NASK_NET),
                         "_grupa": via in good, "_powody": nr})
    return pd.DataFrame(rows)


def test_c(thr=None, synth: Path = SYNTH) -> pd.DataFrame:
    truth = json.loads((synth / "prawda.json").read_text(encoding="utf-8"))
    camp: dict[str, list[str]] = {}
    for m, t in sorted(truth.items()):
        camp.setdefault(t["kampania"], []).append(m)
    held_variant = {ms[-1] for c, ms in camp.items() if not c.startswith("neg") and c != "O6-K2"}
    held_campaign, held_neg = set(camp["O6-K2"]), {m for m, t in truth.items() if t["rodzaj"] != "oszustwo"}
    held = held_variant | held_campaign | held_neg
    g = build([synth / m for m in sorted(truth) if m not in held], thr)
    rows = []
    for m in sorted(held):
        t = truth[m]
        got, via, sc, so, nr = ask(g, uploaded(synth / m))
        if m in held_neg:
            want, ok, typ = "nowy", set(), "inna kampania (negatyw)"
        elif m in held_campaign:
            want, ok, typ = "sieć", {x for x, y in truth.items() if y["operator"] == t["operator"]}, "nowa kampania znanego operatora"
        else:
            want, ok, typ = "kampania", {x for x, y in truth.items() if y["kampania"] == t["kampania"]}, "nowy wariant znanej kampanii"
        rows.append({"materiał": m, "typ": typ, "prawda": t["kampania"], "oczekiwane": want, "wynik": got, "najbliższy": via,
                     "prawda najbliższego": truth.get(via, {}).get("kampania", ""), "wynik kampanii": sc, "wynik operatora": so,
                     "ocena": verdict(got, via, want, ok), "_grupa": via in ok, "_powody": nr})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------------------------------------------------
# podsumowanie wg kryteriów walidacji z opisu wyzwania (pkt 6)


def _frac(num: int, den: int) -> str:
    return f"{num}/{den} ({num / den:.0%})" if den else "brak danych"


def summary(ra: pd.DataFrame | None, rb: pd.DataFrame | None, rc: pd.DataFrame | None) -> list[dict]:
    """Wiersze {kryterium, miara, wynik, jak liczone}; ra, rb, rc mogą być None (brak danych w danym środowisku)."""
    parts = [x for x in (ra, rc) if x is not None]
    ac = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    rows = []
    if len(ac):
        pos = ac[ac["oczekiwane"] == "kampania"]
        links = ac[ac["wynik"] == "kampania"]
        tp = int(((ac["wynik"] == "kampania") & (ac["oczekiwane"] == "kampania") & ac["_grupa"]).sum())
        rows += [
            {"kryterium": "Skuteczność: podobne materiały i warianty tych samych kampanii", "miara": "trafione na poziomie kampanii",
             "wynik": _frac(int((pos["ocena"] == "OK").sum()), len(pos)),
             "jak liczone": "nowy wariant znanej kampanii rozpoznany jako ta sama kampania, wskazany właściwy materiał"},
            {"kryterium": "", "miara": "wskazana właściwa grupa (kampania lub sieć)",
             "wynik": _frac(int(pos["_grupa"].sum()), len(pos)), "jak liczone": "najbliższy materiał jest z tej samej kampanii"},
            {"kryterium": "Poprawność przypisywania do istniejących grup", "miara": "precyzja decyzji „znana kampania”",
             "wynik": _frac(tp, len(links)), "jak liczone": "z decyzji „znana kampania” ile wskazało właściwą grupę"},
            {"kryterium": "", "miara": "czułość decyzji „znana kampania”", "wynik": _frac(tp, len(pos)),
             "jak liczone": "z nowych wariantów ile dostało decyzję „znana kampania” z właściwą grupą"},
        ]
        neg = ac[ac["oczekiwane"] == "nowy"]
        rows.append({"kryterium": "Niełączenie tego, co nie powinno być połączone", "miara": "obce materiały zostawione jako „nowy wzorzec”",
                     "wynik": _frac(int((neg["ocena"] == "OK").sum()), len(neg)),
                     "jak liczone": "negatywy z syntetyki i przypadki NASK spoza kampanii {1,2} i {48,61}"})
        net = ac[ac["oczekiwane"] == "sieć"]
        if len(net):
            rows.append({"kryterium": "Nowa kampania znanego operatora", "miara": "rozpoznany operator, nie doklejony do kampanii",
                         "wynik": _frac(int((net["ocena"] == "OK").sum()), len(net)),
                         "jak liczone": "nowa kampania tej samej infrastruktury: werdykt „znany operator” z właściwym operatorem"})
        used = ac[ac["wynik"] != "nowy"]
        rows.append({"kryterium": "Interpretowalność", "miara": "decyzje połączeniowe z podanymi przesłankami",
                     "wynik": _frac(int((used["_powody"] > 0).sum()), len(used)),
                     "jak liczone": "każda decyzja „kampania”/„sieć” ma co najmniej jeden wskazany powód (wspólne ślady, kanały)"})
    if rb is not None and len(rb):
        rows += [{"kryterium": "Odporność: duplikaty, niekompletne dane, format", "miara": "dobra decyzja (dokładnie)",
                  "wynik": _frac(int((rb["ocena"] == "OK").sum()), len(rb)), "jak liczone": "sam HTML, sam HAR, sam zrzut, ten sam materiał drugi raz"},
                 {"kryterium": "", "miara": "dobra grupa (także inny poziom)",
                  "wynik": _frac(int(rb["_grupa"].sum()), len(rb)), "jak liczone": "najbliższy materiał z tej samej kampanii"}]
    return rows


def score(df: pd.DataFrame) -> str:
    n, ok = len(df), int((df["ocena"] == "OK").sum())
    part = int(df["ocena"].str.startswith("częściowo").sum())
    return f"{ok}/{n} OK, {part} częściowo, {n - ok - part} błędów"


def table(df: pd.DataFrame) -> str:
    cols = [c for c in df.columns if c not in HIDDEN]
    return "\n".join(["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
                     + ["| " + " | ".join(str(r[c]).replace("|", "/") for c in cols) + " |" for _, r in df.iterrows()])


def run_all(thr=None, nask: Path = NASK, synth: Path = SYNTH) -> dict:
    """Uruchamia testy dla dostępnych zbiorów; brakujące zbiory są pomijane (None). Kanał infra tylko z zapisanego pliku: wynik nie
    zależy od tego, czy komputer ma akurat sieć."""
    from .infra import forced

    with forced("cache"):
        ra = test_a(thr, nask) if nask.is_dir() else None
        rb = test_b(thr, nask) if nask.is_dir() else None
        rc = test_c(thr, synth) if (synth / "prawda.json").is_file() else None
    return {"A": ra, "B": rb, "C": rc, "podsumowanie": summary(ra, rb, rc),
            "próg": thr if thr is not None else Gallery(profile="strony").cfg.thresholds.get("campaign")}


# --------------------------------------------------------------------------------------------------------------------
# zapis wyników (żeby interfejs pokazywał je także tam, gdzie nie ma danych organizatora)

STORED = ROOT / "code" / "config" / "embsim" / "wyniki_jury.json"


def to_record(r: dict) -> dict:
    """Wynik `run_all` w postaci JSON: tabele bez kolumn pomocniczych, z datą i progiem. Same werdykty i wyniki, bez treści materiałów."""
    import datetime

    tab = {k: (None if r[k] is None else r[k].drop(columns=list(HIDDEN)).to_dict("records")) for k in ("A", "B", "C")}
    return {"próg": r["próg"], "data": datetime.date.today().isoformat(), "podsumowanie": r["podsumowanie"], **tab,
            "wyniki": {k: (None if r[k] is None else score(r[k])) for k in ("A", "B", "C")}}


def save_stored(r: dict, path: Path = STORED) -> None:
    path.write_text(json.dumps(to_record(r), ensure_ascii=False, indent=1), encoding="utf-8")


def load_stored(path: Path = STORED) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
