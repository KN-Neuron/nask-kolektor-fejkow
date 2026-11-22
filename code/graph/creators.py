"""Twórca (Creator) jako węzeł główny: jeden operator stojący za reklamami, nawet gdy używa wielu stron i płatników.

    .venv/bin/python graph/creators.py build [--hub-cap 100]     # policz twórców i zapisz w grafie (idempotentne)
    .venv/bin/python graph/creators.py diff "<twórca A>" "<twórca B>" # co odróżnia A od B (id albo nazwa strony)

Twórca = podmiot z graph/subjects.py: reklamy połączone tą samą stroną (Advertiser), płatnikiem (Payer), domeną albo identycznym
tekstem. Węzły-huby (stopień > hub_cap, np. płatnik „Advertiser”, youtube.com) NIE sklejają twórców; strona zawsze skleja\n(w odróżnieniu od podziału na foldy w subjects.py, gdzie duża strona też bywa hubem).

W grafie:
  (:Ad)-[:CREATED_BY]->(:Creator)
  (:Advertiser|Payer|Domain)-[:PART_OF]->(:Creator)       tylko ślady nie-huby, więc każdy należy do dokładnie jednego twórcy
  (:Material)-[:CREATED_BY]->(:Creator)                   przypadek NASK/syntetyka, jeśli wskazuje stronę z Mety (ADVERTISED_BY)

Etykieta (propagacja z twórcy na jego reklamy):
  scam          Meta zdjęła co najmniej SCAM_SHARE (50%) jego reklam; pozostałe reklamy dostają label='scam', label_source='twórca';
  podejrzany    zdjęła część, ale mniej niż połowę (np. 1 z 3000 u dużego wydawcy seriali): reklamy 'podejrzany', do sprawdzenia;
  brak sygnału  nic nie zdjęto. To NIE znaczy 'uczciwy': niezdjęta reklama to tylko brak dowodu.
Reklamy zdjęte przez Metę zawsze mają label='scam', label_source='meta'.
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import provenance
from load import driver
from subjects import components, fetch, hubs

CREATOR_CYPHER = """
UNWIND $rows AS r
MERGE (c:Creator {id: r.id})
  SET c.name = r.name, c.n_pages = r.n_pages, c.n_payers = r.n_payers, c.hub_cap = r.hub_cap, c.stale = false
"""
# liczniki i etykiety liczy provenance.refresh (z krawędzi, z podstawą i datą), nie ta paczka
AD_CYPHER = """
UNWIND $rows AS r
MATCH (a:Ad {id: r.ad}), (c:Creator {id: r.c})
OPTIONAL MATCH (a)-[old:CREATED_BY]->(o:Creator) WHERE o.id <> r.c
DELETE old
WITH DISTINCT a, c
MERGE (a)-[:CREATED_BY]->(c)
"""
TRACE_CYPHER = {
    "BY": "UNWIND $rows AS r MATCH (x:Advertiser {key: r.k}), (c:Creator {id: r.c}) "
          "OPTIONAL MATCH (x)-[old:PART_OF]->(o:Creator) WHERE o.id <> r.c DELETE old WITH DISTINCT x, c MERGE (x)-[:PART_OF]->(c)",
    "PAID_BY": "UNWIND $rows AS r MATCH (x:Payer {name: r.k}), (c:Creator {id: r.c}) "
               "OPTIONAL MATCH (x)-[old:PART_OF]->(o:Creator) WHERE o.id <> r.c DELETE old WITH DISTINCT x, c MERGE (x)-[:PART_OF]->(c)",
    "LINKS_TO": "UNWIND $rows AS r MATCH (x:Domain {name: r.k}), (c:Creator {id: r.c}) "
                "OPTIONAL MATCH (x)-[old:PART_OF]->(o:Creator) WHERE o.id <> r.c DELETE old WITH DISTINCT x, c MERGE (x)-[:PART_OF]->(c)",
}
MATERIAL_CYPHER = """
MATCH (m:Material)-[:ADVERTISED_BY]->(:Advertiser)-[:PART_OF]->(c:Creator)
MERGE (m)-[:CREATED_BY]->(c)
RETURN count(DISTINCT m) AS n
"""


SCAM_SHARE = provenance.SCAM_SHARE
BATCH = 2000

# po przebudowie zostają tylko twórcy, którzy nadal mają członków, kampanie albo decyzje (historia scrapera); resztę kasujemy
PRUNE = """
MATCH (c:Creator) WHERE NOT c.id IN $ids
WITH c, NOT EXISTS { (c)<-[:CREATED_BY]-() } AS empty,
     EXISTS { (c)<-[:RUN_BY]-(:Campaign) } OR EXISTS { (c)<-[:OPERATOR]-(:Decision) } AS has_history
