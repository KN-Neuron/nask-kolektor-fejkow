"""Meta: czy nowa reklama (nieznanego twórcy) przypomina twórców, których reklamy Meta usunęła? Etykieta słaba, z podziałem po twórcach.

    python -m embsim.meta_harm [--sample ../data/meta/sample_s1.jsonl] [--seeds 3]

Etykieta: twórca (page_id) jest „usuwany”, gdy co najmniej jedna jego reklama w zbiorze została zdjęta przez Metę (ma znacznik zdjęcia, bez
treści). To sygnał egzekwowania, nie dowód oszustwa: Meta zdejmuje też spam i naruszenia zasad, a twórca bez zdjętych reklam może być
oszustem jeszcze nieprzyłapanym (szum etykiety w obie strony).

Protokół (bez wycieku):
  * podmiot niezależny = twórca. Twórcy dzieleni losowo na GALERIĘ (60%) i TEST (40%) PRZED jakimkolwiek przetwarzaniem; żaden twórca testowy
    nie ma reklam w galerii. Powtórzone dla kilku ziaren.
  * reklamy zdjęte nie mają treści, więc nie są ani zapytaniami, ani materiałem galerii; etykieta twórcy pochodzi tylko z faktu zdjęcia.
    Zapytanie testowe to reklama z treścią twórcy testowego, a jego własne zdjęte reklamy nie wchodzą do niczego (to źródło etykiety).
  * wynik zapytania = max S do reklam twórców „usuwanych” − max S do reklam pozostałych (S: wzór z docs/14, bez uczenia, bez płatnika i strony).
  * miary: AUROC reklam (przedziały: bootstrap po twórcach testowych), precyzja w górnych 10% wyniku; osobno bez dokładnych duplikatów tekstu
    względem galerii (kopiowanie treści między twórcami jest realnym sygnałem, ale nie jest „podobieństwem”).
  * nie dobieramy żadnego progu, więc nie ma zbioru walidacyjnego do wycieku; konfiguracja wzoru jest ta, którą zamroziliśmy na syntetyce.
"""
from __future__ import annotations

import argparse
import copy
import json
import random
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

from .api import case_from_meta_ad
from .score import Corpus
from .stream_eval import LEX_MAX_CHARS, MODEL, ROTATING, Retriever, log
from .embed import text_vectors

ROOT = Path(__file__).resolve().parents[3]
PROFILES = {
    "tekst gęsty (PCA)": {"text": 1.0},
    "tekst leksykalny": {"text_lex": 1.0},
    "tekst + leksyka + host (wzór)": {"text": 1.0, "text_lex": 1.0, "host": 1.0},
}
GAL_CAP, TEST_CAP = 15, 5


def load(path: Path):
    recs = [json.loads(l) for l in path.open(encoding="utf-8")]
    removed = defaultdict(bool)
    cases = []
    for r in recs:
        if not r.get("page_id"):
            continue
        c = case_from_meta_ad(r)
        pid = str(r["page_id"])
        if c.meta.get("flagged_by_meta"):
            removed[pid] = True
        elif c.text.strip():
            c.meta["page_id"] = pid
            cases.append(c)
        removed.setdefault(pid, False)
    uniq = sorted({c.text for c in cases})
    V = text_vectors(MODEL, uniq)
    vec = {t: V[i] for i, t in enumerate(uniq)}
    for c in cases:
        c.vec = vec[c.text]
    return cases, removed


def split(cases, removed, seed):
    by = defaultdict(list)
    for c in cases:
        by[c.meta["page_id"]].append(c)
    pages = sorted(by)
    rng = random.Random(seed)
    rng.shuffle(pages)
    cut = int(0.6 * len(pages))
    gal_p, test_p = set(pages[:cut]), set(pages[cut:])
    assert not gal_p & test_p
    gal, test = [], []
    for p in pages:
        ads = sorted(by[p], key=lambda c: c.id)
        rng.shuffle(ads)
        (gal if p in gal_p else test).extend(ads[: GAL_CAP if p in gal_p else TEST_CAP])
    return gal, test


def scores(gal, test, removed, weights):
    ret = Retriever(gal, weights)
    cp = ret.corpus
    bad = np.array([removed[c.meta["page_id"]] for c in ret.gal])
    hashes = {h for c in gal for h in c.sets.get("text_hash", ())}
    out = []
    for q in test:
        qq = cp.prepare(copy.copy(q))
        sh = sn = 0.0
        for i in ret.candidates(qq):
            s = cp.score(qq, ret.gal[i]).value
            if bad[i]:
                sh = max(sh, s)
            else:
                sn = max(sn, s)
        out.append({"page": q.meta["page_id"], "y": int(removed[q.meta["page_id"]]), "score": sh - sn,
                    "dup": bool(q.sets.get("text_hash", set()) & hashes)})
    return out


def auc(rows):
    y = [r["y"] for r in rows]
    return float(roc_auc_score(y, [r["score"] for r in rows])) if 0 < sum(y) < len(y) else float("nan")


def prec_top(rows, frac=0.1):
    k = max(1, int(frac * len(rows)))
    top = sorted(rows, key=lambda r: -r["score"])[:k]
    return sum(r["y"] for r in top) / k


def boot(rows, n=300, seed=0):
    by = defaultdict(list)
    for r in rows:
        by[r["page"]].append(r)
    pages = list(by)
    rng = np.random.default_rng(seed)
    a = []
    for _ in range(n):
        s = [r for p in rng.choice(pages, len(pages)) for r in by[p]]
        v = auc(s)
        if v == v:
            a.append(v)
    return float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", default=str(ROOT / "data" / "meta" / "sample_s1.jsonl"))
    ap.add_argument("--seeds", type=int, default=3)
    a = ap.parse_args()
    cases, removed = load(Path(a.sample))
    n_bad = sum(removed.values())
    log(f"reklam z treścią {len(cases)}, twórców {len(removed)}, w tym „usuwanych” {n_bad} ({n_bad / len(removed):.0%})")
    res = defaultdict(list)
    for seed in range(a.seeds):
        gal, test = split(cases, removed, seed)
        base = np.mean([removed[c.meta["page_id"]] for c in test])
        log(f"ziarno {seed}: galeria {len(gal)} reklam, test {len(test)} reklam od {len({c.meta['page_id'] for c in test})} twórców, odsetek „usuwanych” w teście {base:.2f}")
        for name, w in PROFILES.items():
            rows = scores(gal, test, removed, w)
            nd = [r for r in rows if not r["dup"]]
            res[name].append(rows)
            log(f"  {name}: AUROC {auc(rows):.3f}, bez duplikatów {auc(nd):.3f} (n={len(nd)}), precyzja w górnych 10%: {prec_top(rows):.2f} (baza {base:.2f})")
    print("\nPODSUMOWANIE (po ziarnach; przedziały: bootstrap po twórcach testowych, łącznie po ziarnach)")
    for name, runs in res.items():
        allr = [r for rows in runs for r in rows]
        lo, hi = boot(allr)
        per = [auc(r) for r in runs]
        nd = [r for r in allr if not r["dup"]]
        print(f"{name:<32} AUROC {np.mean(per):.3f} [{lo:.3f}; {hi:.3f}]  bez duplikatów {auc(nd):.3f}  precyzja@10% {np.mean([prec_top(r) for r in runs]):.2f}  "
              f"baza {np.mean([r['y'] for r in allr]):.2f}")


if __name__ == "__main__":
    main()
