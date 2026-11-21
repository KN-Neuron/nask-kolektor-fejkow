"""Ładowanie danych do Neo4j (schemat: graph/schema.cypher, opis: docs/13_BAZA_GRAFOWA.md).

    .venv/bin/python graph/load.py schema                 # ograniczenia i indeksy
    .venv/bin/python graph/load.py meta                   # wszystkie reklamy z data/meta/ads.jsonl (~97 tys.)
    .venv/bin/python graph/load.py meta --payer "alex alex" --limit 80   # tylko próbka
    .venv/bin/python graph/load.py meta --file ../data/meta/sample_s1.jsonl  # próbka S1 z graph/sample.py
    .venv/bin/python graph/load.py export                 # teksty z grafu dla embsim (ad_texts.jsonl, ad_meta.jsonl)
    .venv/bin/python graph/load.py nask                   # przypadki z indeksu `fejki demo build` + podobieństwa i kampanie
    .venv/bin/python graph/load.py synth                  # syntetyka z prawdą (generuje data/synth, jeśli nie ma)
    .venv/bin/python graph/load.py all                    # schema + meta + nask

Połączenie: NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD z code/.env (albo ze zmiennych środowiska; środowisko ma pierwszeństwo).
Najpierw meta, potem nask: przypadki dopinają się do już istniejących reklam, reklamodawców i domen z Mety.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
ADS = ROOT.parent / "data" / "meta" / "ads.jsonl"
SCHEMA = ROOT / "graph" / "schema.cypher"
BATCH = 2000

# --------------------------------------------------------------------------------------------------------------------
# wspólne


def driver():
    load_dotenv(ROOT / ".env", override=False)
    return GraphDatabase.driver(os.getenv("NEO4J_URI", "bolt://localhost:7687"),
                                auth=(os.getenv("NEO4J_USER", "neo4j"), os.environ["NEO4J_PASSWORD"]))


def run_batches(session, cypher: str, rows: list[dict], label: str) -> None:
    t = time.time()
    for i in range(0, len(rows), BATCH):
        session.run(cypher, rows=rows[i:i + BATCH]).consume()
        print(f"\r  {label}: {min(i + BATCH, len(rows))}/{len(rows)}", end="", flush=True)
    print(f"  ({time.time() - t:.0f} s)")


def norm_name(s: str) -> str:
    """Do porównywania nazw reklamodawców: bez wielkości liter, akcentów i nadmiarowych spacji."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode() or (s or "")
    return re.sub(r"\s+", " ", s).strip().casefold()


def reg_domain(host: str) -> str:
    from fejki.infra.collect import registered_domain

    return registered_domain(host.lower().strip(". ")) or host.lower()


def schema(session) -> None:
    text = re.sub(r"//[^\n]*", "", SCHEMA.read_text(encoding="utf-8"))
    for stmt in (s.strip() for s in text.split(";")):
        if stmt:
            session.run(stmt).consume()
    session.run("CREATE INDEX advertiser_norm IF NOT EXISTS FOR (n:Advertiser) ON (n.name_norm)").consume()
    print("schemat: ok")


# --------------------------------------------------------------------------------------------------------------------
# Meta Ad Library

FLAGS = {"removed because it didn": "reklama usunięta przez Metę",
         "later disabled for not following": "konto/strona zablokowane przez Metę"}
HOST = re.compile(r"^(?:[a-z0-9-]+\.)+[a-z]{2,}$")


def as_list(v) -> list:
    """Plik ma dwa formaty: prawdziwe listy JSON albo listy zapisane jako tekst Pythona ("['a', 'b']")."""
    if isinstance(v, list):
        return v
    if isinstance(v, str) and v[:1] in "[{":
        try:
            return ast.literal_eval(v)
        except (ValueError, SyntaxError):
            return [v]
    return [v] if v else []


def mixed_script(name: str) -> bool:
    """Nazwa miesza alfabety (np. łacinka + cyrylica udająca łacinkę: „GоІdеn Gеm”) = typowe obchodzenie filtrów."""
    scripts = {unicodedata.name(c, "").split(" ")[0] for c in name if c.isalpha()}
    return len(scripts & {"LATIN", "CYRILLIC", "GREEK"}) > 1


