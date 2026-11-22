"""Planista: okresowe zbieranie nowych materiałów, ocena względem galerii i alerty (dodatkowo punktowane w opisie wyzwania).

Jeden przebieg (`run_once`):
1. zbiera NOWE materiały (pamięta, co już widział, w pliku stanu) z jednego lub kilku źródeł:
   - `--inbox FOLDER`: podfoldery przypadków (HTML, HAR, zrzuty) i pliki JSONL z reklamami Meta wrzucane do folderu,
   - `--urls PLIK`: lista adresów (jeden na linię); z `--fetch` strona jest pobierana (embsim/fetch.py), bez niego tylko domena i schemat,
   - `--meta-keywords PLIK`: wyszukiwanie w Meta Ad Library po słowach kluczowych (wymaga META_ACCESS_TOKEN w code/.env);
2. każdy materiał dostaje decyzję względem galerii (znana kampania / znany operator, nowa kampania / nowy wzorzec) i trafia do galerii,
   więc kolejne odsłony tej samej kampanii łączą się także między sobą;
3. wynik dopisywany do `alerty.jsonl` i `alerty.csv` (czas, źródło, werdykt, kampania, najbliższy materiał, powody); po przebiegu grupy są
   liczone od nowa na pełnej galerii (`Gallery.regroup`) i zapisane obok jako „po przeliczeniu”; galeria zapisana.

    PYTHONPATH=src python -m embsim.watch --inbox ../data/skrzynka --every-min 60
    PYTHONPATH=src python -m embsim.watch --urls adresy.txt --fetch            # jeden przebieg
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from . import analyze as A
from .api import Gallery, case_from_meta_ad

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "code" / "artifacts" / "watch"


def _state(out: Path) -> set[str]:
    p = out / "widziane.json"
    return set(json.loads(p.read_text())) if p.exists() else set()


def _save_state(out: Path, seen: set[str]) -> None:
    (out / "widziane.json").write_text(json.dumps(sorted(seen), ensure_ascii=False))


def from_inbox(inbox: Path):
    """(klucz, źródło, Case) dla podfolderów przypadków i rekordów JSONL z reklamami Meta."""
    for d in A.case_dirs(inbox):
        if d == inbox:
            continue
        stamp = max((p.stat().st_mtime for p in d.rglob("*") if p.is_file()), default=0)
        c = A.case_from_folder(d)
        c.id = d.name
        yield f"dir:{d.name}:{stamp:.0f}", f"folder {d.name}", c
    for f in sorted(inbox.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
                c = case_from_meta_ad(r)
            except (ValueError, KeyError):
                continue
            yield f"meta:{c.id}", f"reklama Meta {c.id} ({f.name})", c


def from_urls(path: Path, fetch: bool):
    for line in path.read_text(encoding="utf-8").splitlines():
        u = line.strip()
        if not u or u.startswith("#"):
            continue
        key = "url:" + hashlib.sha1(u.encode()).hexdigest()[:16]
        c, info = A.case_from_inputs([], "", u, ocr=False, fetch=fetch, case_id=key)
        yield key, f"adres {u[:80]}" + (f" ({'; '.join(info['ostrzeżenia'])})" if info["ostrzeżenia"] else ""), c


def from_meta(keywords: Path, days: int, max_pages: int, cache: Path):
    """Meta Ad Library przez kolektor z poprzedniego silnika (fejki.sources.meta_library). Bez tokenu: MetaError."""
    from fejki.sources.meta_library import Collector, load_ads

    terms = [t.strip() for t in keywords.read_text(encoding="utf-8").splitlines() if t.strip() and not t.startswith("#")]
    col = Collector(cache, log=lambda *a: None)
    col.keywords(terms, days=days, max_pages=max_pages)
    for r in load_ads(cache / "ads.jsonl"):
        c = case_from_meta_ad(r)
        yield f"meta:{c.id}", f"Meta Ad Library {c.id}", c


def run_once(g: Gallery, sources, out: Path = OUT, log=print) -> list[dict]:
    out.mkdir(parents=True, exist_ok=True)
    seen, rows = _state(out), []
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for src in sources:
        for key, label, c in src:
            if key in seen:
                continue
            seen.add(key)
            if not (c.text.strip() or c.sets):
                continue
            if c.id in g._ids:
                c.id = f"{c.id}@{now}"
            d = g.add(c)
            m = d.key_match()
            row = {"czas": now, "źródło": label, "materiał": c.id, "werdykt": A.verdict_style(d)[1], "kampania": d.group,
                   "operator": d.operator, "najbliższy": m.id if m else "", "wynik kampanii": round(d.campaign_score, 3),
                   "powody": "; ".join(A.top_reasons(m)) if m else ""}
            rows.append(row)
            log(f"[{d.verdict}] {label} -> {d.group or '-'} ({row['powody'][:100]})")
    _save_state(out, seen)
    if rows:
        g.regroup()                                   # grupy na pełnej galerii: pierwsze decyzje przy małej galerii zapadały bez tła
        lab = {it["case"].id: (it["group"], it["operator"]) for it in g.items}
        for r in rows:
            r["kampania po przeliczeniu"], r["operator po przeliczeniu"] = lab.get(r["materiał"], (r["kampania"], r["operator"]))
        import pandas as pd

        with (out / "alerty.jsonl").open("a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        csv = out / "alerty.csv"
        pd.DataFrame(rows).to_csv(csv, mode="a", header=not csv.exists(), index=False)
    return rows


def read_alerts(out: Path = OUT, last: int = 200) -> list[dict]:
    p = out / "alerty.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()[-last:] if l.strip()]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gallery", default=os.environ.get("EMBSIM_GALLERY", str(ROOT / "code" / "artifacts" / "gallery_demo.jsonl")))
    ap.add_argument("--inbox", type=Path)
    ap.add_argument("--urls", type=Path)
    ap.add_argument("--fetch", action="store_true", help="pobieraj strony spod adresów (domyślnie tylko domena i schemat)")
    ap.add_argument("--meta-keywords", type=Path)
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--max-pages", type=int, default=2)
    ap.add_argument("--every-min", type=int, default=0, help="co ile minut (0 = jeden przebieg)")
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args()
    if not (a.inbox or a.urls or a.meta_keywords):
        ap.error("podaj co najmniej jedno źródło: --inbox, --urls albo --meta-keywords")
    gp = Path(a.gallery)
    profile = "meta" if a.meta_keywords and not (a.inbox or a.urls) else "strony"
    g = Gallery.load(gp, profile=profile) if gp.exists() else Gallery(profile=profile)
    print(f"galeria: {len(g)} materiałów ({gp}); alerty: {a.out}")
    while True:
        srcs = []
        if a.inbox:
            srcs.append(from_inbox(a.inbox))
        if a.urls:
            srcs.append(from_urls(a.urls, a.fetch))
        if a.meta_keywords:
            srcs.append(from_meta(a.meta_keywords, a.days, a.max_pages, a.out / "meta"))
        try:
            rows = run_once(g, srcs, a.out)
            gp.parent.mkdir(parents=True, exist_ok=True)
            g.save(gp)
            print(f"{datetime.now():%H:%M} przebieg: nowych materiałów {len(rows)}, galeria {len(g)}")
        except Exception as e:                       # jeden nieudany przebieg (sieć, token) nie zatrzymuje planisty
            print(f"przebieg nieudany: {type(e).__name__}: {e}")
        if not a.every_min:
            return
        time.sleep(a.every_min * 60)


if __name__ == "__main__":
    main()
