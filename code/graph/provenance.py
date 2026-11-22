"""Pochodzenie etykiety „scam”: skąd wiemy, ile dowodów i co z nimi nie gra.

Etykieta twórcy (Creator) i jego reklam wynika z TRZECH różnych rodzajów dowodu, które wcześniej zlewały się w jedno pole `meta_flag`:

  zdjęcie reklamy   Meta usunęła konkretną reklamę („removed because it didn't follow…”)        dowód na poziomie reklamy
  blokada konta     Meta wyłączyła stronę/konto („later disabled for not following…”)           dowód na poziomie strony
  ocena analityka   człowiek rozstrzygnął twórcę (`record_analyst_verdict`)                      wygrywa z automatem, ale zostawia ślad

Na twórcy zapisujemy: licznik (`label_num`), mianownik (`label_den` = liczba jego reklam), udział (`scam_share`), podstawę
(`label_basis`), datę (`label_at`) i regułę (`label_rule`); osobno liczby per rodzaj (`n_removed_ads`, `n_blocked_ads`) oraz węzły
`LabelEvidence` (po jednym na rodzaj dowodu, który występuje). Ocena analityka to węzeł `AnalystVerdict` (historia zostaje; `current`
wskazuje obowiązującą).

Reguła automatu (bez zmian względem wcześniejszej): udział zdjętych >= 50% -> `scam`; zdjęto część -> `podejrzany`; nic -> `brak sygnału`
(to NIE znaczy „uczciwy”). Ocena analityka zastępuje wynik automatu; wynik automatu zostaje w `auto_label`.

Konflikty do weryfikacji (`needs_review`, `review_reasons`):
  * analityk przeczy sygnałowi Mety („nie scam”, a Meta zdjęła reklamy);
  * jedna strona twórcy jest w większości zdjęta, a inna (>= 3 reklamy) nie ma ani jednej zdjętej: czy to na pewno jeden operator?;
  * dodanie materiału pasującego dokładnie do kilku twórców naraz (zapisuje `graf/decision.py`, krawędź `CONFLICTS_WITH`).

    .venv/bin/python graph/provenance.py refresh                      # przelicz etykiety wszystkich twórców
    .venv/bin/python graph/provenance.py verdict tw:123 "nie scam" --by ola --note "legalny wydawca"
    .venv/bin/python graph/provenance.py review                       # lista twórców do weryfikacji
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

F_REMOVED = "reklama usunięta przez Metę"            # musi być zgodne z FLAGS w load.py
F_BLOCKED = "konto/strona zablokowane przez Metę"
SCAM_SHARE = 0.5
RULE = "v2: udział zdjętych reklam >= 0,5 -> scam; część -> podejrzany; ocena analityka wygrywa"
VERDICTS = ("scam", "podejrzany", "nie scam")

# 1) liczniki, etykieta, podstawa. Liczone z krawędzi (a nie zwiększane), więc powtórzenie niczego nie zmienia.
COUNTS = """
MATCH (c:Creator) WHERE $ids IS NULL OR c.id IN $ids
WITH c,
     count { (c)<-[:CREATED_BY]-(:Ad) } AS den,
     count { (c)<-[:CREATED_BY]-(a:Ad) WHERE a.meta_flag = $removed } AS n_rem,
     count { (c)<-[:CREATED_BY]-(a:Ad) WHERE a.meta_flag = $blocked } AS n_blk
OPTIONAL MATCH (c)<-[:ABOUT_CREATOR]-(av:AnalystVerdict {current: true})
WITH c, den, n_rem, n_blk, av, n_rem + n_blk AS flagged
WITH c, den, n_rem, n_blk, av, flagged,
     CASE WHEN den = 0 THEN 0.0 ELSE toFloat(flagged) / den END AS share
WITH c, den, n_rem, n_blk, av, flagged, share,
     CASE WHEN share >= $share THEN 'scam' WHEN flagged > 0 THEN 'podejrzany' ELSE 'brak sygnału' END AS auto
