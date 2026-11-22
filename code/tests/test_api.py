import hashlib

import numpy as np

from embsim.api import Gallery, case_from_dict, case_from_meta_ad, case_from_text, case_to_dict
from embsim.bench import Config


def fake_embed(texts, dim=96):
    V = np.zeros((len(texts), dim))
    for i, t in enumerate(texts):
        for w in t.lower().split():
            V[i, int(hashlib.md5(w.encode()).hexdigest(), 16) % dim] += 1
    return V / np.maximum(np.linalg.norm(V, axis=1, keepdims=True), 1e-9)


def cfg():
    return Config(adjust_levels=["campaign"], lexical=True, thresholds={"campaign": 0.6, "operator": 0.275}, e_ref={"campaign": 0.8})


CAMP = {
    "A": "Rafał Brzoska postrzelony nagranie usunięto dziennikarze ujawniają platforma zarobki wpłać {n} zł obserwuj zysk już dziś zostało tylko miejsc",
    "B": "Monika Olejnik ujawnia sekret bogactwa platforma inwestycyjna z AI daje dziennie bez doświadczenia oferta kończy się dziś zarejestruj się odbierz bonus {n}",
    "C": "Adam Glapiński zdradził w studiu jak zarabiać pasywnie banki nie chcą żebyś to wiedział zacznij od {n} zł algorytm robi resztę",
}
KIT = {"A": "/kita/landing", "B": "/kitb/lp", "C": "/kitc/lp"}
SCHEME = {"A": "utm_a,utm_id", "B": "utm_b,utm_visit", "C": "utm_c,gclid"}


def mat(cid, k, n):
    return case_from_text(f"{cid}{k}", CAMP[cid].format(n=n), kit={KIT[cid]}, scheme={SCHEME[cid]})


def build():
    g = Gallery(cfg(), embed_fn=fake_embed)
    for cid in "ABC":
        for k in range(3):
            g.add(mat(cid, k, 100 * (k + 1)))
    return g


def test_known_variant_gets_group_and_evidence_new_pattern_gets_new():
    g = build()
    base = {it["case"].id: it["group"] for it in g.items}
    d = g.query(mat("A", 9, 777))
    assert d.verdict == "znana_kampania" and d.group == base["A0"]
    assert d.matches[0].id.startswith("A") and d.matches[0].shared.get("kit") == ["/kita/landing"]
    new = g.query(case_from_text("X", "Ogłoszenie o otwarciu wystawy sztuki nowoczesnej w galerii miejskiej w sobotę o godzinie osiemnastej"))
    assert new.verdict == "nowy_wzorzec"


def test_add_is_idempotent_and_assigns_ids():
    g = build()
    n = len(g)
    d = g.add(mat("A", 0, 100))               # ten sam id
    assert len(g) == n and d.duplicate_of == "A0"
    d2 = g.add(case_from_text("Y", "Zupełnie inny tekst o kotach i psach oraz ich opiekunach w schronisku miejskim"))
    assert len(g) == n + 1 and d2.verdict == "nowy_wzorzec" and d2.group not in {it["group"] for it in g.items[:n]}


def test_late_add_does_not_refit_and_save_load_roundtrip(tmp_path):
    g = build()
    g.add(mat("A", 5, 1))                     # mała galeria: pełne dopasowanie przy każdym dodaniu
    assert g._fit_n == len(g)
    g.refit_below, g.min_refit = 0, 1000      # od teraz późne dodawanie
    fit_n = g._fit_n
    g.add(mat("B", 7, 555))
    assert g._fit_n == fit_n and len(g) == fit_n + 1
    path = tmp_path / "g.jsonl"
    g.save(path)
    g2 = Gallery.load(path, cfg(), embed_fn=fake_embed)
    assert len(g2) == len(g) and g2._counter["K"] >= 1
    q = mat("C", 8, 321)
    assert g.query(q).verdict == g2.query(q).verdict == "znana_kampania"


