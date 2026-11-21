"""Dodawanie przyrostowe (task 2) i scraper Mety (task 3): silnik embsim decyduje, graf zapamiętuje wynik.

    .venv/bin/python graph/scrape.py seed                              # galeria startowa z próbki S1 (raz, ~2 min)
    .venv/bin/python graph/scrape.py add ../data/meta/nowe.jsonl       # reklamy Meta z pliku JSONL
    .venv/bin/python graph/scrape.py add ../data/dane/do_udostępnienia/2   # folder przypadku (zrzut, HTML, HAR...)
    .venv/bin/python graph/scrape.py add --text "Brzoska ujawnia sekret..."  [--url https://adres.example/x]
    .venv/bin/python graph/scrape.py watch ../data/meta/ads_nowe.jsonl --every-min 60    # scraper: co godzinę nowe linie

Jak to działa dla jednego materiału:
1. embsim (`embsim.api.Gallery`, zamrożona konfiguracja z config/embsim) liczy top-k podobnych z przesłankami per kanał
   i decyzję: znana kampania / znany operator, nowa kampania / nowy wzorzec;
2. graf dokłada DOKŁADNE zgodności z twórcą (ta sama strona, płatnik, domena, identyczny tekst; tylko ślady nie-huby);
3. twórca = dokładna zgodność, a gdy jej nie ma i silnik mówi „znana kampania / znany operator”: twórca najbliższego materiału;
   inaczej nowy twórca (nowy wzorzec);
4. zapis w grafie: węzeł (Ad albo Material) z krawędziami jak przy zwykłym ładowaniu, `CREATED_BY` do twórcy,
   `SIMILAR_TO` do top-k (wynik i powody na krawędzi), decyzja i wyjaśnienie po polsku na węźle (`verdict`, `verdict_text`).
Ponowne dodanie tego samego materiału niczego nie dubluje (MERGE w grafie, ten sam id w galerii).

Galeria (materiały, z którymi porównujemy) leży w artifacts/scrape/galeria.jsonl; jej grupy to id twórców z grafu,
więc „znana kampania tw:…” oznacza znanego twórcę. URL NIE jest odwiedzany (zasada zespołu: nie wchodzimy na strony scamu):
z adresu bierzemy tylko domenę jako ślad.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from load import ADS, CASE_CYPHER, META_CYPHER, ROOT, case_record, driver, meta_record, norm_name, reg_domain

OUT = ROOT / "artifacts" / "scrape"
GALLERY = OUT / "galeria.jsonl"
SEED = ADS.parent / "sample_s1.jsonl"
STATE = OUT / "watch_state.json"
TOP_K = 5


# --------------------------------------------------------------------------------------------------------------------
# galeria


def seed(session, path: Path) -> None:
    """Galeria startowa: reklamy z pliku (domyślnie próbka S1), grupa = ich twórca w grafie. Wektory liczone wsadowo."""
    from embsim.api import Gallery, case_from_meta_ad, case_to_dict

    g = Gallery()
    rows = [json.loads(line) for line in path.open(encoding="utf-8")]
    creator = {r["a"]: r["c"] for r in session.run(
        "UNWIND $ids AS i MATCH (a:Ad {id: i})-[:CREATED_BY]->(c:Creator) RETURN a.id AS a, c.id AS c", ids=[r["id"] for r in rows])}
    missing = sum(1 for r in rows if r["id"] not in creator)
    if missing:
        sys.exit(f"{missing} reklam z {path.name} nie ma twórcy w grafie: najpierw `load.py meta` i `creators.py build`")
    cases = [case_from_meta_ad(r) for r in rows]
    t0 = time.time()
    with_text = [c for c in cases if c.text.strip()]
    V = g.embed_fn([c.text for c in with_text]) if with_text else []
    for c, v in zip(with_text, V):
        c.vec = v
    print(f"wektory: {len(with_text)} tekstów w {time.time() - t0:.0f} s")
    OUT.mkdir(parents=True, exist_ok=True)
    with GALLERY.open("w", encoding="utf-8") as f:
        for c in cases:
            cid = creator[c.id]
            f.write(json.dumps({"case": case_to_dict(c), "group": cid, "operator": cid,
                                "vec": None if c.vec is None else [round(float(x), 6) for x in c.vec]}, ensure_ascii=False) + "\n")
    print(f"galeria: {len(cases)} materiałów, {len(set(creator.values()))} twórców -> {GALLERY}")


def open_gallery():
    from embsim.api import Gallery

    if not GALLERY.exists():
        sys.exit("brak galerii: najpierw `graph/scrape.py seed`")
    return Gallery.load(GALLERY)


def append_gallery(c, group: str) -> None:
    from embsim.api import case_to_dict

    with GALLERY.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"case": case_to_dict(c), "group": group, "operator": group,
                            "vec": None if c.vec is None else [round(float(x), 6) for x in c.vec]}, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------------------------------------------------
# graf

# dokładne zgodności: ślady nie-huby mają PART_OF do jednego twórcy; identyczny tekst bierzemy, gdy nie jest pospolity
EXACT = """
MATCH (n:$label {id: $id})
CALL (n) {
  MATCH (n)-[r:BY|PAID_BY|LINKS_TO|ADVERTISED_BY|LANDS_ON]->(x)-[:PART_OF]->(c:Creator)
  RETURN c, type(r) + ': ' + x.name AS why
  UNION
  MATCH (b:Ad {text_hash: n.text_hash})-[:CREATED_BY]->(c:Creator) WHERE n.text_hash IS NOT NULL AND b <> n
  WITH c, count(b) AS k WHERE k <= 100
  RETURN c, 'identyczny tekst (' + k + ' reklam)' AS why
}
RETURN c.id AS creator, c.name AS name, collect(DISTINCT why) AS why
ORDER BY size(why) DESC
"""

DECISION = """
MATCH (n:$label {id: $id})
MERGE (c:Creator {id: $creator})
  ON CREATE SET c.name = $creator_name, c.n_ads = 0, c.n_flagged = 0, c.label = 'brak sygnału', c.scam_share = 0.0, c.new = true
