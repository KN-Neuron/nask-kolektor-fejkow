"""Niezależny sprawdzian łączenia na PRAWDZIWEJ etykiecie zewnętrznej: reklamy usunięte przez Metę (próbka S1 z Meta Ad Library).

Pytanie: czy nasza miara podobieństwa łączy oszustwo z oszustwem PONAD granicą reklamodawcy? Etykieta pochodzi od Mety, nie od nas, a
metoda jej nie widzi (treść usuniętej reklamy jest podmieniona, a status usunięcia nie jest cechą).

Konstrukcja:
- strona (page_id) jest „skażona”, gdy Meta usunęła choć jedną jej reklamę albo wyłączyła stronę (tekst „removed because it didn't
  follow…” / „later disabled for not following…” zamiast treści);
- bierzemy reklamy Z TREŚCIĄ; dla każdej szukamy najbliższej reklamy z INNEJ strony (ta sama strona byłaby trywialna) profilem
  tekst + leksyka + domena (najlepszy profil na Mecie, docs/WYNIKI.md §3), z blokowaniem kandydatów jak w stream_eval;
- sprawdzamy, czy skażenie sąsiada przewiduje skażenie reklamy, i czy rośnie to z wynikiem podobieństwa (jeśli łączymy kampanie, a nie
  tylko temat, przy wysokim wyniku zgodność powinna być wyraźnie wyższa niż przy niskim).

Ograniczenia: skażenie strony to etykieta „oszust”, nie „ta sama kampania”; część zgodności może wynikać z tematu (kryptowaluty, zdrowie)
a nie z kampanii, dlatego raportujemy zależność od wyniku i osobno identyczne teksty. Przedziały: bootstrap po stronach.

    PYTHONPATH=src .venv/bin/python scripts/walidacja_usuniecia.py [--limit N]   -> artifacts/walidacja/usuniecia.md
"""
from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

from embsim.stream_eval import ROOT, Retriever, load_cases

FLAGS = ("removed because it didn", "later disabled for not following")   # tekst Mety zamiast treści usuniętej reklamy

SAMPLE = ROOT / "data" / "meta" / "sample_s1.jsonl"
OUT = ROOT / "code" / "artifacts" / "walidacja"
WEIGHTS = {"text": 1.0, "text_lex": 1.0, "host": 1.0}
BINS = [(0.0, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 0.9), (0.9, 1.01)]


def flagged(r: dict) -> bool:
    vals = [*(r.get("ad_creative_bodies") or []), *(r.get("ad_creative_link_titles") or [])]
    return any(f in str(v) for v in vals for f in FLAGS)


def tainted_pages(path: Path) -> set[str]:
    out = set()
    for line in path.open(encoding="utf-8"):
        r = json.loads(line)
        if flagged(r):
            out.add(str(r["page_id"]))
    return out


def nearest_other_page(ret: Retriever, q) -> tuple[int | None, float]:
    qq = ret.corpus.prepare(__import__("copy").copy(q))
    best_i, best_s = None, -1.0
    for i in ret.candidates(qq):
        g = ret.gal[i]
        if g.meta["page_id"] == q.meta["page_id"]:
            continue
        s = ret.corpus.score(qq, g).value
        if s > best_s:
            best_i, best_s = i, s
    return best_i, max(best_s, 0.0)


def boot_diff(rows: list[dict], n: int = 500, seed: int = 0) -> tuple[float, float]:
    """95% przedział różnicy P(skażona | sąsiad skażony) − P(skażona | sąsiad czysty), bootstrap po stronach."""
    by = defaultdict(list)
    for r in rows:
        by[r["page"]].append(r)
    pages = list(by)
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        sample = [r for p in rng.choice(pages, len(pages)) for r in by[p]]
        a = [r["y"] for r in sample if r["yn"]]
        b = [r["y"] for r in sample if not r["yn"]]
        if a and b:
            out.append(np.mean(a) - np.mean(b))
    return (float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))) if out else (float("nan"), float("nan"))