def test_meta_ad_adapter_flagged_and_extra_evidence():
    r = {"id": "1", "page_id": "99", "ad_creative_bodies": ["Kup teraz suplement"], "ad_creative_link_titles": ["Promocja"],
         "ad_creative_link_captions": ["sklep-zdrowie.pl"], "beneficiary_payers": [{"payer": "Firma X"}]}
    c = case_from_meta_ad(r)
    assert c.text.startswith("Promocja") and c.sets["host"] == {"sklep-zdrowie.pl"} and c.sets["payer"] == {"Firma X"}
    flagged = case_from_meta_ad({"id": "2", "page_id": "99", "ad_creative_bodies": ["This ad was removed because it didn't follow"]})
    assert flagged.text == "" and flagged.meta["flagged_by_meta"] and "host" not in flagged.sets
    # kanały spoza wyniku trafiają do extra_shared, a nie do wyniku
    g = Gallery(cfg(), embed_fn=fake_embed)
    g.add(c)
    other = case_from_meta_ad({**r, "id": "3", "ad_creative_bodies": ["Zupełnie inny tekst reklamy"], "ad_creative_link_titles": ["Coś innego"]})
    d = g.query(other)
    assert d.matches[0].extra_shared.get("payer") == ["Firma X"] and "payer" not in d.matches[0].channels


def test_dict_roundtrip():
    c = mat("A", 1, 5)
    assert case_from_dict(case_to_dict(c)).sets == c.sets


def test_explain_is_readable_polish_with_evidence():
    g = build()
    d = g.query(mat("A", 9, 777))
    txt = d.explain()
    assert "Znana kampania" in txt and "Najbliższy materiał: A" in txt and "/kita/landing" in txt
    new = g.query(case_from_text("X", "Ogłoszenie o otwarciu wystawy sztuki nowoczesnej w galerii miejskiej w sobotę o osiemnastej"))
    assert new.explain().startswith("Nowy wzorzec")


def test_frozen_config_loads_from_tracked_dir_in_clean_clone(tmp_path, monkeypatch):
    """Czysty klon nie ma artifacts/: Gallery('adj') i CLI muszą działać z konfiguracji śledzonej w repo."""
    from embsim import bench

    monkeypatch.setattr(bench, "ART", tmp_path)               # brak lokalnych plików
    for name in ("adj", "lex", "v3_mixed_pca"):
        cfg, fr = bench.load_frozen(name)
        assert cfg.thresholds["campaign"] > 0 and fr["fingerprint"]
    assert bench.load_frozen("adj")[0].adjust_levels == ["campaign"]
    from embsim.api import DEFAULT_CONFIG
    d = bench.load_frozen(DEFAULT_CONFIG)[0]
    assert d.embed_fix == "abtt1" and d.trace_mode == "overlap" and d.trace_mode_operator == "contain"


def test_operator_requires_rare_shared_trace_when_op_rare_df_set():
    def gal(rare):
        c = cfg(); c.op_rare_df = rare
        g = Gallery(c, embed_fn=fake_embed)
        for i in range(9):                                    # pospolity ślad w 3 z 9 materiałów, reszta ma własne
            g.add(case_from_text(f"P{i}", f"Zupełnie różny tekst numer {i} o ogrodach i pogodzie w regionie {i * 7}",
                                 kit={"/static/app"} if i < 3 else {f"/own{i}/x"}))
        return g
    probe = case_from_text("Q", "Inna treść o samochodach i naprawie silników diesla", kit={"/static/app"})
    assert gal(None).query(probe).verdict == "znany_operator_nowa_kampania"   # bez reguły pospolity ślad skleja
    assert gal(2).query(probe).verdict == "nowy_wzorzec"                       # z regułą: ślad w 3 materiałach nie dowodzi operatora


# --- poprawki z audytu backendu ------------------------------------------------------------------------------------------

def test_many_copies_of_same_text_do_not_zero_the_semantic_channel():
    g = Gallery(cfg(), embed_fn=fake_embed)
    text = CAMP["A"].format(n=1)
    for k in range(10):
        d = g.add(case_from_text(f"copy{k}", text))
    assert d.verdict == "znana_kampania" and d.campaign_score > 0.9               # 10. kopia nie otwiera nowej kampanii
    assert len({it["group"] for it in g.items}) == 1


def test_first_trace_of_new_kind_after_refit_threshold_does_not_crash():
    g = Gallery(cfg(), embed_fn=fake_embed, refit_below=5)
    for i in range(8):
        g.add(case_from_text(f"h{i}", f"różny tekst numer {i} o ogrodzie", host={f"h{i}.example"}))
    g.add(case_from_text("img1", "tekst z obrazem", img={"abc123abc123abc1"}))
    d = g.query(case_from_text("q", "pytanie o obraz", img={"abc123abc123abc1"}))     # wcześniej KeyError: 'img'
    assert d.matches


