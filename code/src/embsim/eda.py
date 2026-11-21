"""EDA: co w danych jest dostępne i które cechy faktycznie wskazują na tego samego twórcę.

    python -m embsim.eda meta  [ads.jsonl]      # reklamy Meta: kompletność, rozkłady, informatywność cech
    python -m embsim.eda cases                  # NASK-10 + urlscan: dostępność kanałów

Informatywność cechy X dla poziomu „twórca” (reklamodawca = page_id): z par reklam, które dzielą wartość X (grupy o rozmiarze 2..cap),
jaki odsetek ma tego samego twórcę (precyzja), jaki odsetek wszystkich par „ten sam twórca” w ogóle dzieli X (czułość), oraz ile razy
precyzja przewyższa losową (lift). Cecha, która nie ma zasięgu albo lifta ~1, nie pomoże. To opis danych, nie ocena modelu; etykieta
„twórca” jest z Ad Library (page_id), a nie z naszej analizy.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
FLAGS = ("removed because it didn", "later disabled for not following")
HOST = re.compile(r"^(?:[a-z0-9-]+\.)+[a-z]{2,}$")
CAP = 200


def first(v):
    if isinstance(v, str) and v[:1] in "[{":
        try:
            import ast

            v = ast.literal_eval(v)
        except (ValueError, SyntaxError):
            return v
    if isinstance(v, list):
        return v[0] if v else None
    return v


def load_meta(path: Path) -> list[dict]:
    rows = []
    for line in path.open(encoding="utf-8"):
        r = json.loads(line)
        body, title, cap = (first(r.get(k)) for k in ("ad_creative_bodies", "ad_creative_link_titles", "ad_creative_link_captions"))
        pays = r.get("beneficiary_payers")
        pays = pays if isinstance(pays, list) else []
        flagged = any(f in " ".join(str(first(r.get(k)) or "") for k in ("ad_creative_bodies", "ad_creative_link_captions")) for f in FLAGS)
        text = "" if flagged else (body or "")
        rows.append({
            "page": r["page_id"], "payer": pays[0]["payer"] if pays and isinstance(pays[0], dict) else None,
            "domain": cap.lower() if isinstance(cap, str) and HOST.match(cap.lower()) else None,
            "title": None if flagged else title, "text_h": hashlib.sha1(text.encode()).hexdigest()[:12] if text.strip() else None,
            "text_len": len(text), "flagged": flagged, "lang": first(r.get("languages")),
            "platforms": ",".join(sorted(r.get("publisher_platforms") or [])) or None,
            "ages": json.dumps(r.get("target_ages"), sort_keys=True) if r.get("target_ages") else None,
            "gender": str(r.get("target_gender")) if r.get("target_gender") else None,
            "loc": json.dumps(sorted(str(x) for x in (r.get("target_locations") or []))[:8]) if r.get("target_locations") else None,
            "reach": r.get("eu_total_reach"), "query": r.get("_query"),
            "start": (r.get("ad_delivery_start_time") or "")[:10] or None,
            "stop": (r.get("ad_delivery_stop_time") or "")[:10] or None, "created": (r.get("ad_creation_time") or "")[:7] or None,
        })
    return rows


def c2(n):
    return n * (n - 1) // 2


def informativeness(rows: list[dict], feats: list[str], cap: int = CAP) -> list[dict]:
    n = len(rows)
    page = [r["page"] for r in rows]
    same_total = sum(c2(c) for c in Counter(page).values())
    base = same_total / c2(n)
    out = []
    for f in feats:
        groups = defaultdict(list)
        for i, r in enumerate(rows):
            if r[f] is not None:
                groups[r[f]].append(i)
        shared = same = covered = 0
        for g in groups.values():
            if not (2 <= len(g) <= cap):
                continue
            covered += len(g)
            shared += c2(len(g))
            same += sum(c2(c) for c in Counter(page[i] for i in g).values())
        out.append({"cecha": f, "zasięg": covered / n, "par_wspólnych": shared, "precyzja": same / shared if shared else float("nan"),
                    "czułość": same / same_total if same_total else float("nan"),
                    "lift": (same / shared) / base if shared and base else float("nan")})
    return out


def eda_meta(path: Path) -> None:
    rows = load_meta(path)
    n = len(rows)
    print(f"reklam: {n}")
    print("\n== kompletność pól (odsetek niepustych)")
    for k in ("text_h", "title", "domain", "payer", "lang", "platforms", "ages", "loc", "reach", "stop"):
        print(f"  {k:<10}{sum(r[k] is not None for r in rows) / n:>7.1%}")
    print(f"  oznaczone przez Metę (usunięte/zablokowane, bez treści): {sum(r['flagged'] for r in rows) / n:.1%}")
    tl = np.array([r["text_len"] for r in rows if r["text_len"]])
    print(f"  długość tekstu (znaki): mediana {np.median(tl):.0f}, p95 {np.percentile(tl, 95):.0f}")

    print("\n== twórcy i koncentracja")
    per_page = Counter(r["page"] for r in rows)
    v = np.array(sorted(per_page.values(), reverse=True))
    print(f"  reklamodawców (stron): {len(v)}, reklam na stronę: mediana {np.median(v):.0f}, p99 {np.percentile(v, 99):.0f}, max {v[0]}")
    print(f"  10 największych stron to {v[:10].sum() / n:.1%} reklam; strony z 1 reklamą: {(v == 1).sum() / len(v):.1%}")
    pg_pay = defaultdict(set)
    pay_pg = defaultdict(set)
    for r in rows:
        if r["payer"]:
            pg_pay[r["page"]].add(r["payer"]); pay_pg[r["payer"]].add(r["page"])
    print(f"  płatników: {len(pay_pg)}; stron na płatnika: mediana {np.median([len(s) for s in pay_pg.values()]):.0f}, "
          f"max {max(len(s) for s in pay_pg.values())}; płatników z ≥2 stronami: {sum(len(s) >= 2 for s in pay_pg.values())}")

    print("\n== duplikacja tekstu")
    th = Counter(r["text_h"] for r in rows if r["text_h"])
    print(f"  unikalnych tekstów: {len(th)} na {sum(th.values())} reklam z tekstem; najczęstszy ×{th.most_common(1)[0][1]}")
    by_text = defaultdict(set)
    for r in rows:
        if r["text_h"]:
            by_text[r["text_h"]].add(r["page"])
    rep = [s for h, s in by_text.items() if th[h] >= 2]
    print(f"  teksty użyte ≥2 razy: {len(rep)}; z nich u ≥2 różnych twórców: {sum(len(s) >= 2 for s in rep)} "
          f"({sum(len(s) >= 2 for s in rep) / max(len(rep), 1):.1%})")

    print("\n== obciążenie doboru (słowa kluczowe wyszukania)")
    q = Counter(r["query"] for r in rows)
    print(f"  zapytań: {len(q)}; reklam na zapytanie: min {min(q.values())}, mediana {np.median(list(q.values())):.0f}, max {max(q.values())}")
    print(f"  zapytań z dokładnie 2000 (= limit zbierania): {sum(c == 2000 for c in q.values())}")
    for k, c in q.most_common(6):
        print(f"    {k}: {c}")
    mo = Counter(r["created"] for r in rows if r["created"])
    print("  reklamy wg miesiąca utworzenia (ostatnie 6):", dict(sorted(mo.items())[-6:]))
    print("  języki:", dict(Counter(r["lang"] for r in rows).most_common(5)))

    print(f"\n== informatywność cech dla poziomu „twórca” (grupy 2..{CAP} reklam)")
    base = sum(c2(c) for c in per_page.values()) / c2(n)
    print(f"  losowa para ma tego samego twórcę z p={base:.5f}")
    feats = ["text_h", "title", "domain", "payer", "ages", "gender", "loc", "platforms", "lang", "start", "query"]
    print(f"  {'cecha':<10}{'zasięg':>9}{'par':>12}{'precyzja':>10}{'czułość':>9}{'lift':>10}")
    for d in sorted(informativeness(rows, feats), key=lambda d: -(d["lift"] if d["lift"] == d["lift"] else 0)):
        print(f"  {d['cecha']:<10}{d['zasięg']:>9.1%}{d['par_wspólnych']:>12}{d['precyzja']:>10.3f}{d['czułość']:>9.3f}{d['lift']:>10.1f}")
    # cechy złożone: pojedyncze są słabe, a kombinacja targetowania bywa swoista
    for r in rows:
        r["targeting"] = "|".join(str(r[k]) for k in ("ages", "gender", "loc")) if r["ages"] and r["loc"] else None
        r["domain+payer"] = f"{r['domain']}|{r['payer']}" if r["domain"] and r["payer"] else None
    print("  złożone:")
    for d in informativeness(rows, ["targeting", "domain+payer"]):
        print(f"  {d['cecha']:<14}{d['zasięg']:>5.1%}{d['par_wspólnych']:>12}{d['precyzja']:>10.3f}{d['czułość']:>9.3f}{d['lift']:>10.1f}")


def eda_cases() -> None:
    from .features import load_case
    from .material import load_case as mat

    nask = ROOT / "data" / "dane" / "do_udostępnienia"
    print("== NASK-10: dostępność kanałów (liczby)")
    print(f"  {'przyp.':<8}{'html':>5}{'har':>5}{'obr.':>5}{'wideo':>6}{'info':>5}{'znaki':>7}{'piksel':>7}{'zestaw':>7}{'schemat':>8}{'host':>5}")
    for d in sorted((p for p in nask.iterdir() if p.is_dir()), key=lambda p: int(p.name)):
        files = [p for p in d.rglob("*") if p.is_file() and not any(x.name.endswith("_files") for x in p.parents if x != d)]
        ext = Counter(p.suffix.lower() for p in files)
        c = load_case(d)
        m = mat(d)
        print(f"  {d.name:<8}{ext['.html'] + ext['.htm']:>5}{ext['.har']:>5}{len(m.images):>5}{ext['.mp4'] + ext['.mov']:>6}"
              f"{sum(p.name.endswith('.info.json') for p in files):>5}{len(c.text):>7}"
              + "".join(f"{len(c.sets.get(k, ())):>{w}}" for k, w in (("pixel", 7), ("kit", 7), ("scheme", 8), ("host", 5))))
    lab = ROOT / "data" / "urlscan" / "labels.csv"
    if lab.exists():
        import csv

        rows = list(csv.DictReader(lab.open(encoding="utf-8")))
        print(f"\n== urlscan: {len(rows)} skanów; etykiety: {dict(Counter((r['label'], r['kind']) for r in rows))}")
        dirs = [ROOT / "data" / "urlscan" / r["case_id"] for r in rows]
        print(f"  mają zrzut: {sum((d / 'screenshot.png').exists() for d in dirs)}, mają urlscan.json: {sum((d / 'urlscan.json').exists() for d in dirs)}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "meta"
    if cmd == "meta":
        eda_meta(Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "data" / "meta" / "ads.jsonl")
    else:
        eda_cases()
