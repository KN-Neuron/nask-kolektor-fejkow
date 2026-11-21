"""Ewaluacja strumieniowa po czasie na PRAWDZIWYCH reklamach Mety (próbka S1): jak zachowuje się system, gdy nowa reklama przychodzi do
wcześniej zebranego zbioru. To odpowiednik zadania organizatora („analiza nowego materiału względem wcześniej przetworzonego zbioru,
wskazanie potencjalnie nowych kampanii”) i pracy scrapera.

    python -m embsim.stream_eval [--sample ../data/meta/sample_s1.jsonl] [--limit N] [--profiles ...]

Protokół:
  * reklamy posortowane po `ad_creation_time` (remis: id); 50% najstarszych = GALERIA, następne 20% = WALIDACJA (dobór progu),
    najnowsze 30% = TEST. Test jest oceniany względem galerii + walidacji, z korpusem dopasowanym ponownie (TF-IDF, idf, PCA, bez etykiet).
  * etykieta = twórca (page_id z Ad Library). Zapytanie ma twórcę ZNANEGO (jest w galerii) albo NOWEGO.
  * wynik: najlepsze dopasowanie w galerii (blokowanie kandydatów: top-k gęsty + top-k leksykalny + dokładne klucze host/płatnik/targetowanie).
  * miary: top-1 twórcy dla znanych, „przypięcie” (poprawny twórca ORAZ wynik ≥ próg), odrzucenie nowych (wynik < próg), AUROC
    „znany vs nowy”, pokrycie kandydatów (czy prawdziwy twórca w ogóle trafił do kandydatów).
  * próg wybrany na walidacji (maksimum średniej z czułości przypięcia i odrzucenia nowych), mierzony raz na teście.
  * przedziały ufności: bootstrap po TWÓRCACH (podmiot niezależny; reklamy jednego twórcy nie są niezależne).
Profile cech: „treść” (tekst gęsty z PCA + tekst leksykalny + host + targetowanie) NIE zawiera ani strony, ani płatnika; „treść + płatnik”
dodaje płatnika, który jest silnie związany z twórcą (w grafie płatnik współtworzy definicję twórcy), więc ten wynik jest częściowo
tautologiczny i podajemy go osobno, żeby było widać, ile wnosi.
Ograniczenia: reklamy zdjęte przez Metę nie mają tekstu ani domeny (w próbce S1 ok. jedna trzecia), więc dla nich w profilu „treść”
zostaje tylko targetowanie; podajemy wyniki także dla reklam z treścią. Próbka S1 ma 50% twórców scam (populacja ok. 16%).
"""
from __future__ import annotations

import argparse
import copy
import json
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

from .api import case_from_meta_ad
from .embed import text_vectors
from .features import Case
from .score import Corpus

ROOT = Path(__file__).resolve().parents[3]
MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
ROTATING = {"host", "payer", "targeting"}                  # brak zgodności nie jest dowodem różnicy
CONTENT = {"text": 1.0, "text_lex": 1.0, "host": 1.0, "targeting": 1.0}
PROFILES = {
    "tekst gęsty (PCA)": {"text": 1.0},
    "tekst leksykalny": {"text_lex": 1.0},
    "treść (tekst+leksyka+host+targetowanie)": CONTENT,
    "treść + płatnik": {**CONTENT, "payer": 1.0},
}


# --------------------------------------------------------------------------------------------------------------------
# dane


def load_cases(path: Path, limit: int | None = None) -> list[Case]:
    recs = [json.loads(l) for l in path.open(encoding="utf-8")]
    recs.sort(key=lambda r: (r.get("ad_creation_time") or "", str(r["id"])))
    if limit:
        recs = recs[:limit]
    cases = []
    for r in recs:
        c = case_from_meta_ad(r)
        key = "|".join(str(r.get(k)) for k in ("target_ages", "target_gender", "target_locations") if r.get(k))
        if key:
            c.sets["targeting"] = {key}
        c.meta["page_id"] = str(r["page_id"])
        cases.append(c)
    uniq = sorted({c.text for c in cases if c.text.strip()})
    V = text_vectors(MODEL, uniq) if uniq else np.zeros((0, 1))
    vec = {t: V[i] for i, t in enumerate(uniq)}
    for c in cases:
        if c.text.strip():
            c.vec = vec[c.text]
    return cases


def split_chronological(n: int, fracs=(0.5, 0.2)) -> tuple[range, range, range]:
    a = int(n * fracs[0])
    b = int(n * (fracs[0] + fracs[1]))
    return range(0, a), range(a, b), range(b, n)


# --------------------------------------------------------------------------------------------------------------------
# wyszukiwanie z blokowaniem


