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
    for name in ("adj", "lex"):
        cfg, fr = bench.load_frozen(name)
        assert cfg.thresholds["campaign"] > 0 and fr["fingerprint"]
    assert bench.load_frozen("adj")[0].adjust_levels == ["campaign"]