def test_metadata_only_record_creates_no_group_and_exact_rule_needs_more_than_one_image():
    g = Gallery(cfg(), embed_fn=fake_embed)
    empty = case_from_text("m1", "", page={"123"})
    d = g.add(empty)
    assert d.verdict == "brak_danych" and len(g) == 0 and "Brak danych" in d.explain()
    g.add(case_from_text("a", "Oferta pierwsza o ogrodach", img={"logo0123456789ab"}, kit={"/a/b"}))
    other = case_from_text("b", "Zupełnie inna strona o samochodach i serwisie", img={"logo0123456789ab"}, kit={"/c/d"})
    assert g.query(other).exact_of is None                                            # jedno wspólne logo nie wymusza kampanii


def test_registered_domain_handles_multi_part_suffix_and_ip():
    from embsim.features import registered

    assert registered("shop.firma.com.pl") == "firma.com.pl" and registered("a.com.pl") == "a.com.pl"
    assert registered("www.bbc.co.uk") == "bbc.co.uk" and registered("sub.example.com") == "example.com"
    assert registered("203.0.113.7") == "203.0.113.7"


def test_decision_is_same_before_and_after_restart_with_late_added_materials(tmp_path):
    g = Gallery(cfg(), embed_fn=fake_embed, refit_below=3, refit_fraction=10.0)       # po 3 materiałach tylko późne dodawanie
    for i in range(3):
        g.add(case_from_text(f"s{i}", f"Osobna treść numer {i} o ogrodach", host={f"s{i}.example"}))
    for i in range(4):
        g.add(case_from_text(f"late{i}", f"Całkiem inna treść {i} o samochodach i serwisie", host={"wspolny.example"}))
    q = case_from_text("q", "Nowa treść o czymś jeszcze innym", host={"wspolny.example"})
    before = g.query(q)
    g.save(tmp_path / "g.jsonl")
    after = Gallery.load(tmp_path / "g.jsonl", embed_fn=fake_embed).query(q)
    assert before.verdict == after.verdict


def test_profiles_give_same_thresholds_everywhere_and_are_recorded_in_decision():
    from embsim.api import META_CAMPAIGN_THRESHOLD

    gm, gs = Gallery(embed_fn=fake_embed, profile="meta"), Gallery(embed_fn=fake_embed, profile="strony")
    assert gm.cfg.thresholds["campaign"] == META_CAMPAIGN_THRESHOLD and gs.cfg.thresholds["campaign"] == 0.62
    gm.add(case_from_text("a", "Pierwsza oferta numer jeden o ogrodach"))
    assert gm.query(case_from_text("q", "Pierwsza oferta numer jeden o ogrodach")).profile == "meta"
    assert Gallery(embed_fn=fake_embed, profile="meta", thresholds={"campaign": 0.9}).cfg.thresholds["campaign"] == 0.9   # jawny próg wygrywa


def test_close_second_campaign_is_flagged_as_ambiguous():
    g = build()                                                                         # tło: 3 kampanie po 3 warianty
    base = "Rafał Brzoska ujawnia platforma zarobki wpłać zł obserwuj zysk już dziś zostało tylko miejsc"
    g.add(case_from_text("k1", base + " alfa", kit={"/k/one"}), group="K1", operator="O1")
    g.add(case_from_text("k2", base + " beta", kit={"/k/two"}), group="K2", operator="O2")
    d = g.query(case_from_text("q", base + " gamma"))
    assert d.verdict == "znana_kampania" and d.alternative and d.alternative[0] in ("K1", "K2")
    assert "niejednoznaczne" in d.explain()


def test_matches_have_no_duplicate_ids():
    from embsim.api import Gallery, Case
    g = Gallery()
    g.add(Case(id="a", text="Szokujące: prezes zdradził sposób na zysk. Wpłać 500 zł i obserwuj."))
    d = g.add(Case(id="b", text="Szokujące: prezes zdradził sposób na zysk. Wpłać 700 zł i obserwuj."))
    ids = [m.id for m in d.matches]
    assert len(ids) == len(set(ids))