SET c.n_ads = den, c.n_flagged = flagged, c.n_removed_ads = n_rem, c.n_blocked_ads = n_blk, c.scam_share = share,
    c.auto_label = auto,
    c.label = CASE WHEN av IS NOT NULL THEN av.verdict ELSE auto END,
    c.label_basis = CASE WHEN av IS NOT NULL THEN 'ocena analityka'
                         WHEN auto = 'brak sygnału' THEN 'brak sygnału'
                         WHEN n_blk > 0 AND n_rem > 0 THEN 'zdjęcie reklamy + blokada konta'
                         WHEN n_blk > 0 THEN 'blokada konta' ELSE 'zdjęcie reklamy' END,
    c.label_num = flagged, c.label_den = den, c.label_at = datetime(), c.label_rule = $rule,
    c.analyst_contradicts = av IS NOT NULL AND av.verdict = 'nie scam' AND auto IN ['scam', 'podejrzany']
RETURN count(c) AS n
"""

# 2) węzły dowodów: po jednym na rodzaj, który występuje; wygasłe (0) znikają
EVIDENCE = """
MATCH (c:Creator) WHERE $ids IS NULL OR c.id IN $ids
UNWIND [{k: 'zdjęcie reklamy', n: c.n_removed_ads}, {k: 'blokada konta', n: c.n_blocked_ads}] AS e
OPTIONAL MATCH (old:LabelEvidence {id: c.id + '|' + e.k}) WHERE e.n = 0
DETACH DELETE old
WITH c, e WHERE e.n > 0
MERGE (ev:LabelEvidence {id: c.id + '|' + e.k})
  SET ev.kind = e.k, ev.num = e.n, ev.den = c.n_ads, ev.share = toFloat(e.n) / c.n_ads, ev.at = datetime()
MERGE (c)-[:HAS_EVIDENCE]->(ev)
"""

# 3) konflikty: strona w większości zdjęta obok strony bez żadnej zdjętej reklamy
PAGES = """
MATCH (c:Creator) WHERE $ids IS NULL OR c.id IN $ids
OPTIONAL MATCH (c)<-[:CREATED_BY]-(a:Ad)-[:BY]->(adv:Advertiser)
WITH c, adv, count(a) AS n, sum(CASE WHEN a.meta_flag IS NOT NULL THEN 1 ELSE 0 END) AS f
WITH c, collect(CASE WHEN adv IS NULL THEN null ELSE {n: n, f: f} END) AS pages
WITH c, size([p IN pages WHERE p IS NOT NULL AND p.n >= 3 AND p.f = 0]) > 0
        AND size([p IN pages WHERE p IS NOT NULL AND toFloat(p.f) / p.n >= 0.5]) > 0 AS mixed
WITH c, mixed, EXISTS { (c)<-[:CONFLICTS_WITH]-(:Decision) } AS claimed
SET c.page_conflict = mixed,
    c.review_reasons = [r IN [
        CASE WHEN c.analyst_contradicts THEN 'ocena analityka przeczy sygnałowi Mety' END,
        CASE WHEN mixed THEN 'jedna strona w większości zdjęta, inna bez żadnej zdjętej reklamy' END,
        CASE WHEN claimed THEN 'dokładna zgodność z kilkoma twórcami naraz przy dodawaniu materiału' END] WHERE r IS NOT NULL]
SET c.needs_review = size(c.review_reasons) > 0
"""

# 4) propagacja na reklamy twórcy: własny dowód reklamy (Meta) wygrywa z propagowanym, każda z podstaw jest nazwana
ADS = """
MATCH (c:Creator) WHERE $ids IS NULL OR c.id IN $ids
MATCH (c)<-[:CREATED_BY]-(a:Ad)
SET a.label = CASE WHEN a.meta_flag IS NOT NULL THEN 'scam' ELSE c.label END,
    a.label_source = CASE WHEN a.meta_flag IS NOT NULL THEN 'meta'
                          WHEN c.label_basis = 'ocena analityka' THEN 'analityk'
                          WHEN c.label <> 'brak sygnału' THEN 'twórca' END,
    a.label_basis = CASE WHEN a.meta_flag = $removed THEN 'zdjęcie reklamy'
                         WHEN a.meta_flag = $blocked THEN 'blokada konta'
                         WHEN c.label <> 'brak sygnału' THEN c.label_basis END,
    a.label_from = CASE WHEN a.meta_flag IS NULL AND c.label <> 'brak sygnału' THEN c.id END