def report(rows: list[dict], n_all: int, n_pages_t: int, n_pages: int, secs: float) -> str:
    y = np.array([r["y"] for r in rows])
    base = y.mean()
    md = ["# Sprawdzian na etykiecie usunięć Mety", "",
          f"Próbka S1: {n_all} reklam, z treścią {len(rows)}; stron {n_pages}, skażonych {n_pages_t}. Odsetek reklam ze skażonych stron "
          f"wśród reklam z treścią: **{base:.3f}** (poziom bazowy). Profil: tekst + leksyka + domena. Czas: {secs:.0f} s.", "",
          "## Zgodność z najbliższą reklamą INNEJ strony, wg wyniku podobieństwa", "",
          "| wynik | reklam | P(skażona | sąsiad skażony) | P(skażona | sąsiad czysty) | różnica [95% CI po stronach] | zgodność etykiet |",
          "|---|---|---|---|---|---|"]
    for lo, hi in BINS:
        sub = [r for r in rows if lo <= r["s"] < hi]
        if not sub:
            continue
        a = [r["y"] for r in sub if r["yn"]]
        b = [r["y"] for r in sub if not r["yn"]]
        lo_ci, hi_ci = boot_diff(sub, n=300)
        pa = np.mean(a) if a else float("nan")
        pb = np.mean(b) if b else float("nan")
        agree = np.mean([r["y"] == r["yn"] for r in sub])
        md.append(f"| {lo:.1f}–{min(hi, 1):.1f} | {len(sub)} | {pa:.3f} (n={len(a)}) | {pb:.3f} (n={len(b)}) | {pa - pb:+.3f} "
                  f"[{lo_ci:+.3f}; {hi_ci:+.3f}] | {agree:.3f} |")
    signed = np.array([r["s"] if r["yn"] else -r["s"] for r in rows])
    auc = roc_auc_score(y, signed) if 0 < base < 1 else float("nan")
    md += ["", f"AUROC przewidywania skażenia z (wynik × znak sąsiada): **{auc:.3f}** (0,5 = brak informacji).", ""]
    for name, sel in (("bez identycznych tekstów (sąsiad z innym tekstem)", lambda r: not r["dup"]),
                      ("tylko identyczne teksty na różnych stronach", lambda r: r["dup"])):
        sub = [r for r in rows if sel(r)]
        a = [r["y"] for r in sub if r["yn"] and r["s"] >= 0.5]
        b = [r["y"] for r in sub if not r["yn"] and r["s"] >= 0.5]
        if a and b:
            ci = boot_diff([r for r in sub if r["s"] >= 0.5], n=300)
            md.append(f"- {name}, wynik ≥ 0,5: P(skażona | sąsiad skażony) {np.mean(a):.3f} (n={len(a)}) wobec "
                      f"{np.mean(b):.3f} (n={len(b)}), różnica {np.mean(a) - np.mean(b):+.3f} [{ci[0]:+.3f}; {ci[1]:+.3f}]")
        else:
            md.append(f"- {name}: za mało par z wynikiem ≥ 0,5 (n={len(a)} i {len(b)})")
    return "\n".join(md) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sample", type=Path, default=SAMPLE)
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    t0 = time.time()
    bad = tainted_pages(a.sample)
    cases = load_cases(a.sample, a.limit)
    content = [c for c in cases if c.text.strip()]
    print(f"reklam {len(cases)}, z treścią {len(content)}, skażonych stron {len(bad)}; wektory gotowe po {time.time() - t0:.0f} s", flush=True)
    ret = Retriever(content, WEIGHTS)
    hashes = [c.sets.get("text_hash", set()) for c in content]
    rows = []
    for n, q in enumerate(content):
        i, s = nearest_other_page(ret, q)
        if n % 1000 == 0:
            print(f"  {n}/{len(content)}  {time.time() - t0:.0f} s", flush=True)
        if i is None:
            continue
        rows.append({"page": q.meta["page_id"], "y": int(q.meta["page_id"] in bad), "yn": int(ret.gal[i].meta["page_id"] in bad),
                     "s": float(s), "dup": bool(hashes[n] & hashes[i])})
    OUT.mkdir(parents=True, exist_ok=True)
    md = report(rows, len(cases), len({c.meta["page_id"] for c in cases} & bad), len({c.meta["page_id"] for c in cases}), time.time() - t0)
    (OUT / "usuniecia.md").write_text(md, encoding="utf-8")
    (OUT / "usuniecia_wiersze.json").write_text(json.dumps(rows), encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