MERGE (n)-[:CREATED_BY]->(c)
SET n.verdict = $verdict, n.verdict_text = $text, n.creator_source = $source, n.added_at = datetime(),
    n.label = CASE WHEN n.meta_flag IS NOT NULL THEN 'scam' ELSE c.label END,
    n.label_source = CASE WHEN n.meta_flag IS NOT NULL THEN 'meta' WHEN c.label <> 'brak sygnału' THEN 'twórca' ELSE null END
WITH n, c
SET c.n_ads = coalesce(c.n_ads, 0) + CASE WHEN n:Ad THEN 1 ELSE 0 END
WITH n
UNWIND $matches AS m
CALL (m) { MATCH (o:Ad {id: m.id}) RETURN o UNION MATCH (o:Material {id: m.id}) RETURN o }
MERGE (n)-[s:SIMILAR_TO]->(o)
SET s.score = m.score, s.operator_score = m.operator_score, s.channels = m.channels, s.reasons = m.reasons
"""


def q(cypher: str, label: str) -> str:
    return cypher.replace("$label", label)  # etykieta nie może być parametrem Cyphera; tu tylko "Ad" albo "Material"


def write_node(session, kind: str, payload: dict) -> str:
    """Węzeł jak przy zwykłym ładowaniu (te same krawędzie do stron, płatników, domen...). Zwraca etykietę."""
    session.run(META_CYPHER if kind == "ad" else CASE_CYPHER, rows=[payload]).consume()
    return "Ad" if kind == "ad" else "Material"


HUB_OF = {"host": "Domain {name: x}", "kit": "PageKit {prefix: x}", "scheme": "UrlScheme {fingerprint: x}"}


def only_hubs(session, m) -> list[str]:
    """Pospolite ślady (hub w grafie), jeśli to JEDYNE, co łączy z najbliższym materiałem; inaczej pusta lista.
    Silnik embsim potrafi dać 0,95 za samo wspólne google.com; graf wie, że to hub, więc takiego połączenia nie przyjmujemy."""
    chans = {k for k, v in m.channels.items() if v > 0}
    if not chans or not chans <= set(HUB_OF):
        return []
    hubs = []
    for ch in chans:
        vals = m.shared.get(ch, [])
        if not vals:
            return []
        n = session.run(f"UNWIND $v AS x MATCH (h:{HUB_OF[ch]}) WHERE h.hub RETURN count(h) AS n", v=vals).single()["n"]
        if n < len(vals):
            return []
        hubs += vals
    return hubs


def decide_creator(session, label: str, id: str, d, gallery_group: dict) -> tuple[str, str, str]:
    """(id twórcy, nazwa, źródło przypisania)."""
    exact = list(session.run(q(EXACT, label), id=id))
    if exact:
        e = exact[0]
        src = "dokładna zgodność: " + "; ".join(e["why"][:3])
        if len(exact) > 1:
            src += f" (uwaga: pasuje też do {len(exact) - 1} innych twórców)"
        return e["creator"], e["name"], src
    if d.verdict in ("znana_kampania", "znany_operator_nowa_kampania") and d.matches:
        best = d.matches[0] if d.verdict == "znana_kampania" else max(d.matches, key=lambda m: m.operator_score)
        g = gallery_group.get(best.id)
        hubs = only_hubs(session, best)
        if hubs:
            why = f"nowy wzorzec: silnik łączył z {best.id} tylko przez pospolity ślad ({', '.join(hubs[:3])}), więc to pomijamy"
            return f"tw:{id}", "nowy twórca", why
        if g:
            name = session.run("MATCH (c:Creator {id: $c}) RETURN c.name AS n", c=g).single()
            return g, name["n"] if name else g, f"podobieństwo do {best.id} ({d.verdict.replace('_', ' ')})"
    return f"tw:{id}", "nowy twórca", "nowy wzorzec: brak dokładnej zgodności i podobnego materiału"


def match_rows(d) -> list[dict]:
    from embsim.api import _CHANNEL_PL, _EXTRA_PL

    out = []
    for m in d.matches[:TOP_K]:
        reasons = [f"{_CHANNEL_PL.get(k, k)} {v:.2f}" for k, v in sorted(m.channels.items(), key=lambda kv: -kv[1]) if v > 0]
        reasons += [f"{_EXTRA_PL.get(k, k)}: {', '.join(v[:2])}" for k, v in m.extra_shared.items()]
        out.append({"id": m.id, "score": round(m.campaign_score, 3), "operator_score": round(m.operator_score, 3),
                    "channels": sorted(k for k, v in m.channels.items() if v > 0), "reasons": reasons[:6]})
    return out


# --------------------------------------------------------------------------------------------------------------------
# wejścia


def inputs(target: str | None, text: str | None, url: str | None):
    """Zwraca listę (kind, payload do grafu, Case do embsim)."""
    from embsim.api import case_from_folder, case_from_meta_ad, case_from_text

    if text is not None or url is not None:
        import hashlib

        dom = reg_domain(url.split("/")[2]) if url and "//" in url else None
        tid = "tekst:" + hashlib.sha1(f"{text or ''}|{url or ''}".encode()).hexdigest()[:10]
        case = case_from_text(tid, text or "", host={dom} if dom else set())
        payload = {"id": tid, "name": (text or url or "")[:60], "source": "wklejony tekst", "title": "", "titles": [],
                   "text": text or "", "ocr_text": "", "keywords": [], "missing": [], "cloaking": [], "pages": [],
                   "notes": [f"adres (nieodwiedzany): {url}"] if url else [], "observed_at": None, "observed_last": None,
                   "files": [], "persons": [], "products": [], "brands": [], "contacts": [], "topics": [], "ads": [],
                   "accounts": [], "advertisers": [], "trackers": [], "landing": [dom] if dom else [], "calls": [], "redirects": [],
                   "kits": [], "schemes": [], "images": [], "dataset": "nowe", "truth_campaign": None, "truth_operator": None,
                   "truth_kind": None}
        return [("m", payload, case)]
    p = Path(target)
    if p.is_dir():
        from fejki.demo.material import load_persons, material_from_folder

        m = material_from_folder(p, ocr=True, persons=load_persons())
        m.id = f"nowy:{p.name}"
        case = case_from_folder(p)
        case.id = m.id
        payload = {**case_record(m, ROOT, folder=p), "dataset": "nowe", "truth_campaign": None, "truth_operator": None, "truth_kind": None}
        return [("m", payload, case)]
    from fejki.demo.material import load_persons

    persons = load_persons()
    out = []
    for line in p.open(encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            rec = meta_record(r, persons)
            rec["page_norm"] = norm_name(rec["page_name"])
            out.append(("ad", rec, case_from_meta_ad(r)))
    return out


def add(session, items, g=None, quiet: bool = False) -> list[dict]:
    g = g or open_gallery()
    group = {it["case"].id: it["group"] for it in g.items}
    report = []
    for kind, payload, case in items:
        t0 = time.time()
        dup = case.id in group
        d = g.query(case, TOP_K, exclude_id=case.id)
        label = write_node(session, kind, payload)
        cid, cname, src = decide_creator(session, label, case.id, d, group)
        if "pospolity ślad" in src:  # decyzja silnika poprawiona przez graf (hub)
            d.verdict = "nowy_wzorzec"
        text = d.explain() + f"\nTwórca: {cname} [{cid}] ({src})."
        session.run(q(DECISION, label), id=case.id, creator=cid, creator_name=cname, verdict=d.verdict, text=text, source=src,
                    matches=match_rows(d)).consume()
        if not dup:
            g.add(case, group=cid, operator=cid)
            append_gallery(g.items[-1]["case"], cid)
            group[case.id] = cid
        report.append({"id": case.id, "decyzja": d.verdict, "wynik": round(d.campaign_score, 2), "twórca": cname, "id_twórcy": cid,
                       "skąd": src, "nowy w galerii": not dup, "s": round(time.time() - t0, 1)})
        if not quiet:
            print(f"\n== {case.id}  ({report[-1]['s']} s)\n{text}")
    return report


def watch(session, path: Path, every_min: int) -> None:
    """Scraper: przetwarza linie dopisane do pliku od poprzedniego przebiegu (stan w artifacts/scrape/watch_state.json)."""
    from embsim.api import case_from_meta_ad
    from fejki.demo.material import load_persons

    g = open_gallery()
    persons = load_persons()
    while True:
        state = json.loads(STATE.read_text()) if STATE.exists() else {}
        done = state.get(str(path), 0)
        with path.open(encoding="utf-8") as f:
            lines = f.readlines()
        new = [ln for ln in lines[done:] if ln.strip()]
        items = []
        for line in new:
            r = json.loads(line)
            rec = meta_record(r, persons)
            rec["page_norm"] = norm_name(rec["page_name"])
            items.append(("ad", rec, case_from_meta_ad(r)))
        rep = add(session, items, g, quiet=True)
        state[str(path)] = len(lines)
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(state))
        stamp = time.strftime("%F %T")
        verdicts = {v: sum(r["decyzja"] == v for r in rep) for v in {r["decyzja"] for r in rep}}
        print(f"[{stamp}] nowych reklam: {len(rep)}  {verdicts}")
        if rep:
            with (OUT / "watch_report.jsonl").open("a", encoding="utf-8") as f:
                for r in rep:
                    f.write(json.dumps({"at": stamp, **r}, ensure_ascii=False) + "\n")
        if every_min <= 0:
            return
        time.sleep(every_min * 60)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["seed", "add", "watch"])
    ap.add_argument("target", nargs="?", help="seed/watch: plik JSONL; add: plik JSONL albo folder przypadku")
    ap.add_argument("--text", help="add: wklejony tekst reklamy")
    ap.add_argument("--url", help="add: adres reklamy (NIE jest odwiedzany, bierzemy tylko domenę)")
    ap.add_argument("--every-min", type=int, default=0, help="watch: co ile minut (0 = jeden przebieg)")
    a = ap.parse_args()
    drv = driver()
    with drv.session() as s:
        if a.what == "seed":
            seed(s, Path(a.target) if a.target else SEED)
        elif a.what == "add":
            if not a.target and a.text is None and a.url is None:
                sys.exit("podaj plik JSONL, folder albo --text / --url")
            rep = add(s, inputs(a.target, a.text, a.url))
            if len(rep) > 1:
                print("\n" + "\n".join(f"{r['id']:<22} {r['decyzja']:<30} {r['wynik']:<5} {r['twórca']}" for r in rep))
        else:
            if not a.target:
                sys.exit("podaj plik JSONL, który zbiera scraper (np. ../data/meta/ads.jsonl)")
            watch(s, Path(a.target), a.every_min)
    drv.close()


if __name__ == "__main__":
    main()