"""
MATERIALS = """
MATCH (c:Creator) WHERE $ids IS NULL OR c.id IN $ids
MATCH (c)<-[:CREATED_BY]-(m:Material)
SET m.label = c.label,
    m.label_source = CASE WHEN c.label_basis = 'ocena analityka' THEN 'analityk' WHEN c.label <> 'brak sygnału' THEN 'twórca' END,
    m.label_basis = CASE WHEN c.label <> 'brak sygnału' THEN c.label_basis END,
    m.label_from = CASE WHEN c.label <> 'brak sygnału' THEN c.id END
"""


def refresh(run, ids: list[str] | None = None) -> int:
    """Przelicza etykiety wskazanych twórców (None = wszystkich). `run` to `tx.run` albo `session.run`; zwraca liczbę twórców.

    Wszystko liczone z krawędzi, więc wielokrotne wywołanie daje ten sam stan (idempotentne)."""
    p = {"ids": ids, "removed": F_REMOVED, "blocked": F_BLOCKED, "share": SCAM_SHARE, "rule": RULE}
    n = run(COUNTS, **p).single()["n"]
    run(EVIDENCE, **p).consume()
    run(PAGES, **p).consume()
    run(ADS, **p).consume()
    run(MATERIALS, **p).consume()
    return n


def record_analyst_verdict(session, creator: str, verdict: str, analyst: str, note: str = "") -> str:
    """Ocena analityka dla twórcy. Poprzednia przestaje być obowiązująca, ale zostaje w grafie. Zwraca id oceny."""
    if verdict not in VERDICTS:
        raise ValueError(f"ocena musi być jedną z: {', '.join(VERDICTS)}")
    vid = hashlib.sha1(f"{creator}|{analyst}|{verdict}|{note}".encode()).hexdigest()[:16]

    def work(tx):
        if tx.run("MATCH (c:Creator {id: $c}) RETURN c", c=creator).single() is None:
            raise KeyError(f"nie ma twórcy {creator}")
        tx.run("MATCH (:Creator {id: $c})<-[:ABOUT_CREATOR]-(v:AnalystVerdict) SET v.current = false", c=creator).consume()
        tx.run("MATCH (c:Creator {id: $c}) MERGE (v:AnalystVerdict {id: $id}) "
               "SET v.verdict = $verdict, v.analyst = $analyst, v.note = $note, v.current = true, v.at = datetime() "
               "MERGE (v)-[:ABOUT_CREATOR]->(c)", c=creator, id=vid, verdict=verdict, analyst=analyst, note=note).consume()
        refresh(tx.run, [creator])

    session.execute_write(work)
    return vid


def review_list(session) -> list[dict]:
    return [dict(r) for r in session.run(
        "MATCH (c:Creator) WHERE c.needs_review RETURN c.id AS id, c.name AS name, c.label AS label, c.auto_label AS auto, "
        "c.label_num AS num, c.label_den AS den, c.review_reasons AS powody ORDER BY c.label_den DESC")]


def main() -> None:
    from load import driver

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["refresh", "verdict", "review"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--by", default="analityk")
    ap.add_argument("--note", default="")
    a = ap.parse_args()
    drv = driver()
    with drv.session() as s:
        if a.what == "refresh":
            print("przeliczono twórców:", s.execute_write(lambda tx: refresh(tx.run)))
        elif a.what == "verdict":
            if len(a.args) != 2:
                sys.exit("użycie: verdict <id twórcy> <scam|podejrzany|nie scam> [--by ...] [--note ...]")
            print("zapisano ocenę", record_analyst_verdict(s, a.args[0], a.args[1], a.by, a.note))
        else:
            for r in review_list(s):
                print(f"{r['id']:<24} {r['label']:<13} (auto: {r['auto']}, {r['num']}/{r['den']})  {'; '.join(r['powody'])}  [{r['name']}]")
    drv.close()


if __name__ == "__main__":
    main()