class Retriever:
    def __init__(self, gallery: list[Case], weights: dict, k: int = 30, per_key: int = 40):
        self.k, self.per_key = k, per_key
        self.gal = [copy.copy(c) for c in gallery]
        self.w = weights
        self.corpus = Corpus(self.gal, None, weights, rotating=ROTATING & set(weights), trace_mode="overlap", combine="mean",
                             embed_fix="abtt1" if "text" in weights else "none")
        cp = self.corpus
        self.dense = None
        if "text" in weights:
            dim = next(len(cp._sv(c)) for c in self.gal if cp._sv(c) is not None)
            self.dense = np.stack([cp._sv(c) if cp._sv(c) is not None else np.zeros(dim, dtype=np.float32) for c in self.gal])
        self.row2idx = {c.lex_i: i for i, c in enumerate(self.gal) if c.lex_i is not None}
        self.inv: dict[str, dict] = {ch: defaultdict(list) for ch in ("host", "payer", "targeting") if ch in weights}
        for i, c in enumerate(self.gal):
            for ch, d in self.inv.items():
                for x in c.sets.get(ch, ()):
                    d[x].append(i)

    def candidates(self, q: Case) -> set[int]:
        cp, cand = self.corpus, set()
        if self.dense is not None and cp._sv(q) is not None:
            s = self.dense @ cp._sv(q)
            cand.update(np.argpartition(-s, min(self.k, len(s) - 1))[: self.k].tolist())
        if cp._X is not None and q.lex_vec is not None:
            s = np.asarray((cp._X @ q.lex_vec.T).todense()).ravel()
            top = np.argpartition(-s, min(self.k, len(s) - 1))[: self.k]
            cand.update(self.row2idx[r] for r in top.tolist() if r in self.row2idx)
        for ch, d in self.inv.items():
            for x in q.sets.get(ch, ()):
                cand.update(d.get(x, [])[-self.per_key:])
        return cand

    def best(self, q: Case) -> tuple[int | None, float, set[int]]:
        q = self.corpus.prepare(copy.copy(q))
        cand = self.candidates(q)
        best_i, best_s = None, 0.0
        for i in cand:
            s = self.corpus.score(q, self.gal[i]).value
            if s > best_s:
                best_i, best_s = i, s
        return best_i, float(best_s), cand


def run_queries(gallery: list[Case], queries: list[Case], weights: dict) -> list[dict]:
    ret = Retriever(gallery, weights)
    pages = {c.meta["page_id"] for c in gallery}
    hashes = {h for c in gallery for h in c.sets.get("text_hash", ())}
    rows, t0 = [], time.time()
    for q in queries:
        i, s, cand = ret.best(q)
        page = q.meta["page_id"]
        rows.append({"page": page, "best_page": ret.gal[i].meta["page_id"] if i is not None else None, "score": s,
                     "known": page in pages, "has_text": bool(q.text.strip()),
                     "dup": bool(q.sets.get("text_hash", set()) & hashes), "n_cand": len(cand),
                     "cover": any(ret.gal[j].meta["page_id"] == page for j in cand)})
    ms = 1000 * (time.time() - t0) / max(len(queries), 1)
    for r in rows:
        r["ms"] = ms
    return rows


# --------------------------------------------------------------------------------------------------------------------
# miary


def pick_threshold(rows: list[dict]) -> float:
    """Próg maksymalizujący średnią z (czułość przypięcia znanych, odrzucenie nowych); tylko wiersze walidacji."""
    kn = [r for r in rows if r["known"]]
    nw = [r for r in rows if not r["known"]]
    if not kn or not nw:
        return 0.5
    best_t, best_v = 0.5, -1.0
    for t in np.linspace(0, 1, 201):
        tpr = np.mean([(r["best_page"] == r["page"]) and r["score"] >= t for r in kn])
        tnr = np.mean([r["score"] < t for r in nw])
        if (tpr + tnr) / 2 > best_v:
            best_v, best_t = (tpr + tnr) / 2, float(t)
    return best_t


def metrics(rows: list[dict], t: float) -> dict:
    kn = [r for r in rows if r["known"]]
    nw = [r for r in rows if not r["known"]]
    out = {"n": len(rows), "n_znanych": len(kn), "n_nowych": len(nw)}
    out["top1_znani"] = float(np.mean([r["best_page"] == r["page"] for r in kn])) if kn else float("nan")
    out["pokrycie_kandydatów"] = float(np.mean([r.get("cover", False) for r in kn])) if kn else float("nan")
    out["przypięcie_znani"] = float(np.mean([(r["best_page"] == r["page"]) and r["score"] >= t for r in kn])) if kn else float("nan")
    out["odrzucenie_nowych"] = float(np.mean([r["score"] < t for r in nw])) if nw else float("nan")
    if kn and nw:
        y = np.r_[np.ones(len(kn)), np.zeros(len(nw))]
        s = np.r_[[r["score"] for r in kn], [r["score"] for r in nw]]
        out["AUROC_znany_vs_nowy"] = float(roc_auc_score(y, s))
    else:
        out["AUROC_znany_vs_nowy"] = float("nan")
    return out


