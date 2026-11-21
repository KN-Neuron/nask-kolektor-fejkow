import numpy as np

from fejki.analyze.replay import replay
from fejki.config import load_config
from fejki.embed.encoder import encode_tfidf
from fejki.embed.erase import apply_leace, fit_leace, rule_label
from fejki.embed.probes import probe
from fejki.ingest.cert import parse_cert
from fejki.process.pipeline import enrich
from fejki.synth.campaigns import generate_all

KW = dict(n_campaigns=6, dev_fraction=0.5, variants=(15, 25), n_background=300, n_controls=40)


def _ads(seed=1):
    cfg = load_config()
    _, camp, controls, bg, cert = generate_all(seed, **KW)
    return cfg, [enrich(a, cfg) for a in bg + camp + controls], cert


def test_generator_deterministic():
    _, c1, k1, b1, _ = generate_all(5, **KW)
    _, c2, k2, b2, _ = generate_all(5, **KW)
    assert [a.model_dump_json() for a in c1 + k1 + b1] == [a.model_dump_json() for a in c2 + k2 + b2]
    _, c3, *_ = generate_all(6, **KW)
    assert [a.body for a in c1] != [a.body for a in c3]


def test_synthetic_safety_reserved_tlds_only():
    _, ads, _ = _ads()
    for a in ads:
        assert all(d.endswith(".example") for d in a.domains)
        assert all(x.value.startswith(("t.me/test_", "wa.me/", "bit.ly")) or x.kind in ("phone", "url") for x in a.artifacts)


def test_leace_probe_near_chance_on_fit():
    cfg, ads, _ = _ads()
    X = encode_tfidf([a.text_norm for a in ads], dim=64)
    fit = [i for i, a in enumerate(ads) if a.source == "synthetic_background" and a.meta["split"] == "fit"]
    labs = [rule_label(ads[i].text_norm) for i in fit]
    er, rank = fit_leace(X[fit], labs)
    assert 1 <= rank <= len(set(labs)) - 1
    groups = [str(i) for i in fit]
    before = probe(X[fit], labs, groups)["acc"]
    after = probe(apply_leace(er, X)[fit], labs, groups)["acc"]
    chance = probe(X[fit], labs, groups)["chance"]
    assert before > 0.8 and after < chance + 0.1


def test_cert_parser_tolerant():
    raw = {"meta": 1, "entries": [{"DomainName": "Bad.Example", "InsertDate": "2026-01-02", "DeleteDate": None},
                                  {"domain": "no-dates.example"}, {"other": 1}]}
    got = parse_cert(raw)
    assert [g["domain"] for g in got] == ["bad.example", "no-dates.example"]
    assert got[0]["insert_date"].year == 2026 and got[1]["insert_date"] is None
    assert parse_cert([]) == []


def test_replay_detects_injected_campaign():
    cfg, ads, _ = _ads()
    cfg = load_config(overrides={"bursts.n_regions": 4})
    X = encode_tfidf([a.text_norm for a in ads], dim=64)
    tracks, log, bursts, _ = replay(ads, X, 0.4, cfg, cert=None)
    assert len(log) > 30 and set(bursts.columns) >= {"region", "day", "p", "burst"}
    assert isinstance(tracks, list)
    assert np.all(bursts.p.between(0, 1))
