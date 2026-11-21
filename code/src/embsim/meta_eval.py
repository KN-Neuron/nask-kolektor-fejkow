"""Czy sam tekst reklamy odtwarza TWÓRCĘ (page_id) na podziale po podmiotach z grafu? Bez uczenia.

    python -m embsim.meta_eval ARTIFACTS_DIR ADS_JSONL

Wejście: ARTIFACTS_DIR/{ad_meta.jsonl (id, h, fold, subject), minilm_ads/, qwen_ads/ (częściowe wsady)}.
Jednostka: unikalny tekst; etykieta: page_id (teksty użyte przez wielu twórców lub w wielu foldach są pomijane jako niejednoznaczne).
Próg dobieramy na foldzie val (siatka, plateau ARI), wynik mierzymy na test. Wynik tekstu jak w score.py: (cos − μ)/(1 − μ).
Porównanie: TF-IDF znaków (zero modelu), MiniLM, a na wspólnym podzbiorze krótszych tekstów także Qwen3-VL-Embedding-2B.
"""
from __future__ import annotations

import json
import random
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

from .metrics import evaluate_level

PER_CREATOR = 40        # twórca z setkami tekstów nie może zdominować par
SHOW = ("AUC", "AP", "ARI", "B3_F", "top1", "znany_vs_nowy_AUC", "błędnie_połączone")


def load_units(art: Path, ads: Path, seed: int = 1):
    page = {}
    for line in ads.open(encoding="utf-8"):
        r = json.loads(line)
        page[r["id"]] = r["page_id"]
    info = defaultdict(lambda: {"pages": set(), "folds": set(), "n": 0})
    for line in (art / "ad_meta.jsonl").open(encoding="utf-8"):
        r = json.loads(line)
        if r["h"]:
            u = info[r["h"]]
            u["pages"].add(page[r["id"]]); u["folds"].add(r["fold"]); u["n"] += 1
    keep = {h: u for h, u in info.items() if len(u["pages"]) == 1 and len(u["folds"]) == 1}
    print(f"unikalnych tekstów: {len(info)}, jednoznacznych (1 twórca, 1 fold): {len(keep)} (pominięto {len(info) - len(keep)})")
    by = defaultdict(list)
    for h, u in keep.items():
        by[(next(iter(u["folds"])), next(iter(u["pages"])))].append(h)
    rnd = random.Random(seed)
    units = []   # (hash, fold, creator)
    for (fold, creator), hs in sorted(by.items(), key=lambda kv: kv[0]):
        rnd.shuffle(hs)
        units += [(h, fold, creator) for h in hs[:PER_CREATOR]]
    return units


def texts_by_hash(art: Path) -> dict[str, str]:
    out = {}
    for line in (art / "ad_texts.jsonl").open(encoding="utf-8"):
        r = json.loads(line)
        out.setdefault(r["h"], r["text"])
    return out


def vectors(d: Path, upto: int | None = None) -> dict[str, np.ndarray]:
    hashes = json.loads((d / "hashes.json").read_text())
    full = d / "vectors.npy"
    V = np.load(full) if full.exists() else np.concatenate([np.load(c) for c in sorted(d.glob("chunk_*.npy"))])
    V = V.astype(np.float32)
    V /= np.linalg.norm(V, axis=1, keepdims=True)
    return {h: V[i] for i, h in enumerate(hashes[: len(V)])}


def score_matrix(V: np.ndarray, mu: float | None = None) -> np.ndarray:
    S = V @ V.T
    mu = float(np.median(S[np.triu_indices(len(V), 1)])) if mu is None else mu
    return np.clip((S - mu) / (1 - mu), 0, 1)


def tfidf_vectors(texts: list[str]) -> np.ndarray:
    from sklearn.feature_extraction.text import TfidfVectorizer

    X = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2, sublinear_tf=True, max_features=200000).fit_transform(texts)
    return X  # rzadka macierz, wiersze znormalizowane (l2)


def sparse_scores(X) -> np.ndarray:
    S = (X @ X.T).toarray()
    mu = float(np.median(S[np.triu_indices(S.shape[0], 1)]))
    return np.clip((S - mu) / (1 - mu), 0, 1)


def run(name: str, getV, units, out: list) -> None:
    """getV(lista haszy) -> macierz wyników per fold; próg z val, miary na test."""
    res = {}
    tau = None
    for fold in ("val", "test"):
        us = [u for u in units if u[1] == fold]
        S = getV([u[0] for u in us])
        lab = [u[2] for u in us]
        if fold == "val":
            grid = [round(x, 2) for x in np.arange(0.05, 0.96, 0.05)]
            ari = {t: evaluate_level(S, lab, t)["ARI"] for t in grid}
            best = max(ari.values())
            tau = float(np.median([t for t in grid if ari[t] >= best - 0.02]))
        res[fold] = {"n": len(us), "twórców": len(set(lab)), "próg": tau, **evaluate_level(S, lab, tau)}
    out.append((name, res))


def table(title: str, rows: list) -> None:
    print(f"\n### {title}")
    r0 = rows[0][1]
    print(f"  val: {r0['val']['n']} tekstów / {r0['val']['twórców']} twórców; test: {r0['test']['n']} tekstów / {r0['test']['twórców']} twórców")
    print(f"  {'model':<16}{'próg(val)':>10}" + "".join(f"{k:>18}" for k in SHOW) + "   (miary na TEST)")
    for name, res in rows:
        t = res["test"]
        print(f"  {name:<16}{t['próg']:>10.2f}" + "".join(f"{t.get(k, float('nan')):>18.3f}" for k in SHOW))


def main() -> None:
    art, ads = Path(sys.argv[1]), Path(sys.argv[2])
    units = load_units(art, ads)
    tx = texts_by_hash(art)
    mini = vectors(art / "minilm_ads")
    qwen = vectors(art / "qwen_ads")
    cache = {}

    def tfidf_for(hs):
        return sparse_scores(tfidf_vectors([tx[h] for h in hs]))

    def dense_for(table_):
        return lambda hs: score_matrix(np.stack([table_[h] for h in hs]))

    # A: pełny zbiór jednoznacznych tekstów
    rows = []
    run("TF-IDF znaków", tfidf_for, units, rows)
    run("MiniLM (lekki)", dense_for(mini), units, rows)
    table(f"A. wszystkie jednoznaczne teksty ({len(units)} jednostek)", rows)

    # B: wspólny podzbiór z Qwenem (tylko krótsze teksty, bo liczenie Qwena przerwano)
    common = [u for u in units if u[0] in qwen]
    rows = []
    run("TF-IDF znaków", tfidf_for, common, rows)
    run("MiniLM (lekki)", dense_for(mini), common, rows)
    run("Qwen3-VL 2B", dense_for(qwen), common, rows)
    table(f"B. wspólny podzbiór z Qwenem ({len(common)} jednostek; tylko krótsze teksty)", rows)


if __name__ == "__main__":
    main()
