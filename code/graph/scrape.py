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
import decision as dec
import resume

OUT = ROOT / "artifacts" / "scrape"
GALLERY = OUT / "galeria.jsonl"
SEED = ADS.parent / "sample_s1.jsonl"
STATE = OUT / "watch_state.json"
ERRORS = OUT / "watch_errors.jsonl"
TOP_K = 5


# --------------------------------------------------------------------------------------------------------------------
# galeria


def seed(session, path: Path) -> None:
    """Galeria startowa: reklamy z pliku (domyślnie próbka S1), grupa = ich twórca w grafie. Wektory liczone wsadowo."""
    from embsim.api import Gallery, case_from_meta_ad, case_to_dict

    g = Gallery(profile="meta")                       # reklamy Meta: próg kampanii 0,5
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
            f.write(json.dumps({"case": case_to_dict(c), "group": dec.campaign_of(cid, cid), "operator": cid,   # kampania != operator
                                "vec": None if c.vec is None else [round(float(x), 6) for x in c.vec]}, ensure_ascii=False) + "\n")
    seed_campaigns(session, creator)
    print(f"galeria: {len(cases)} materiałów, {len(set(creator.values()))} twórców -> {GALLERY}")


def seed_campaigns(session, creator: dict[str, str]) -> None:
    """Kampania domyślna każdego twórcy z próbki (`kam:<twórca>#0`) jako węzeł w grafie, z reklamami startowymi."""
    rows = [{"ad": a, "c": c, "camp": dec.campaign_of(c, c)} for a, c in creator.items()]
    for i in range(0, len(rows), 2000):
        session.run("""UNWIND $rows AS r MATCH (a:Ad {id: r.ad}), (c:Creator {id: r.c})
            MERGE (k:Campaign {id: r.camp}) ON CREATE SET k.origin = 'seed', k.created_at = datetime()
            MERGE (k)-[:RUN_BY]->(c)
            MERGE (a)-[ic:IN_CAMPAIGN]->(k) SET ic.source = 'seed: kampania domyślna twórcy', ic.method = 'seed'""", rows=rows[i:i + 2000]).consume()


def open_gallery():
    from embsim.api import Gallery

    if not GALLERY.exists():
        sys.exit("brak galerii: najpierw `graph/scrape.py seed`")
    cut = resume.repair_gallery(GALLERY)           # niedokończony wiersz po awarii dopisywania
    if cut:
        print(f"galeria: odcięto {cut} bajtów niedokończonego wiersza")
    g = Gallery.load(GALLERY, profile="meta")
    for it in g.items:                              # stare galerie: w polu grupy było id twórcy
        it["group"] = dec.campaign_of(it["group"], it.get("operator")) or it["group"]
    return g


def append_gallery(c, campaign: str, operator: str) -> None:
    from embsim.api import case_to_dict

    resume.append_line(GALLERY, {"case": case_to_dict(c), "group": campaign, "operator": operator,
                                 "vec": None if c.vec is None else [round(float(x), 6) for x in c.vec]})


# --------------------------------------------------------------------------------------------------------------------
# graf

def node_cypher(kind: str) -> str:
    return META_CYPHER if kind == "ad" else CASE_CYPHER


def account_of(kind: str, payload: dict) -> str | None:
    """Konto reklamowe materiału (osobno od kampanii i operatora): strona reklamodawcy Meta albo pierwsze konto z przypadku."""
    if kind == "ad" and payload.get("page_id"):
        return "fb:" + str(payload["page_id"])
    accs = payload.get("accounts") or []
    return str(accs[0]) if accs else None


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


