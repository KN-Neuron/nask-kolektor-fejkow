"""Zbiory zewnętrzne tylko tekstowe (LIAR, BS Detector, BuzzFeed, CREDBANK...): czy sam tekst odtwarza TWÓRCĘ i czy dezinformacja
nie łączy się z reklamami scam.

    python -m embsim.ext inspect data/zewnetrzne/liar          # kolumny i przykładowe wiersze (nic nie zakłada)
    python -m embsim.ext prepare buzzfeed-webis                # tylko BuzzFeed-Webis: XML -> articles.tsv + spec.json
    python -m embsim.ext run liar [--vs-synth]                 # ocena; wymaga data/zewnetrzne/liar/spec.json albo presetu

Zbiory leżą w `data/zewnetrzne/<nazwa>/` (nie wchodzą do gita). Opis kolumn: `spec.json` obok plików, np.
    {"file": "train.tsv", "sep": "\\t", "header": false, "text": [2], "creator": 4, "min_per_creator": 5}
`text` i `creator` to nazwy kolumn (z nagłówkiem) albo numery (bez nagłówka). Presety poniżej są z pamięci i NIE zostały sprawdzone
na prawdziwych plikach: po pobraniu użyj `inspect` i popraw spec.

Protokół: twórcy są dzieleni stabilnie (hash) na połowę dev i test; próg dobieramy na dev, mierzymy na teście. Nic się nie uczy.
Wyniki dotyczą WYŁĄCZNIE kanału tekstowego; to inny zbiór niż kampanie reklam (angielski, wiadomości/wypowiedzi, bez ruchu sieciowego),
więc nie zastępuje oceny na reklamach.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

from .embed import text_vectors
from .features import Case
from .metrics import evaluate_level
from .score import Corpus

EXT = Path(__file__).resolve().parents[3] / "data" / "zewnetrzne"
ART = Path(__file__).resolve().parents[2] / "artifacts" / "ext"
MODEL = "paraphrase-multilingual-MiniLM-L12-v2"   # ten sam lekki model co w bench.py (konfiguracja zamrożona)
PRESETS = {  # Z PAMIĘCI, niezweryfikowane; zob. docstring
    "liar": {"file": "train.tsv", "sep": "\t", "header": False, "text": [2], "creator": 4},
    "bsdetector": {"file": "fake.csv", "sep": ",", "header": True, "text": ["title", "text"], "creator": "site_url"},
}


# --------------------------------------------------------------------------------------------------------------------
# wczytanie


def read_rows(f: Path, sep: str | None, header: bool) -> tuple[list[str] | None, list[list[str]]]:
    csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
    sep = sep or ("\t" if f.suffix.lower() in {".tsv", ".txt"} else ",")
    with f.open(newline="", encoding="utf-8", errors="ignore") as h:
        rows = list(csv.reader(h, delimiter=sep))
    return (rows[0], rows[1:]) if header and rows else (None, rows)


def prepare_buzzfeed(d: Path) -> None:
    """BuzzFeed-Webis: articles/*.xml + overview.csv -> articles.tsv (twórca = portal) i spec.json. Odmawia XML z DTD/ENTITY."""
    import xml.etree.ElementTree as ET

    rows = []
    with (d / "overview.csv").open(newline="", encoding="utf-8") as h:
        for r in csv.DictReader(h):
            raw = (d / "articles" / r["XML"]).read_text(encoding="utf-8", errors="ignore")
            if "<!DOCTYPE" in raw or "<!ENTITY" in raw:
                raise SystemExit(f"{r['XML']}: DTD/ENTITY w XML z zewnątrz, nie parsuję")
            x = ET.fromstring(raw.encode("utf-8"))
            clean = lambda t: " ".join((t or "").split())
            rows.append([r["XML"], r["portal"], r["orientation"], r["veracity"], clean(x.findtext("title")),
                         clean(x.findtext("mainText"))])
    with (d / "articles.tsv").open("w", newline="", encoding="utf-8") as h:
        w = csv.writer(h, delimiter="\t")
        w.writerow(["file", "portal", "orientation", "veracity", "title", "text"])
        w.writerows(rows)
    (d / "spec.json").write_text(json.dumps({"file": "articles.tsv", "sep": "\t", "header": True, "text": ["title", "text"],
                                             "creator": "portal", "min_per_creator": 20}))
    print(f"zapisano {len(rows)} artykułów do articles.tsv i spec.json (twórca = portal)")


def load(name: str, cap_creators: int = 40, per_creator: int = 25, seed: int = 1) -> tuple[list[str], list[str]]:
    d = EXT / name
    spec_f = d / "spec.json"
    spec = json.loads(spec_f.read_text()) if spec_f.exists() else PRESETS.get(name)
    if spec is None:
        raise SystemExit(f"brak {spec_f} i presetu dla '{name}': uruchom `inspect` i opisz kolumny w spec.json")
    head, rows = read_rows(d / spec["file"], spec.get("sep"), spec.get("header", True))
    col = lambda c: head.index(c) if isinstance(c, str) else c
    tcols, ccol = [col(c) for c in spec["text"]], col(spec["creator"])
    by = defaultdict(list)
    for r in rows:
        if len(r) <= max(tcols + [ccol]):
            continue
        text = "\n".join(r[c].strip() for c in tcols if r[c].strip())
        if text and r[ccol].strip():
            by[r[ccol].strip().lower()].append(text)
    keep = sorted(c for c, v in by.items() if len(v) >= spec.get("min_per_creator", 5))
    rnd = random.Random(seed)
    rnd.shuffle(keep)
    texts, creators = [], []
    for c in keep[:cap_creators]:
        for t in rnd.sample(by[c], min(per_creator, len(by[c]))):
            texts.append(t[:2000]); creators.append(c)
    return texts, creators


def half(creator: str) -> str:
    """Stabilny podział twórców na dev/test (ten sam twórca zawsze w tej samej połowie)."""
    return "dev" if int(hashlib.sha1(creator.encode()).hexdigest(), 16) % 2 == 0 else "test"


# --------------------------------------------------------------------------------------------------------------------
# ocena


def scores(V: np.ndarray, mu: float | None = None) -> np.ndarray:
    """Wynik tylko z kanału tekstowego, tak jak w score.Corpus: (cos − μ)/(1 − μ), obcięte do [0,1]."""
    S = V @ V.T
    mu = float(np.median(S[np.triu_indices(len(V), 1)])) if mu is None else mu
    return np.clip((S - mu) / (1 - mu), 0, 1)


def pick_tau(S: np.ndarray, labels: list) -> float:
    grid = [round(x, 2) for x in np.arange(0.05, 0.96, 0.05)]
    ari = {t: evaluate_level(S, labels, t)["ARI"] for t in grid}
    best = max(ari.values())
    return float(np.median([t for t in grid if ari[t] >= best - 0.02]))


def evaluate(texts: list[str], creators: list[str], vectors=None) -> dict:
    vectors = vectors or (lambda ts: text_vectors(MODEL, ts))
    V = np.asarray(vectors(texts))
    out, tau = {}, None
    for part in ("dev", "test"):
        idx = [i for i, c in enumerate(creators) if half(c) == part]
        if len(idx) < 10:
            raise SystemExit(f"za mało twórców w połowie {part} ({len(idx)} tekstów)")
        S = scores(V[idx])
        lab = [creators[i] for i in idx]
        tau = pick_tau(S, lab) if part == "dev" else tau
        out[part] = {"n_tekstów": len(idx), "n_twórców": len(set(lab)), "próg": tau, **evaluate_level(S, lab, tau)}
    return out


def cross_link(Va: np.ndarray, Vb: np.ndarray, tau: float) -> dict:
    """Czy dwie klasy (np. dezinformacja vs reklamy scam) się mieszają: odsetek połączonych par międzyklasowych i AUC
    „para z tej samej klasy” vs „międzyklasowa” (1,0 = idealnie rozdzielone)."""
    V = np.vstack([Va, Vb])
    S = V @ V.T
    mu = float(np.median(S[np.triu_indices(len(V), 1)]))
    Sn = np.clip((S - mu) / (1 - mu), 0, 1)
    na = len(Va)
    cross = Sn[:na, na:]
    within = np.r_[Sn[:na, :na][np.triu_indices(na, 1)], Sn[na:, na:][np.triu_indices(len(Vb), 1)]]
    y = np.r_[np.ones(len(within)), np.zeros(cross.size)]
    return {"odsetek_połączonych_międzyklasowo": float((cross >= tau).mean()),
            "AUC_ta_sama_klasa_vs_międzyklasowa": float(roc_auc_score(y, np.r_[within, cross.ravel()]))}


def synth_texts() -> list[str]:
    from .bench import SYNTH_DEV, synth_seed

    out = [c.text for c in synth_seed(1).cases if c.text]
    return out


# --------------------------------------------------------------------------------------------------------------------


def inspect(d: Path) -> None:
    for f in sorted(p for p in d.iterdir() if p.suffix.lower() in {".csv", ".tsv", ".txt", ".json", ".jsonl"})[:10]:
        print(f"\n== {f.name} ({f.stat().st_size / 1e6:.1f} MB)")
        if f.suffix.lower() in {".json", ".jsonl"}:
            print(f.read_text(encoding="utf-8", errors="ignore")[:600])
            continue
        head, rows = read_rows(f, None, False)
        for r in rows[:3]:
            print([x[:50] for x in r][:14])
        print(f"wierszy: {len(rows)}, kolumn w 1. wierszu: {len(rows[0]) if rows else 0}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["inspect", "prepare", "run"])
    ap.add_argument("name")
    ap.add_argument("--cap", type=int, default=40, help="maks. twórców")
    ap.add_argument("--per-creator", type=int, default=25, help="maks. tekstów na twórcę")
    ap.add_argument("--vs-synth", action="store_true", help="dodatkowo: czy zbiór miesza się z tekstami scam (syntetyk)")
    a = ap.parse_args()
    if a.cmd == "inspect":
        inspect(Path(a.name))
        return
    if a.cmd == "prepare":
        prepare_buzzfeed(EXT / a.name)
        return
    texts, creators = load(a.name, a.cap, a.per_creator)
    print(f"{a.name}: {len(texts)} tekstów, {len(set(creators))} twórców (połowy dev/test po hashu twórcy)")
    res = evaluate(texts, creators)
    keys = ("n_tekstów", "n_twórców", "próg", "AUC", "AP", "ARI", "B3_F", "top1", "znany_vs_nowy_AUC", "błędnie_połączone")
    for part, m in res.items():
        print(f"  {part:<5}" + "  ".join(f"{k}={m.get(k, float('nan')):.3f}" for k in keys))
    if a.vs_synth:
        st = synth_texts()
        V = np.asarray(text_vectors(MODEL, texts)); Vs = np.asarray(text_vectors(MODEL, st))
        print("  mieszanie z reklamami scam (syntetyk):", cross_link(V, Vs, res["dev"]["próg"]))
    ART.mkdir(parents=True, exist_ok=True)
    (ART / f"{a.name}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float))


if __name__ == "__main__":
    main()
