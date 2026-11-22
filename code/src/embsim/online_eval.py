"""Ocena ścieżki online na reklamach Meta: galeria zaczyna pusta, reklamy przychodzą chronologicznie i każda jest oceniana TYM SAMYM kodem, którego używa
interfejs, CLI i scraper (`Gallery.query` / `add`, profil „meta”).

    python -m embsim.online_eval [--creators 150] [--seed 7]

Prawdy kampanii na Mecie nie ma; proxy: twórca (`page_id`). Dla każdej reklamy zapisujemy, zanim trafi do galerii: wynik kampanii najlepszego
dopasowania i czy ten dopasowany materiał ma tego samego twórcę. Grupy nie wpływają na wyniki kampanii, więc jeden przebieg wystarcza do
przeliczenia dowolnego progu (pomiar progu = filtr po zapisanych wynikach, bez ponownego liczenia).

Miary przy progu t (decyzja „znana kampania” = wynik ≥ t):
  precyzja   spośród reklam uznanych za znaną kampanię: odsetek z poprawnym twórcą najlepszego dopasowania,
  czułość    spośród reklam, których twórca był już w galerii: odsetek uznanych i z poprawnym twórcą,
  odrzucenie spośród reklam z twórcą spoza galerii: odsetek zostawionych jako nowe (nie uznanych za znaną kampanię).
Rozbicie po rozmiarze galerii w chwili zapytania (do 100, 100–300, ponad 300 materiałów), bo dla małej galerii wynik jest najsłabszy.
Przedziały: bootstrap po twórcach.
"""
from __future__ import annotations

import argparse
import copy
import json
import random
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from .api import Gallery, case_from_meta_ad, has_evidence
from .embed import text_vectors
from .stream_eval import MODEL, log

ROOT = Path(__file__).resolve().parents[3]
STAGES = (("do 100", 0, 100), ("100–300", 100, 300), ("ponad 300", 300, 10**9))


def load(path: Path, n_creators: int, seed: int):
    cases = []
    for line in path.open(encoding="utf-8"):
        r = json.loads(line)
        c = case_from_meta_ad(r)
        if r.get("page_id") and not c.meta.get("flagged_by_meta") and c.text.strip():
            c.meta["page_id"] = str(r["page_id"])
            cases.append(c)
    by = defaultdict(list)
    for c in cases:
        by[c.meta["page_id"]].append(c)
    pages = sorted(p for p, v in by.items() if len(v) >= 3)
    random.Random(seed).shuffle(pages)
    sel = [c for p in pages[:n_creators] for c in sorted(by[p], key=lambda c: c.meta.get("ad_creation_time", ""))[:10]]
    sel.sort(key=lambda c: (c.meta.get("ad_creation_time", ""), c.id))
    uniq = sorted({c.text for c in sel})
    V = text_vectors(MODEL, uniq)
    vec = {t: V[i] for i, t in enumerate(uniq)}
    for c in sel:
        c.vec = vec[c.text]
    return sel


def replay(sel) -> list[dict]:
    g = Gallery(profile="meta")
    owner: dict[str, str] = {}
    seen: set[str] = set()
    rows, t0 = [], time.time()
    for n, c in enumerate(sel, 1):
        page = c.meta["page_id"]
        row = {"page": page, "known": page in seen, "size": len(g), "score": 0.0, "hit": False}
        if len(g):
            d = g.query(copy.deepcopy(c), 5)
            if d.matches:
                best = max(d.matches, key=lambda m: m.campaign_score)
                row["score"], row["hit"] = float(best.campaign_score), owner.get(best.id) == page
        rows.append(row)
        g.add(copy.deepcopy(c))
        owner[c.id] = page
        seen.add(page)
        if n % 200 == 0:
            log(f"[online] {n}/{len(sel)} reklam, {time.time() - t0:.0f}s")
    return rows


def metrics(rows: list[dict], t: float) -> dict:
    pred = [r for r in rows if r["score"] >= t]
    known = [r for r in rows if r["known"]]
    new = [r for r in rows if not r["known"] and r["size"] > 0]
    return {"n": len(rows), "uznane": len(pred),
            "precyzja": float(np.mean([r["hit"] for r in pred])) if pred else float("nan"),
            "czułość": float(np.mean([r["score"] >= t and r["hit"] for r in known])) if known else float("nan"),
            "odrzucenie": float(np.mean([r["score"] < t for r in new])) if new else float("nan")}


def boot(rows: list[dict], t: float, key: str, n: int = 300, seed: int = 0) -> tuple[float, float]:
    by = defaultdict(list)
    for r in rows:
        by[r["page"]].append(r)
    pages = list(by)
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        s = [r for p in rng.choice(pages, len(pages)) for r in by[p]]
        v = metrics(s, t)[key]
        if v == v:
            out.append(v)
    return (float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))) if out else (float("nan"), float("nan"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", default=str(ROOT / "data" / "meta" / "sample_s1.jsonl"))
    ap.add_argument("--creators", type=int, default=150)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    sel = load(Path(a.sample), a.creators, a.seed)
    log(f"próbka: {len(sel)} reklam z treścią od {len({c.meta['page_id'] for c in sel})} twórców; start od pustej galerii")
    rows = replay(sel)
    (ROOT / "code" / "artifacts" / "online_eval.json").write_text(json.dumps(rows), encoding="utf-8")
    print("\nPRÓG KAMPANII (profil meta = 0,5 domyślnie); metryki całości, w nawiasie 95% CI po twórcach")
    for t in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9):
        m = metrics(rows, t)
        ci = {k: boot(rows, t, k) for k in ("precyzja", "czułość", "odrzucenie")}
        print(f"t={t:.1f}: uznane {m['uznane']:>4}  " + "  ".join(f"{k} {m[k]:.2f} [{ci[k][0]:.2f}; {ci[k][1]:.2f}]" for k in ci))
    print("\nROZMIAR GALERII (t = 0,5)")
    for name, lo, hi in STAGES:
        sub = [r for r in rows if lo <= r["size"] < hi]
        if sub:
            m = metrics(sub, 0.5)
            print(f"{name:<10} n={m['n']:>4}  uznane {m['uznane']:>4}  precyzja {m['precyzja']:.2f}  czułość {m['czułość']:.2f}  odrzucenie {m['odrzucenie']:.2f}")


if __name__ == "__main__":
    main()