def meta_record(r: dict, persons) -> dict:
    from fejki.demo.material import find_persons

    bodies = [str(x) for x in as_list(r.get("ad_creative_bodies"))]
    captions = [str(x) for x in as_list(r.get("ad_creative_link_captions"))]
    titles = [str(x) for x in as_list(r.get("ad_creative_link_titles"))]
    flag = next((v for k, v in FLAGS.items() if k in " ".join(bodies + captions)), None)
    payers = sorted({p["payer"] for p in as_list(r.get("beneficiary_payers")) if isinstance(p, dict) and p.get("payer")})
    domains = sorted({reg_domain(c) for c in captions if HOST.match(c.lower().strip())})
    title = "" if flag else next((t for t in titles if t), "")
    body = "" if flag else (bodies[0] if bodies else "")
    q = r.get("_query", "")
    reach = str(r.get("eu_total_reach", ""))
    return {
        "id": r["id"], "name": (title[:60] or f"Reklama …{r['id'][-6:]}"), "title": title, "body": body[:1000],
        "created": r.get("ad_creation_time"), "start": r.get("ad_delivery_start_time"), "stop": r.get("ad_delivery_stop_time"),
        "reach": int(reach) if reach.isdigit() else None,
        "platforms": [str(x) for x in as_list(r.get("publisher_platforms"))],
        "library_url": f"https://www.facebook.com/ads/library/?id={r['id']}",  # publiczny link, bez tokenu
        "flag": flag, "query": q,
        # odcisk tekstu (jak w embsim.eda): ta sama reklama w wielu kopiach = jeden węzeł Text i jeden wektor
        "text_hash": hashlib.sha1(body.encode()).hexdigest()[:12] if body.strip() else None,
        "page_id": r["page_id"], "page_name": r.get("page_name") or r["page_id"], "mixed": mixed_script(r.get("page_name") or ""),
        "payers": payers, "domains": domains, "topic": q[3:] if q.startswith("kw:") else None,
        "persons": [{"name": k, "count": v} for k, v in find_persons(f"{title} {body}", persons).items()] if body or title else [],
    }


META_CYPHER = """
UNWIND $rows AS r
MERGE (a:Ad {id: r.id})
  SET a.source = 'meta_ad_library', a.name = r.name, a.title = r.title, a.body = r.body,
      a.created = date(r.created), a.delivery_start = date(r.start),
      a.delivery_stop = CASE WHEN r.stop IS NULL THEN null ELSE date(r.stop) END,
      a.eu_reach = r.reach, a.platforms = r.platforms, a.library_url = r.library_url, a.meta_flag = r.flag, a.found_by = r.query,
      a.text_hash = r.text_hash
MERGE (adv:Advertiser {key: 'fb:' + r.page_id})
  SET adv.name = r.page_name, adv.name_norm = r.page_norm, adv.page_id = r.page_id, adv.mixed_script = r.mixed
MERGE (a)-[:BY]->(adv)
FOREACH (p IN r.payers | MERGE (py:Payer {name: p}) MERGE (a)-[:PAID_BY]->(py))
FOREACH (d IN r.domains | MERGE (dm:Domain {name: d}) SET dm.name = d MERGE (a)-[:LINKS_TO]->(dm))
FOREACH (t IN CASE WHEN r.topic IS NULL THEN [] ELSE [r.topic] END | MERGE (tp:Topic {name: t}) MERGE (a)-[:ABOUT]->(tp))
FOREACH (p IN r.persons | MERGE (pe:Person {name: p.name}) MERGE (a)-[m:MENTIONS]->(pe) SET m.count = p.count)
"""


def load_meta(session, payers: set[str] | None, limit: int | None, path: Path = ADS) -> None:
    from fejki.demo.material import load_persons

    persons = load_persons()
    rows, per = [], {}
    for line in path.open(encoding="utf-8"):
        r = json.loads(line)
        if payers:
            ps = {p.get("payer") for p in as_list(r.get("beneficiary_payers")) if isinstance(p, dict)} & payers
            if not ps or (limit and all(per.get(p, 0) >= limit for p in ps)):
                continue
            for p in ps:
                per[p] = per.get(p, 0) + 1
        rec = meta_record(r, persons)
        rec["page_norm"] = norm_name(rec["page_name"])
        rows.append(rec)
    print(f"Meta: {len(rows)} reklam do załadowania")
    run_batches(session, META_CYPHER, rows, "reklamy Meta")


