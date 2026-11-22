"""Warstwa grafu: kontrakt decyzji (kampania / operator / konto osobno), zapis transakcyjny i wznawianie, pochodzenie etykiety scam.

Wymaga lokalnej bazy Neo4j, którą stawia jednorazowo:

    docker run -d --rm --name fejki-neo4j-test -p 17474:7474 -p 17687:7687 -e NEO4J_AUTH=neo4j/testpass12345 neo4j:5.26-community

Adres: `FEJKI_TEST_NEO4J` (domyślnie bolt://localhost:17687), hasło: `FEJKI_TEST_NEO4J_PASSWORD`. Testy CZYSZCZĄ bazę, więc odmawiają pracy
na czymkolwiek innym niż localhost i na porcie 7687 (zwykła lokalna baza zespołu) i nigdy nie dotykają serwera Railway.
Bez bazy testy są pomijane. Wymaga też modelu tekstu embsim w cache (jak reszta testów silnika).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "graph"))
neo4j = pytest.importorskip("neo4j")

URI = os.environ.get("FEJKI_TEST_NEO4J", "bolt://localhost:17687")
PASSWORD = os.environ.get("FEJKI_TEST_NEO4J_PASSWORD", "testpass12345")
_u = urlsplit(URI)
if _u.hostname not in ("localhost", "127.0.0.1") or _u.port == 7687:
    pytest.skip("testy grafu czyszczą bazę: dozwolona tylko jednorazowa baza testowa na localhost (nie port 7687)", allow_module_level=True)

import creators  # noqa: E402
import decision as dec  # noqa: E402
import load  # noqa: E402
import provenance  # noqa: E402
import resume  # noqa: E402
import scrape  # noqa: E402

REMOVED = "This ad was removed because it didn't follow our advertising standards"
BLOCKED = "The page later disabled for not following our policies"


@pytest.fixture()
def db(tmp_path, monkeypatch):
    try:
        drv = neo4j.GraphDatabase.driver(URI, auth=("neo4j", PASSWORD))
        drv.verify_connectivity()
    except Exception:
        pytest.skip("brak lokalnej bazy testowej Neo4j (zob. docstring)")
    monkeypatch.setenv("NEO4J_URI", URI)
    monkeypatch.setenv("NEO4J_PASSWORD", PASSWORD)
    for name, val in (("OUT", tmp_path / "scrape"), ("GALLERY", tmp_path / "scrape" / "galeria.jsonl"),
                      ("STATE", tmp_path / "scrape" / "watch_state.json"), ("ERRORS", tmp_path / "scrape" / "watch_errors.jsonl")):
        monkeypatch.setattr(scrape, name, val)
    with drv.session() as s:
        s.run("MATCH (n) DETACH DELETE n").consume()
        load.schema(s)
        yield s
    drv.close()


def raw(ad_id, page, text, payer="Jan Kowalski", caption="dom-x.pl", flag=None):
    r = {"id": ad_id, "page_id": page[0], "page_name": page[1], "ad_creative_bodies": [text], "ad_creative_link_titles": [text[:24]],
         "ad_creative_link_captions": [caption], "beneficiary_payers": [{"payer": payer}], "ad_creation_time": "2026-01-01",
         "ad_delivery_start_time": "2026-01-01", "publisher_platforms": ["facebook"]}
    if flag:
        r["ad_creative_bodies"], r["ad_creative_link_captions"] = [flag], [flag]
    return r


def payload(r):
    from fejki.demo.material import load_persons

    rec = load.meta_record(r, load_persons())
    rec["page_norm"] = load.norm_name(rec["page_name"])
    return rec


def load_ads(s, rows):
    s.run(load.META_CYPHER, rows=[payload(r) for r in rows]).consume()


PAGE_X, PAGE_Y = ("111", "Alfa Media"), ("222", "Beta Sklep")
TEXT_X = "Jak zwykły Polak zarobił na kryptowalutach po rozmowie z prezesem banku. Zacznij inwestować jeszcze dziś, bez ryzyka."
TEXT_Y = "Wyprzedaż kuchenek mikrofalowych i robotów kuchennych, tylko w tym tygodniu, darmowa dostawa na terenie całego kraju."
TEXT_B = "Przepis na szarlotkę: jabłka, cynamon, mąka, masło, trzy jajka i godzina w piekarniku nagrzanym do 180 stopni."


def world(s, tmp_path):
    """Operator X (3 reklamy w galerii + 4. tylko w grafie z domeną dom-x2.pl) i obcy operator Y; twórcy zbudowani, galeria wysiana."""
    seed_rows = [raw("x1", PAGE_X, TEXT_X), raw("x2", PAGE_X, TEXT_X + " Sprawdź szczegóły."), raw("x3", PAGE_X, TEXT_X + " Ostatnie miejsca."),
                 raw("y1", PAGE_Y, TEXT_Y, payer="Inna Firma", caption="dom-y.pl"), raw("y2", PAGE_Y, TEXT_Y + " Zamów.", payer="Inna Firma",
                                                                                      caption="dom-y.pl")]
    load_ads(s, seed_rows + [raw("x4", PAGE_X, "Inna treść tej samej strony do domeny x2", caption="dom-x2.pl")])
    creators.build(s, 100)
    path = tmp_path / "seed.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in seed_rows), encoding="utf-8")
    scrape.seed(s, path)
    return seed_rows


def count(s, cypher, **p):
    return s.run(cypher, **p).single()[0]


def test_form_shows_two_campaigns_of_one_operator(db, tmp_path):
    world(db, tmp_path)
    op = count(db, "MATCH (:Ad {id: 'x1'})-[:CREATED_BY]->(c:Creator) RETURN c.id")
    assert op != count(db, "MATCH (:Ad {id: 'y1'})-[:CREATED_BY]->(c:Creator) RETURN c.id")
    # formularz 1: ta sama treść i domena operatora X; formularz 2: zupełnie inna treść, druga domena operatora X (znana tylko grafowi)
    r1 = scrape.add(db, scrape.inputs(None, TEXT_X, "https://dom-x.pl/oferta"))[0]
    r2 = scrape.add(db, scrape.inputs(None, TEXT_B, "https://dom-x2.pl/ciasto"))[0]
    assert r1["id_twórcy"] == r2["id_twórcy"] == op          # operator: ten sam
    assert r1["kampania"] != r2["kampania"] and r2["nowa kampania"]   # kampanie: dwie
    rows = db.run("MATCH (c:Creator {id: $op})<-[:RUN_BY]-(k:Campaign)<-[:IN_CAMPAIGN]-(m:Material) "
                  "RETURN k.id AS k, collect(m.id) AS m ORDER BY k", op=op).data()
    assert len(rows) == 2
    # odczyt decyzji: kampania, operator, wersja metody i źródło są osobnymi polami i krawędziami
    d = db.run("MATCH (m:Material)-[:HAS_DECISION]->(d:Decision)-[:CAMPAIGN]->(k), (d)-[:OPERATOR]->(o) "
               "RETURN m.id AS m, k.id AS k, o.id AS o, d.method AS method, d.source AS source", ).data()
    assert len(d) == 2 and {x["o"] for x in d} == {op} and len({x["k"] for x in d}) == 2
    assert all(x["method"].endswith("|" + dec.CONTRACT) and x["source"] for x in d)


def test_gallery_keeps_campaign_and_operator_apart(db, tmp_path):
    world(db, tmp_path)
    scrape.add(db, scrape.inputs(None, TEXT_B, "https://dom-x2.pl/ciasto"))
    rows = [json.loads(line) for line in scrape.GALLERY.read_text(encoding="utf-8").splitlines()]
    assert all(r["group"].startswith("kam:") for r in rows)
    last = rows[-1]
    assert last["operator"].startswith("tw:") and last["group"] != last["operator"]


def test_ad_counters_change_only_on_real_change_and_retry_is_idempotent(db, tmp_path):
    world(db, tmp_path)
    before = db.run("MATCH (c:Creator)<-[:CREATED_BY]-(:Ad {id: 'x1'}) RETURN c.id AS id, c.n_ads AS n, c.n_flagged AS f").single()
    new = raw("x5", PAGE_X, TEXT_X + " Nowy wariant.", flag=REMOVED)
    for _ in range(3):                                         # trzy powtórzenia = jedna zmiana
        scrape.add(db, [("ad", {**payload(new), "page_norm": "alfa media"}, scrape_case(new))])
    after = db.run("MATCH (c:Creator {id: $id}) RETURN c.n_ads AS n, c.n_flagged AS f", id=before["id"]).single()
    assert after["n"] == before["n"] + 1 and after["f"] == before["f"] + 1
    assert count(db, "MATCH (:Ad {id: 'x5'})-[:HAS_DECISION]->(d) RETURN count(d)") == 1
    assert count(db, "MATCH (:Ad {id: 'x5'})-[:SIMILAR_TO]->() RETURN count(*) >= 0") is True
    again = scrape.add(db, [("ad", {**payload(new), "page_norm": "alfa media"}, scrape_case(new))], skip_done=True)
    assert again == []                                          # rejestr przetworzonych


def scrape_case(r):
    from embsim.api import case_from_meta_ad

    return case_from_meta_ad(r)


def test_failed_write_leaves_no_half_state(db, tmp_path, monkeypatch):
    world(db, tmp_path)
    ad = raw("x6", PAGE_X, TEXT_X + " Awaria.")

    def boom(run, ids=None):
        raise RuntimeError("awaria w środku transakcji")

    monkeypatch.setattr(provenance, "refresh", boom)
    with pytest.raises(RuntimeError):
        scrape.add(db, [("ad", {**payload(ad), "page_norm": "alfa media"}, scrape_case(ad))])
    assert count(db, "MATCH (a:Ad {id: 'x6'}) RETURN count(a)") == 0       # węzeł nie powstał
    assert count(db, "MATCH (d:Decision) RETURN count(d)") == 0


def test_rebuild_is_published_atomically(db, tmp_path, monkeypatch):
    world(db, tmp_path)
    n0 = count(db, "MATCH (c:Creator) RETURN count(c)")
    db.run("MATCH (c:Creator) SET c.marker = 'stary'").consume()

    def boom(run, ids=None):
        raise RuntimeError("awaria przy przebudowie")

    monkeypatch.setattr(provenance, "refresh", boom)
    with pytest.raises(RuntimeError):
        creators.build(db, 100)
    assert count(db, "MATCH (c:Creator) RETURN count(c)") == n0              # nic nie skasowane przed zapisem
    assert count(db, "MATCH (c:Creator) WHERE c.marker = 'stary' RETURN count(c)") == n0
    assert count(db, "MATCH (:Ad)-[:CREATED_BY]->(:Creator) RETURN count(*)") == 6
    monkeypatch.undo()
    creators.build(db, 100)                                                  # po poprawnym przebiegu: stan z nowego zapisu
    assert count(db, "MATCH (m:GraphMeta {key: 'creators'}) RETURN m.status") == "ready"


def test_rebuild_keeps_scraper_history(db, tmp_path):
    world(db, tmp_path)
    scrape.add(db, scrape.inputs(None, TEXT_B, "https://dom-x2.pl/ciasto"))
    d0 = count(db, "MATCH (d:Decision) RETURN count(d)")
    k0 = count(db, "MATCH (k:Campaign) RETURN count(k)")
    creators.build(db, 100)
    assert count(db, "MATCH (d:Decision) RETURN count(d)") == d0 and count(db, "MATCH (k:Campaign) RETURN count(k)") == k0


def test_label_provenance_separates_ad_removal_block_and_analyst(db, tmp_path):
    load_ads(db, [raw(f"a{i}", PAGE_X, TEXT_X + f" {i}") for i in range(4)] + [raw("r1", PAGE_X, "", flag=REMOVED),
                                                                              raw("b1", PAGE_X, "", flag=BLOCKED)])
    creators.build(db, 100)
    c = db.run("MATCH (c:Creator) RETURN c").single()["c"]
    assert (c["n_ads"], c["n_removed_ads"], c["n_blocked_ads"], c["label_num"], c["label_den"]) == (6, 1, 1, 2, 6)
    assert c["label"] == "podejrzany" and c["label_basis"] == "zdjęcie reklamy + blokada konta" and c["label_at"] is not None
    kinds = {r["k"]: (r["num"], r["den"]) for r in db.run("MATCH (:Creator)-[:HAS_EVIDENCE]->(e) RETURN e.kind AS k, e.num AS num, e.den AS den")}
    assert kinds == {"zdjęcie reklamy": (1, 6), "blokada konta": (1, 6)}
    own = {r["id"]: (r["l"], r["s"], r["b"]) for r in db.run("MATCH (a:Ad) RETURN a.id AS id, a.label AS l, a.label_source AS s, a.label_basis AS b")}
    assert own["r1"] == ("scam", "meta", "zdjęcie reklamy") and own["b1"] == ("scam", "meta", "blokada konta")
    assert own["a0"] == ("podejrzany", "twórca", "zdjęcie reklamy + blokada konta")
    # analityk przeczy automatowi: wygrywa, ale zostaje konflikt do weryfikacji i ślad po automacie
    provenance.record_analyst_verdict(db, c["id"], "nie scam", "ola", "legalny wydawca")
    c2 = db.run("MATCH (c:Creator) RETURN c").single()["c"]
    assert c2["label"] == "nie scam" and c2["auto_label"] == "podejrzany" and c2["label_basis"] == "ocena analityka"
    assert c2["needs_review"] and any("analityk" in r for r in c2["review_reasons"])
    assert count(db, "MATCH (a:Ad {id: 'a0'}) RETURN a.label_source") == "analityk"
    assert count(db, "MATCH (a:Ad {id: 'r1'}) RETURN a.label") == "scam"          # własny dowód Mety nie znika
    provenance.record_analyst_verdict(db, c["id"], "scam", "jan")                   # nowa ocena zastępuje, historia zostaje
    assert count(db, "MATCH (v:AnalystVerdict) RETURN count(v)") == 2
    assert count(db, "MATCH (v:AnalystVerdict {current: true}) RETURN count(v)") == 1


def test_mixed_pages_flag_creator_for_review(db):
    pages = [("1", "Strona jeden"), ("2", "Strona dwa")]
    ads = [raw(f"p{i}", pages[0], "", payer="Wspólny", flag=REMOVED) for i in range(3)]
    ads += [raw(f"q{i}", pages[1], TEXT_Y + str(i), payer="Wspólny") for i in range(4)]
    load_ads(db, ads)
    creators.build(db, 100)
    c = db.run("MATCH (c:Creator) RETURN c").single()["c"]
    assert c["page_conflict"] and c["needs_review"]
    assert [r["id"] for r in provenance.review_list(db)] == [c["id"]]


def test_exact_match_to_several_creators_is_recorded_as_conflict(db, tmp_path):
    load_ads(db, [raw("m1", ("1", "Strona jeden"), TEXT_X, payer="P1", caption="wspolna.pl"),
                  raw("m2", ("2", "Strona dwa"), TEXT_Y, payer="P2", caption="inna.pl")])
    creators.build(db, 100)
    # materiał z adresem w domenie jednego twórcy i tekstem identycznym z reklamą drugiego: dwa dowody, dwóch twórców
    path = tmp_path / "seed.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in [raw("m1", ("1", "Strona jeden"), TEXT_X, payer="P1", caption="wspolna.pl"),
                                                     raw("m2", ("2", "Strona dwa"), TEXT_Y, payer="P2", caption="inna.pl")]), encoding="utf-8")
    scrape.seed(db, path)
    rep = scrape.add(db, scrape.inputs(None, TEXT_Y, "https://wspolna.pl/x"))[0]
    assert rep["do weryfikacji"]
    assert count(db, "MATCH (:Decision)-[:CONFLICTS_WITH]->(c:Creator) RETURN count(DISTINCT c)") >= 1
    assert count(db, "MATCH (c:Creator) WHERE c.needs_review RETURN count(c)") >= 1


# --------------------------------------------------------------------------------------------------------------------
# wznawianie importu (bez bazy)


def test_read_new_waits_for_unfinished_line_and_advances_by_bytes(tmp_path):
    f = tmp_path / "ads.jsonl"
    f.write_bytes(b'{"id": "1"}\n{"id": "2"}\n{"id": "3"')            # trzecia linia niedokończona
    lines, off = resume.read_new(f, 0)
    assert [json.loads(x)["id"] for _, x in lines] == ["1", "2"] and off == len(b'{"id": "1"}\n{"id": "2"}\n')
    with f.open("ab") as h:
        h.write(b', "x": 1}\n')                                        # writer dokończył
    lines, off2 = resume.read_new(f, off)
    assert [json.loads(x)["id"] for _, x in lines] == ["3"] and off2 == f.stat().st_size
    f.write_bytes(b'{"id": "1"}\n{"id": "2"}\n{"id": "3"}')            # ostatnia linia bez \n, ale poprawny JSON: bierzemy
    assert len(resume.read_new(f, 0)[0]) == 3


def test_state_is_atomic_and_resets_when_file_is_replaced(tmp_path):
    f, st = tmp_path / "ads.jsonl", tmp_path / "state.json"
    f.write_text('{"id": "1"}\n{"id": "2"}\n', encoding="utf-8")
    s0 = resume.load_state(st, f)
    assert s0["offset"] == 0
    resume.save_state(st, f, 12, s0["head"])
    assert resume.load_state(st, f)["offset"] == 12 and not (tmp_path / "state.tmp").exists()
    f.write_text('{"id": "9"}\n', encoding="utf-8")                    # podmieniony, krótszy plik
    assert resume.load_state(st, f)["offset"] == 0
    st.write_text("{broken", encoding="utf-8")                          # uszkodzony stan nie wywraca importu
    assert resume.load_state(st, f)["offset"] == 0


def test_repair_gallery_drops_half_written_row(tmp_path):
    g = tmp_path / "galeria.jsonl"
    resume.append_line(g, {"a": 1})
    resume.append_line(g, {"a": 2})
    with g.open("ab") as h:
        h.write(b'{"a": 3, "cut')                                      # awaria w środku dopisywania
    assert resume.repair_gallery(g) > 0
    assert [json.loads(x)["a"] for x in g.read_text().splitlines()] == [1, 2]
    assert resume.repair_gallery(g) == 0


def test_watch_resumes_without_duplicates(db, tmp_path):
    world(db, tmp_path)
    feed = tmp_path / "ads_nowe.jsonl"
    a1, a2 = raw("w1", PAGE_X, TEXT_X + " Pierwsza."), raw("w2", PAGE_X, TEXT_X + " Druga.")
    feed.write_text(json.dumps(a1) + "\nto nie jest json\n" + json.dumps(a2)[:40], encoding="utf-8")   # zła linia + niedokończona
    scrape.watch(db, feed, 0)
    assert count(db, "MATCH (a:Ad) WHERE a.id IN ['w1', 'w2'] RETURN count(a)") == 1       # w2 czeka na dokończenie
    assert scrape.ERRORS.exists() and "to nie jest json" in scrape.ERRORS.read_text(encoding="utf-8")
    with feed.open("w", encoding="utf-8") as h:                                             # writer dokończył plik
        h.write(json.dumps(a1) + "\nto nie jest json\n" + json.dumps(a2) + "\n")
    st = json.loads(scrape.STATE.read_text(encoding="utf-8"))[str(feed)]
    assert 0 < st["offset"] < feed.stat().st_size
    scrape.watch(db, feed, 0)
    scrape.watch(db, feed, 0)                                                               # trzeci przebieg: nic nowego
    assert count(db, "MATCH (a:Ad) WHERE a.id IN ['w1', 'w2'] RETURN count(a)") == 2
    assert count(db, "MATCH (:Ad)-[:HAS_DECISION]->(d) WHERE d.node_id IN ['w1', 'w2'] RETURN count(d)") == 2
    assert count(db, "MATCH (c:Creator)<-[:CREATED_BY]-(a:Ad) WHERE a.id IN ['w1', 'w2'] RETURN count(DISTINCT c)") == 1