def cluster_bootstrap(rows: list[dict], t: float, keys: tuple, n: int = 500, seed: int = 0) -> dict[str, tuple[float, float]]:
    """Przedziały 95% przez ponowne losowanie TWÓRCÓW (cały twórca z jego reklamami)."""
    by = defaultdict(list)
    for r in rows:
        by[r["page"]].append(r)
    pages = list(by)
    rng = np.random.default_rng(seed)
    acc = {k: [] for k in keys}
    for _ in range(n):
        sample = [r for p in rng.choice(len(pages), size=len(pages), replace=True) for r in by[pages[p]]]
        m = metrics(sample, t)
        for k in keys:
            if not np.isnan(m[k]):
                acc[k].append(m[k])
    return {k: (float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))) if v else (float("nan"), float("nan")) for k, v in acc.items()}


def slices(rows: list[dict]) -> dict[str, list[dict]]:
    return {"wszystkie": rows, "z treścią": [r for r in rows if r["has_text"]],
            "z treścią, tekst nowy (bez identycznego w galerii)": [r for r in rows if r["has_text"] and not r["dup"]]}


# --------------------------------------------------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sample", type=Path, default=ROOT / "data" / "meta" / "sample_s1.jsonl")
    ap.add_argument("--limit", type=int, default=None, help="tylko N najstarszych reklam (próba dymna)")
    ap.add_argument("--profiles", nargs="*", default=list(PROFILES))
    a = ap.parse_args()
    t0 = time.time()
    cases = load_cases(a.sample, a.limit)
    G, V, T = split_chronological(len(cases))
    print(f"reklam: {len(cases)} | galeria {len(G)}, walidacja {len(V)}, test {len(T)} | wektory tekstu: {time.time() - t0:.0f}s", flush=True)
    dates = [c.meta.get("ad_creation_time", "")[:10] for c in cases]
    print(f"zakresy dat: galeria {dates[G[0]]}..{dates[G[-1]]}, walidacja {dates[V[0]]}..{dates[V[-1]]}, test {dates[T[0]]}..{dates[T[-1]]}")
    report = {}
    keys = ("top1_znani", "przypięcie_znani", "odrzucenie_nowych", "AUROC_znany_vs_nowy")
    for name in a.profiles:
        w = PROFILES[name]
        t1 = time.time()
        val = run_queries([cases[i] for i in G], [cases[i] for i in V], w)
        thr = pick_threshold([r for r in val if True])
        test = run_queries([cases[i] for i in list(G) + list(V)], [cases[i] for i in T], w)
        print(f"\n### {name}  | próg z walidacji {thr:.2f} | {test[0]['ms']:.0f} ms/zapytanie | {time.time() - t1:.0f}s", flush=True)
        known = [r for r in test if r["known"]]
        print(f"  zapytań testowych: {len(test)}, ze znanym twórcą: {len(known)}, nowym: {len(test) - len(known)}; średnio kandydatów: "
              f"{np.mean([r['n_cand'] for r in test]):.0f}")
        print(f"  {'wycinek':<54}{'n zn/now':>10}{'top1':>9}{'przypięcie':>12}{'odrz. nowych':>14}{'AUROC':>8}{'pokrycie':>10}")
        report[name] = {"próg": thr}
        for sl, rows in slices(test).items():
            m = metrics(rows, thr)
            ci = cluster_bootstrap(rows, thr, keys)
            fmt = lambda k: f"{m[k]:.3f}" if not np.isnan(m[k]) else "  -  "
            print(f"  {sl:<54}{m['n_znanych']:>5}/{m['n_nowych']:<4}{fmt('top1_znani'):>9}{fmt('przypięcie_znani'):>12}"
                  f"{fmt('odrzucenie_nowych'):>14}{fmt('AUROC_znany_vs_nowy'):>8}{fmt('pokrycie_kandydatów'):>10}")
            print(f"{'':<54}{'95% CI':>10}" + "".join(f"  [{ci[k][0]:.2f},{ci[k][1]:.2f}]" for k in keys))
            report[name][sl] = {**m, **{f"CI_{k}": ci[k] for k in keys}}
    out = ROOT / "code" / "artifacts" / "stream"
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=float))
    print("\nzapisano:", out / "report.json")


if __name__ == "__main__":
    main()
