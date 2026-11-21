"""Podział na podmioty (subjects) policzony z grafu: składowe spójne reklam połączonych śladami operatora.

    .venv/bin/python graph/subjects.py stats              # rozmiar największej składowej przy różnych limitach hubów
    .venv/bin/python graph/subjects.py split --hub-cap 100 --write-graph

Zasady:
- podmiot = składowa spójna grafu Ad–{Advertiser, Payer, Domain, identyczny tekst}; ślady tematyczne (słowo kluczowe, osoba) NIE łączą;
- węzeł-hub (stopień > hub_cap: duży legalny reklamodawca, `youtube.com`, płatnik „Advertiser”) NIE skleja podmiotów,
  bo inaczej cały zbiór wpada w jedną składową; dla każdego hubu raportujemy, czy jego reklamy trafiły do wielu foldów;
- cały podmiot trafia do jednego foldu, więc warianty jednej kampanii nie rozjeżdżają się między trening i test;
- `audit` zwraca każdy wspólny ślad nie-hub między foldami; poprawny podział = pusta lista.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "splits"
LINK_TYPES = ("BY", "PAID_BY", "LINKS_TO")
FOLDS = ("train", "val", "test")

Edge = tuple[str, str]  # (id materiału, klucz węzła-śladu, np. "PAID_BY:Eastmoor Media")


# --------------------------------------------------------------------------------------------------------------------
# czysta logika (testowana bez bazy)


def degrees(edges: list[Edge]) -> Counter:
    return Counter(n for _, n in set(edges))


def hubs(edges: list[Edge], hub_cap: int | None) -> set[str]:
    if hub_cap is None:
        return set()
    return {n for n, d in degrees(edges).items() if d > hub_cap}


def components(ids: list[str], edges: list[Edge], hub_cap: int | None = 100) -> dict[str, int]:
    """Materiał -> numer podmiotu. Węzły-huby nie łączą; materiał bez śladów jest sam sobie podmiotem."""
    parent = {i: i for i in ids}

    def find(a: str) -> str:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    skip = hubs(edges, hub_cap)
    first: dict[str, str] = {}
    for m, n in edges:
        if n in skip or m not in parent:
            continue
        if n in first:
            parent[find(m)] = find(first[n])
        else:
            first[n] = m
    roots: dict[str, int] = {}
    return {i: roots.setdefault(find(i), len(roots)) for i in ids}


def assign_folds(subject_of: dict[str, int], fractions=(0.7, 0.15, 0.15), seed: int = 1) -> dict[int, str]:
    """Podmiot -> fold. Zachłannie od największych, do foldu z największym niedoborem względem docelowego udziału."""
    size = Counter(subject_of.values())
    total = sum(size.values())
    target = {f: total * p for f, p in zip(FOLDS, fractions)}
    have = dict.fromkeys(FOLDS, 0)
    rng = random.Random(seed)
    order = sorted(size, key=lambda s: (-size[s], rng.random()))
    out: dict[int, str] = {}
    for s in order:
        f = max(FOLDS, key=lambda k: (target[k] - have[k], rng.random()))
        out[s] = f
        have[f] += size[s]
    return out


def audit(fold_of: dict[str, str], edges: list[Edge], hub_cap: int | None) -> dict:
    """Wspólne ślady między foldami. `leaks` (nie-huby) musi być puste; `hub_cross` to znane, jawne wyjątki."""
    skip = hubs(edges, hub_cap)
    folds_of: dict[str, set[str]] = defaultdict(set)
    for m, n in edges:
        if m in fold_of:
            folds_of[n].add(fold_of[m])
    leaks = sorted(n for n, fs in folds_of.items() if len(fs) > 1 and n not in skip)
    hub_cross = sorted(n for n, fs in folds_of.items() if len(fs) > 1 and n in skip)
    return {"leaks": leaks, "hub_cross": hub_cross, "n_hubs": len(skip)}


# --------------------------------------------------------------------------------------------------------------------
# Neo4j


def fetch(session) -> tuple[list[str], list[Edge]]:
    ids = [r["id"] for r in session.run("MATCH (a:Ad) RETURN a.id AS id")]
    q = ("MATCH (a:Ad)-[r:" + "|".join(LINK_TYPES) + "]->(x) "
         "RETURN a.id AS a, type(r) + ':' + toString(coalesce(x.key, x.name)) AS n")
    edges = [(r["a"], r["n"]) for r in session.run(q)]
    # identyczny tekst reklamy to też ślad (ten sam przekaz); bez tego ten sam tekst mógłby trafić do train i test
    edges += [(r["a"], "TEXT:" + r["h"]) for r in
              session.run("MATCH (a:Ad) WHERE a.text_hash IS NOT NULL RETURN a.id AS a, a.text_hash AS h")]
    return ids, edges


def write_graph(session, fold_of: dict[str, str], subject_of: dict[str, int]) -> None:
    rows = [{"id": i, "fold": fold_of[i], "subject": subject_of[i]} for i in fold_of]
    for k in range(0, len(rows), 5000):
        session.run("UNWIND $rows AS r MATCH (a:Ad {id: r.id}) SET a.fold = r.fold, a.subject = r.subject",
                    rows=rows[k:k + 5000]).consume()


def main() -> None:
    sys.path.insert(0, str(Path(__file__).parent))
    from load import driver

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["stats", "split"])
    ap.add_argument("--hub-cap", type=int, default=100)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--write-graph", action="store_true", help="zapisz Ad.fold i Ad.subject w bazie")
    args = ap.parse_args()
    drv = driver()
    with drv.session() as s:
        ids, edges = fetch(s)
        if args.what == "stats":
            for cap in (None, 1000, 300, 100, 50, 20):
                sub = components(ids, edges, cap)
                sz = Counter(sub.values())
                top = sz.most_common(3)
                print(f"hub_cap={cap!s:>5}  podmiotów={len(sz):>6}  największe={[n for _, n in top]}  "
                      f"solo={sum(1 for n in sz.values() if n == 1)}  huby={len(hubs(edges, cap))}")
            return
        sub = components(ids, edges, args.hub_cap)
        fold_sub = assign_folds(sub, seed=args.seed)
        fold_of = {i: fold_sub[sub[i]] for i in ids}
        rep = audit(fold_of, edges, args.hub_cap)
        sz = Counter(sub.values())
        print("foldy (reklamy):", dict(Counter(fold_of.values())))
        print("foldy (podmioty):", dict(Counter(fold_sub.values())))
        print(f"podmiotów: {len(sz)}, solo: {sum(1 for n in sz.values() if n == 1)}, największy: {sz.most_common(1)[0][1]}")
        print(f"przecieki (wspólny ślad nie-hub między foldami): {len(rep['leaks'])}")
        print(f"huby pominięte przy łączeniu: {rep['n_hubs']}, z tego rozciągają się na >1 fold: {len(rep['hub_cross'])}")
        OUT.mkdir(parents=True, exist_ok=True)
        f = OUT / f"meta_hub{args.hub_cap}_seed{args.seed}.json"
        f.write_text(json.dumps({"hub_cap": args.hub_cap, "seed": args.seed, "fold": fold_of, "subject": sub,
                                 "audit": rep}, ensure_ascii=False))
        print("zapisano:", f)
        if args.write_graph:
            write_graph(s, fold_of, sub)
            print("zapisano Ad.fold i Ad.subject w grafie")
    drv.close()


if __name__ == "__main__":
    main()