def add(session, items, g=None, quiet: bool = False, skip_done: bool = False) -> list[dict]:
    """Dodaje materiały: silnik decyduje, graf zapisuje kampanię, operatora i konto OSOBNO, w jednej transakcji na materiał.

    `skip_done`: pomija materiały, dla których graf ma już decyzję tej wersji metody (rejestr przetworzonych; używa go `watch`)."""
    g = g or open_gallery()
    method = dec.method_version(g)
    campaign = {it["case"].id: it["group"] for it in g.items}
    operator = {it["case"].id: it.get("operator") or it["group"] for it in g.items}
    if skip_done:
        done = {}
        for kind in ("ad", "m"):
            ids = [c.id for k, _, c in items if k == kind]
            done[kind] = dec.decided(session, "Ad" if kind == "ad" else "Material", ids, method)
        items = [it for it in items if it[2].id not in done[it[0]]]
    report = []
    for kind, payload, case in items:
        t0 = time.time()
        dup = case.id in campaign
        label = "Ad" if kind == "ad" else "Material"
        d = g.query(case, TOP_K, exclude_id=case.id)
        rows, acc = match_rows(d), account_of(kind, payload)

        def make_rec(tx, d=d, label=label, case=case, rows=rows, acc=acc):
            rec = dec.resolve(tx, label, case.id, d, gallery_campaign=campaign, gallery_operator=operator, account=acc,
                              method=method, matches=rows)
            rec.text = d.explain() + (f"\nKampania: {rec.campaign_id}{' (nowa)' if rec.new_campaign else ''}. "
                                     f"Operator: {rec.operator_name} [{rec.operator_id}] ({rec.source}).")
            return rec

        rec = session.execute_write(dec.write_decision, node_cypher(kind), [payload], make_rec)
        if not dup:
            g.add(case, group=rec.campaign_id, operator=rec.operator_id)
            append_gallery(g.items[-1]["case"], rec.campaign_id, rec.operator_id)
            campaign[case.id], operator[case.id] = rec.campaign_id, rec.operator_id
        report.append({"id": case.id, "decyzja": rec.verdict, "wynik": round(d.campaign_score, 2), "twórca": rec.operator_name,
                       "id_twórcy": rec.operator_id, "kampania": rec.campaign_id, "konto": rec.account_id, "skąd": rec.source,
                       "nowa kampania": rec.new_campaign, "do weryfikacji": rec.conflicts, "nowy w galerii": not dup,
                       "s": round(time.time() - t0, 1)})
        if not quiet:
            print(f"\n== {case.id}  ({report[-1]['s']} s)\n{rec.text}")
    return report


BATCH_LINES = 50


def watch(session, path: Path, every_min: int) -> None:
    """Scraper: przetwarza linie dopisane do pliku od poprzedniego przebiegu; można go przerwać w dowolnym momencie i wznowić.

    Czyta od zapamiętanego bajtu (`resume.read_new`), kończy tylko na pełnych liniach, zapisuje stan atomowo po każdej paczce, pomija to,
    co graf już rozstrzygnął, a złe linie odkłada do `watch_errors.jsonl` zamiast zatrzymywać import."""
    from embsim.api import case_from_meta_ad
    from fejki.demo.material import load_persons

    g = open_gallery()
    persons = load_persons()
    while True:
        st = resume.load_state(STATE, path)
        if st.get("reset"):
            print(f"[{time.strftime('%F %T')}] plik zmieniony lub skrócony: czytam od początku (to, co już rozstrzygnięto, jest pomijane)")
        offset, head, total = st["offset"], st["head"], 0
        verdicts: dict[str, int] = {}
        while True:
            lines, new_off = resume.read_new(path, offset, BATCH_LINES)
            if new_off == offset:
                break
            items = []
            for _, line in lines:
                try:
                    r = json.loads(line)
                    rec = meta_record(r, persons)
                    rec["page_norm"] = norm_name(rec["page_name"])
                    items.append(("ad", rec, case_from_meta_ad(r)))
                except Exception as e:                      # zła linia nie blokuje reszty
                    resume.log_error(ERRORS, line, f"{type(e).__name__}: {e}")
            rep = add(session, items, g, quiet=True, skip_done=True)
            resume.save_state(STATE, path, new_off, head)   # dopiero po zapisaniu paczki w grafie i galerii
            offset, total = new_off, total + len(rep)
            for r in rep:
                verdicts[r["decyzja"]] = verdicts.get(r["decyzja"], 0) + 1
            if rep:
                with (OUT / "watch_report.jsonl").open("a", encoding="utf-8") as f:
                    for r in rep:
                        f.write(json.dumps({"at": time.strftime("%F %T"), **r}, ensure_ascii=False) + "\n")
        print(f"[{time.strftime('%F %T')}] nowych reklam: {total}  {verdicts}")
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