FOREACH (_ IN CASE WHEN empty AND NOT has_history THEN [1] ELSE [] END | DETACH DELETE c)
FOREACH (_ IN CASE WHEN has_history THEN [1] ELSE [] END | SET c.stale = true)
RETURN count(c) AS seen
"""


def build(session, hub_cap: int) -> None:
    ids, edges = fetch(session)
    # strona (BY) zawsze łączy: duża strona to jeden twórca, a nie hub; limit hubów dotyczy płatników, domen i tekstów
    skip = {n for n in hubs(edges, hub_cap) if not n.startswith("BY:")}
    sub = components(ids, [e for e in edges if e[1] not in skip], None)
    info = {r["id"]: r for r in session.run(
        "MATCH (a:Ad)-[:BY]->(v:Advertiser) RETURN a.id AS id, a.meta_flag IS NOT NULL AS flagged, v.name AS page")}
    members: dict[int, list[str]] = defaultdict(list)
    for a, c in sub.items():
        members[c].append(a)
    traces: dict[int, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for a, n in edges:
        if n not in skip:
            kind, key = n.split(":", 1)
            traces[sub[a]][kind].add(key)
    cid = lambda c: f"tw:{min(members[c])}"  # stabilne id: najmniejsze id reklamy (nie zależy od kolejności liczenia)
    rows = []
    for c, ads in members.items():
        pages = Counter(info[a]["page"] for a in ads if a in info)
        name = pages.most_common(1)[0][0] if pages else cid(c)
        if len(pages) > 1:
            name += f" (+{len(pages) - 1} stron)"
        rows.append({"id": cid(c), "name": name, "n_ads": len(ads), "n_flagged": sum(info[a]["flagged"] for a in ads if a in info),
                     "n_pages": len(traces[c]["BY"]), "n_payers": len(traces[c]["PAID_BY"]), "hub_cap": hub_cap})
    ad_rows = [{"ad": a, "c": cid(c)} for a, c in sub.items()]
    trace_rows = {kind: [{"k": k, "c": cid(c)} for c, t in traces.items() for k in t[kind]] for kind in TRACE_CYPHER}
    ids = [r["id"] for r in rows]

    def publish(tx):
        """Cała przebudowa w JEDNEJ transakcji: czytelnicy widzą stary stan albo nowy, nigdy połowę. Nic nie jest kasowane przed zapisem."""
        def batches(cypher, data):
            for i in range(0, len(data), BATCH):
                tx.run(cypher, rows=data[i:i + BATCH]).consume()
        batches(CREATOR_CYPHER, rows)
        batches(AD_CYPHER, ad_rows)
        for kind, q in TRACE_CYPHER.items():
            batches(q, trace_rows[kind])
        n = tx.run(MATERIAL_CYPHER).single()["n"]
        tx.run(PRUNE, ids=ids).consume()
        provenance.refresh(tx.run, None)
        tx.run("MERGE (m:GraphMeta {key: 'creators'}) SET m.built_at = datetime(), m.n_creators = $n, m.hub_cap = $h, m.status = 'ready'",
               n=len(rows), h=hub_cap).consume()
        return n

    t0 = time.time()
    n_mat = session.execute_write(publish)
    print(f"zapisano w jednej transakcji ({time.time() - t0:.0f} s)")
    sz = Counter(r["n_ads"] for r in rows)
    print(f"twórców: {len(rows)}, scam: {sum(r['n_flagged'] >= SCAM_SHARE * r['n_ads'] for r in rows)}, "
          f"podejrzanych: {sum(0 < r['n_flagged'] < SCAM_SHARE * r['n_ads'] for r in rows)}, jednoreklamowych: {sz[1]}, "
          f"największy: {max(r['n_ads'] for r in rows)} reklam, huby pominięte: {len(skip)}, przypadki NASK/syntetyka: {n_mat}")


DIFF = """
MATCH (c:Creator) WHERE c.id = $x OR c.name = $x OR EXISTS { (c)<-[:PART_OF]-(:Advertiser {name: $x}) }
WITH c LIMIT 1
MATCH (c)<-[:CREATED_BY]-(a:Ad)
OPTIONAL MATCH (a)-[:PAID_BY]->(py:Payer)
OPTIONAL MATCH (a)-[:LINKS_TO]->(d:Domain)
OPTIONAL MATCH (a)-[:ABOUT]->(t:Topic)
OPTIONAL MATCH (a)-[:MENTIONS]->(pe:Person)
OPTIONAL MATCH (a)-[:BY]->(v:Advertiser)
RETURN c.id AS id, c.name AS name, c.label AS label, c.n_ads AS n_ads, c.n_flagged AS n_flagged,
       collect(DISTINCT v.name) AS strony, collect(DISTINCT py.name) AS płatnicy, collect(DISTINCT d.name) AS domeny,
       collect(DISTINCT t.name) AS tematy, collect(DISTINCT pe.name) AS osoby,
       min(a.delivery_start) AS od, max(coalesce(a.delivery_stop, a.delivery_start)) AS do,
       count(DISTINCT a.text_hash) AS teksty
"""


def diff(session, x: str, y: str) -> None:
    a, b = (session.run(DIFF, x=v).single() for v in (x, y))
    for v, r in ((x, a), (y, b)):
        if r is None:
            sys.exit(f"nie znaleziono twórcy: {v}")
    print(f"A = {a['name']} [{a['id']}]: {a['label']}, {a['n_ads']} reklam, {a['n_flagged']} zdjętych, {a['teksty']} tekstów, "
          f"{a['od']}..{a['do']}")
    print(f"B = {b['name']} [{b['id']}]: {b['label']}, {b['n_ads']} reklam, {b['n_flagged']} zdjętych, {b['teksty']} tekstów, "
          f"{b['od']}..{b['do']}")
    for k in ("strony", "płatnicy", "domeny", "tematy", "osoby"):
        sa, sb = set(a[k]), set(b[k])
        print(f"\n{k}: wspólne {sorted(sa & sb)[:10]}\n  tylko A {sorted(sa - sb)[:10]}\n  tylko B {sorted(sb - sa)[:10]}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["build", "diff"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--hub-cap", type=int, default=100)
    a = ap.parse_args()
    drv = driver()
    with drv.session() as s:
        if a.what == "build":
            s.run("CREATE CONSTRAINT creator_id IF NOT EXISTS FOR (n:Creator) REQUIRE n.id IS UNIQUE").consume()
            build(s, a.hub_cap)
        else:
            diff(s, *a.args[:2])
    drv.close()


if __name__ == "__main__":
    main()