# --------------------------------------------------------------------------------------------------------------------
# przypadki NASK (z indeksu `fejki demo build`) + wynik porównania


def sha256(path: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


KIND = {".har": "har", ".html": "html", ".htm": "html", ".mhtml": "mhtml", ".mp4": "wideo", ".mov": "wideo",
        ".png": "obraz", ".jpg": "obraz", ".jpeg": "obraz", ".webp": "obraz", ".json": "metadane"}


def tracker(t: str) -> dict:
    low = t.lower()
    kind = "google_ads" if low.startswith("aw-") else "gtm" if low.startswith("gtm-") else "google_analytics" if low.startswith(("g-", "ua-")) else "inny"
    return {"id": t, "kind": kind}


def case_record(m, base: Path) -> dict:
    files = []
    for f in m.files:
        p = (base / m.base_dir / f) if m.base_dir else None
        if p and p.is_file():
            files.append({"sha": sha256(p), "name": f, "kind": KIND.get(p.suffix.lower(), "inny"), "size": p.stat().st_size})
    dates = sorted(o["date"] for o in m.observed if o.get("date"))
    redirects = []
    for r in m.redirects:  # "a.host → b.host (302)"
        mm = re.match(r"(\S+)\s*→\s*(\S+)", r)
        if mm:
            redirects.append({"src": reg_domain(mm.group(1)), "dst": reg_domain(mm.group(2))})
    return {
        "id": m.id, "name": m.label, "source": m.source, "title": (m.titles or [""])[0], "titles": m.titles,
        "text": m.text[:20000], "ocr_text": m.ocr_text[:20000], "keywords": m.keywords, "missing": m.missing,
        "cloaking": m.cloaking, "pages": m.pages, "notes": m.notes,
        "observed_at": dates[0][:19] if dates else None, "observed_last": dates[-1][:19] if dates else None,
        "files": [f for f in files if f["sha"]],
        "persons": [{"name": k, "count": v} for k, v in (m.person_counts or {p: 1 for p in m.persons}).items()],
        "products": m.products, "brands": m.logos, "contacts": m.contacts,
        "topics": [{"name": k, "w": v} for k, v in m.topics.items()],
        "ads": m.ad_ids, "accounts": m.ad_accounts,
        "advertisers": [{"name": a, "norm": norm_name(a)} for a in m.advertisers],
        "trackers": [{"id": f"meta:{p}", "kind": "meta_pixel"} for p in m.pixel_ids] + [tracker(t) for t in m.tracker_ids],
        "landing": m.landing_domains, "calls": sorted({reg_domain(h) for h in m.third_party_hosts} - set(m.landing_domains)),
        "redirects": redirects, "kits": m.path_prefixes, "schemes": m.url_schemes,
        "images": [{"phash": i.phash, "file": i.file, "role": i.role} for i in m.images],
    }


CASE_CYPHER = """
UNWIND $rows AS r
MERGE (m:Material {id: r.id})
  SET m.name = r.name, m.source = r.source, m.title = r.title, m.titles = r.titles, m.text = r.text, m.ocr_text = r.ocr_text,
      m.keywords = r.keywords, m.missing = r.missing, m.cloaking = r.cloaking, m.pages = r.pages, m.notes = r.notes,
      m.observed_at = CASE WHEN r.observed_at IS NULL THEN null ELSE localdatetime(r.observed_at) END,
      m.observed_last = CASE WHEN r.observed_last IS NULL THEN null ELSE localdatetime(r.observed_last) END,
      m.dataset = r.dataset, m.truth_campaign = r.truth_campaign, m.truth_operator = r.truth_operator,
      m.truth_kind = r.truth_kind
FOREACH (f IN r.files | MERGE (a:Artifact {sha256: f.sha}) SET a.name = f.name, a.kind = f.kind, a.size = f.size
                        MERGE (m)-[:HAS_ARTIFACT]->(a))
FOREACH (i IN r.images | MERGE (h:ImageHash {phash: i.phash}) SET h.name = i.phash MERGE (m)-[x:HAS_IMAGE]->(h) SET x.file = i.file, x.role = i.role)
FOREACH (p IN r.persons | MERGE (pe:Person {name: p.name}) MERGE (m)-[x:MENTIONS]->(pe) SET x.count = p.count)
FOREACH (p IN r.products | MERGE (pr:Product {name: p}) MERGE (m)-[:PROMOTES]->(pr))
FOREACH (b IN r.brands | MERGE (br:Brand {name: b}) MERGE (m)-[:IMPERSONATES]->(br))
FOREACH (c IN r.contacts | MERGE (co:Contact {value: c}) SET co.name = c MERGE (m)-[:HAS_CONTACT]->(co))
FOREACH (t IN r.topics | MERGE (tp:Topic {name: t.name}) MERGE (m)-[x:ABOUT]->(tp) SET x.weight = t.w)
FOREACH (a IN r.ads | MERGE (ad:Ad {id: a}) ON CREATE SET ad.name = 'Reklama …' + right(a, 6), ad.source = 'z materiału'
                      MERGE (m)-[:SHOWS_AD]->(ad))
FOREACH (a IN r.accounts | MERGE (ac:AdAccount {id: a}) SET ac.name = a MERGE (m)-[:BOUGHT_BY]->(ac))
FOREACH (t IN r.trackers | MERGE (tr:Tracker {id: t.id}) SET tr.kind = t.kind, tr.name = t.id MERGE (m)-[:USES_TRACKER]->(tr))
FOREACH (d IN r.landing | MERGE (dm:Domain {name: d}) MERGE (m)-[:LANDS_ON]->(dm))
FOREACH (d IN r.calls | MERGE (dm:Domain {name: d}) MERGE (m)-[:CALLS]->(dm))
FOREACH (x IN r.redirects | MERGE (s:Domain {name: x.src}) MERGE (t:Domain {name: x.dst}) MERGE (s)-[:REDIRECTS_TO]->(t)
                           MERGE (m)-[:REDIRECTS_THROUGH]->(t))
FOREACH (k IN r.kits | MERGE (pk:PageKit {prefix: k}) SET pk.name = k MERGE (m)-[:USES_KIT]->(pk))
FOREACH (s IN r.schemes | MERGE (us:UrlScheme {fingerprint: s}) SET us.name = s MERGE (m)-[:USES_URL_SCHEME]->(us))
WITH m, r
UNWIND (CASE WHEN size(r.advertisers) = 0 THEN [null] ELSE r.advertisers END) AS adv
WITH m, r, adv WHERE adv IS NOT NULL
OPTIONAL MATCH (known:Advertiser {name_norm: adv.norm}) WHERE r.dataset = 'nask'
WITH m, adv, r, collect(known) AS ks
FOREACH (k IN ks | MERGE (m)-[:ADVERTISED_BY]->(k))
FOREACH (_ IN CASE WHEN size(ks) = 0 THEN [1] ELSE [] END |
  MERGE (n:Advertiser {key: CASE r.dataset WHEN 'nask' THEN '' ELSE r.dataset + ':' END + 'name:' + adv.norm})
    SET n.name = adv.name, n.name_norm = adv.norm
  MERGE (m)-[:ADVERTISED_BY]->(n))
"""

INFRA_CYPHER = """
UNWIND $rows AS r
MERGE (d:Domain {name: r.domain})
  SET d.registered = CASE WHEN r.created IS NULL THEN null ELSE datetime(r.created) END, d.infra_collected = r.collected_at
FOREACH (g IN CASE WHEN r.registrar IS NULL THEN [] ELSE [r.registrar] END |
  MERGE (rg:Registrar {name: g}) MERGE (d)-[:REGISTERED_AT]->(rg))
FOREACH (ip IN r.ips | MERGE (i:IP {addr: ip.addr}) SET i.name = ip.addr MERGE (d)-[:RESOLVES_TO]->(i)
  FOREACH (n IN CASE WHEN ip.asn IS NULL THEN [] ELSE [ip.asn] END |
    MERGE (a:ASN {number: n}) SET a.name = 'AS' + n + coalesce(' ' + ip.org, ''), a.org = ip.org, a.country = ip.country
    MERGE (i)-[:ANNOUNCED_BY]->(a)))
FOREACH (c IN r.certs | MERGE (ce:Certificate {serial: c.serial})
  SET ce.issuer = c.issuer, ce.not_before = c.not_before, ce.name = coalesce(c.issuer, c.serial) MERGE (d)-[:HAS_CERT]->(ce))
"""

SIM_CYPHER = """
UNWIND $rows AS r
MATCH (a:Material {id: r.a}), (b:Material {id: r.b})
MERGE (a)-[s:SIMILAR]->(b)
  SET s.score = r.score, s.relation = r.relation, s.text_sim = r.text_sim, s.channels = r.channels, s.reasons = r.reasons
"""

GROUP_CYPHER = """
UNWIND $rows AS r
MERGE (c:Campaign {id: r.id}) SET c.name = r.id + ': ' + r.name, c.strength = r.strength, c.persons = r.persons, c.domains = r.domains,
  c.dataset = r.dataset
WITH c, r
UNWIND r.members AS mid
MATCH (m:Material {id: mid}) MERGE (m)-[:IN_CAMPAIGN]->(c)
"""

NET_CYPHER = """
UNWIND $rows AS r
MERGE (n:Network {id: r.id}) SET n.name = 'Sieć ' + r.id, n.strength = r.strength, n.dataset = r.dataset
WITH n, r
UNWIND r.members AS mid
MATCH (m:Material {id: mid})-[:IN_CAMPAIGN]->(c:Campaign) MERGE (c)-[:IN_NETWORK]->(n)
"""


SYNTH_DIR = ROOT.parent / "data" / "synth"
SYNTH_INDEX = ROOT / "artifacts" / "demo" / "index_synth.json"


def load_nask(session, min_score: float) -> None:
    from fejki.demo import store

    idx = store.load()
    if not idx:
        sys.exit("brak indeksu: najpierw `fejki demo build` (z katalogu code/)")
    load_cases(session, idx, "nask", min_score)


def load_synth(session, min_score: float) -> None:
    """Syntetyka (`fejki demo synth`) jako osobny zbiór: Material.dataset='synth' + prawda (truth_*), kampanie z prefiksem `synth:`.
    Domeny .example/.test i reklamodawcy z kluczem `synth:` nie sklejają się z prawdziwymi danymi; wspólne są tylko osoby (z tekstu)."""
    from fejki.demo import store
    from fejki.demo.synth_cases import generate

    if not (SYNTH_DIR / "prawda.json").exists():
        generate(SYNTH_DIR, 6, 2, 3, 1)
    idx = store.load(SYNTH_INDEX)
    if not idx or idx.data_dir != str(SYNTH_DIR):
        idx = store.build(SYNTH_DIR, ocr=False)
        store.save(idx, SYNTH_INDEX)
    truth = json.loads((SYNTH_DIR / "prawda.json").read_text(encoding="utf-8"))
    load_cases(session, idx, "synth", min_score, truth)


def load_cases(session, idx, dataset: str, min_score: float, truth: dict | None = None) -> None:
    from fejki.demo import store
    from fejki.demo.similar import all_pairs, campaigns

    pre = "" if dataset == "nask" else f"{dataset}:"
    rows = []
    for m in idx.materials:
        r = case_record(m, ROOT)
        t = (truth or {}).get(m.id, {})
        rows.append({**r, "dataset": dataset, "truth_campaign": t.get("kampania"), "truth_operator": t.get("operator"),
                     "truth_kind": t.get("rodzaj")})
    print(f"{dataset}: {len(rows)} przypadków (zbudowano {idx.built_at})")
    run_batches(session, CASE_CYPHER, rows, "przypadki")

    infra, canon = [], {}
    for d, rec in idx.infra.items():
        rd = dict(rec.get("rdap") or {})
        if rd.get("registrar"):  # „NameCheap, Inc.” i „Namecheap Inc.” to ten sam rejestrator
            key = re.sub(r"\b(inc|llc|ltd|limited|co)\b|[^a-z0-9]", "", rd["registrar"].lower())
            rd["registrar"] = canon.setdefault(key, rd["registrar"])
        ips = [{"addr": ip, **{k: (rec.get("asn", {}).get(ip) or {}).get(k) for k in ("asn", "org", "country")}} for ip in rec.get("a", [])]
        certs = [c for c in rec.get("certs", []) if c.get("serial")][:10]
        infra.append({"domain": d, "created": rd.get("created"), "registrar": rd.get("registrar"), "ips": ips, "certs": certs,
                      "collected_at": rec.get("collected_at")})
    if infra:
        run_batches(session, INFRA_CYPHER, infra, "infrastruktura domen")

    recs = store.infra_records(idx) if idx.infra else None
    pairs = all_pairs(idx.materials, recs)
    sims = [{"a": p.a, "b": p.b, "score": round(p.score, 3), "relation": p.relation, "text_sim": round(p.text_sim, 3),
             "channels": sorted({e.channel for e in p.evidence}), "reasons": [e.reason for e in p.evidence[:8]]}
            for p in pairs if p.score >= min_score]
    session.run("MATCH (:Material {dataset: $d})-[s:SIMILAR]->(:Material {dataset: $d}) DELETE s", d=dataset).consume()
    run_batches(session, SIM_CYPHER, sims, "podobieństwa (SIMILAR)")

    session.run("MATCH (m:Material {dataset: $d})-[r:IN_CAMPAIGN]->() DELETE r", d=dataset).consume()
    session.run("MATCH (c:Campaign) WHERE NOT (c)<-[:IN_CAMPAIGN]-() DETACH DELETE c").consume()
    session.run("MATCH (n:Network) WHERE coalesce(n.dataset, 'nask') = $d DETACH DELETE n", d=dataset).consume()
    camps = campaigns(idx.materials, pairs, 0.7, "kampania")
    nets = [n for n in campaigns(idx.materials, pairs, 0.7, "sieć") if len(n.members) > 1]
    dump = lambda cs: [{"id": pre + c.id, "name": c.name, "members": c.members, "strength": c.strength, "persons": c.persons,
                        "domains": c.domains, "dataset": dataset} for c in cs]
    run_batches(session, GROUP_CYPHER, dump(camps), "kampanie")
    run_batches(session, NET_CYPHER, dump(nets), "sieci")


# --------------------------------------------------------------------------------------------------------------------


def export_texts(session, out: Path) -> None:
    """Teksty reklam z grafu dla embsim: ad_texts.jsonl (h, text) do `python -m embsim.batch` i ad_meta.jsonl (id, h, fold,
    subject) do `python -m embsim.meta_eval`. Fold i subject są puste, dopóki nie uruchomisz `graph/subjects.py split --write-graph`."""
    out.mkdir(parents=True, exist_ok=True)
    texts, n = {}, 0
    with (out / "ad_meta.jsonl").open("w", encoding="utf-8") as f:
        for r in session.run("MATCH (a:Ad) RETURN a.id AS id, a.text_hash AS h, a.body AS body, a.fold AS fold, "
                             "a.subject AS subject"):
            f.write(json.dumps({"id": r["id"], "h": r["h"], "fold": r["fold"], "subject": r["subject"]}) + "\n")
            if r["h"]:
                texts.setdefault(r["h"], r["body"])
            n += 1
    with (out / "ad_texts.jsonl").open("w", encoding="utf-8") as f:
        for h, t in texts.items():
            f.write(json.dumps({"h": h, "text": t}, ensure_ascii=False) + "\n")
    print(f"eksport: {n} reklam, {len(texts)} unikalnych tekstów -> {out}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["schema", "meta", "nask", "synth", "all", "export"])
    ap.add_argument("--payer", action="append", help="meta: tylko reklamy tych płatników (próbka)")
    ap.add_argument("--limit", type=int, help="meta: maks. reklam na płatnika")
    ap.add_argument("--file", type=Path, default=ADS, help="meta: inny plik JSONL, np. próbka z graph/sample.py")
    ap.add_argument("--out", type=Path, default=ROOT / "artifacts" / "meta", help="export: katalog na ad_texts/ad_meta")
    ap.add_argument("--min-score", type=float, default=0.4, help="nask: zapisuj SIMILAR od tego wyniku")
    args = ap.parse_args()
    drv = driver()
    with drv.session() as s:
        if args.what in ("schema", "all"):
            schema(s)
        if args.what in ("meta", "all"):
            load_meta(s, set(args.payer) if args.payer else None, args.limit, args.file)
        if args.what in ("nask", "all"):
            load_nask(s, args.min_score)
        if args.what == "synth":
            load_synth(s, args.min_score)
        if args.what == "export":
            export_texts(s, args.out)
        print("w bazie:", {r["l"]: r["n"] for r in s.run("MATCH (n) RETURN labels(n)[0] AS l, count(*) AS n ORDER BY n DESC")})
    drv.close()


if __name__ == "__main__":
    main()
