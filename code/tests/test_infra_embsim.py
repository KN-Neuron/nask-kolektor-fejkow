"""Kanał `infra` (embsim/infra.py): ślady z metadanych domen, bez sieci (rekordy podstawione w pamięci podręcznej)."""
import pytest

from embsim import analyze as A
from embsim import infra as I
from embsim.api import Gallery, demo_thresholds
from embsim.features import Case

REC_A = {"a": ["104.21.1.1", "5.6.7.8"], "asn": {"104.21.1.1": "13335", "5.6.7.8": "64500"},
         "ns": ["Liz.ns.cloudflare.com.", "shane.ns.cloudflare.com"], "mx": ["aspmx.l.google.com"],
         "registrar": "Dynadot Inc", "created": "2026-10-08T18:18:20Z"}
REC_B = {"a": [], "asn": {}, "ns": ["ns1.dyna-ns.net", "ns1.prywatny-dns.xyz"], "mx": ["mail.prywatny-dns.xyz"],
         "registrar": "Dynadot Inc", "created": "2026-10-08T18:20:08Z"}


@pytest.fixture
def cache(monkeypatch, tmp_path):
    monkeypatch.setattr(I, "CACHE_FILE", tmp_path / "infra.json")
    monkeypatch.setattr(I, "_CACHE", {"civic.live": REC_A, "across.live": REC_B})
    monkeypatch.setattr(I, "_MEM", {})
    monkeypatch.setenv("EMBSIM_INFRA", "cache")


def test_traces_skip_big_providers():
    t = I.traces(REC_A)
    assert "cf:liz+shane" in t                         # para NS Cloudflare = konto
    assert "ip:5.6.7.8" in t and "ip:104.21.1.1" not in t   # adres w sieci Cloudflare to serwer brzegowy
    assert not any(x.startswith(("ns:", "mx:")) for x in t)  # cloudflare.com i google.com pomijane
    assert "rej:Dynadot Inc|2026-10-08T18" in t
    tb = I.traces(REC_B)
    assert "ns:prywatny-dns.xyz" in tb and "mx:prywatny-dns.xyz" in tb and "ns:dyna-ns.net" not in tb


def test_enrich_from_cache_and_modes(cache, monkeypatch):
    c = I.enrich(Case("x", sets={"host": {"civic.live", "netlify.app", "google.com"}}))
    assert "cf:liz+shane" in c.sets["infra"] and set(c.meta["infra"]) == {"civic.live"}   # platformy i pospolite usługi pominięte
    assert "infra" not in I.enrich(Case("y", sets={"host": {"nieznana.live"}})).sets   # brak w pliku, bez sieci: brak kanału
    monkeypatch.setenv("EMBSIM_INFRA", "off")
    assert "infra" not in I.enrich(Case("z", sets={"host": {"civic.live"}})).sets


def test_net_mode_refetches_errors_and_saves(cache, monkeypatch):
    I._CACHE["zla.live"] = {"errors": ["rdap: HTTPStatusError"]}
    monkeypatch.setattr(I, "collect", lambda d, resolver=None, get=None, **kw: {**REC_B, "errors": []})
    assert I.lookup("zla.live", net=False) == {"errors": ["rdap: HTTPStatusError"]}
    assert I.lookup("zla.live", net=True)["registrar"] == "Dynadot Inc"
    assert "zla.live" in I.CACHE_FILE.read_text()


def test_describe_is_readable():
    assert I.describe("rej:Dynadot Inc|2026-10-08T18") == "rejestracja domeny: Dynadot Inc, 2026-10-08 ok. 18:00 UTC"
    assert "to samo konto" in I.describe("cf:liz+shane")


def test_gallery_links_different_domains_by_registration(cache):
    """Dwie strony na różnych domenach z tej samej partii rejestracji: wspólny ślad `infra` w dopasowaniu i w przesłankach."""
    g = Gallery(embed_fn=A.hash_embed, thresholds=demo_thresholds())
    a = I.enrich(Case("a", text="Prezes banku zdradził sposób na zysk", sets={"host": {"civic.live"}, "kit": {"/aio/sdk"}}))
    g.add(a)
    g.add(Case("n", text="Przepis na sernik z rodzynkami", sets={"host": {"inna.pl"}}))
    b = I.enrich(Case("b", text="Prezes banku zdradził sposób na zysk", sets={"host": {"across.live"}, "kit": {"/aio/sdk"}}))
    m = next(m for m in g.query(b).matches if m.id == "a")
    assert m.shared.get("infra") == ["rej:Dynadot Inc|2026-10-08T18"] and m.channels["infra"] > 0
    assert any("rejestracja domeny: Dynadot Inc" in r for r in A.top_reasons(m, 6))


def test_auto_mode_fetches_new_domain_in_memory_only(cache, monkeypatch):
    """Tryb domyślny `auto`: domena spoza pliku (np. nowy materiał jury) pobrana szybko z sieci, bez zapisu pliku w repozytorium."""
    calls = []
    monkeypatch.setenv("EMBSIM_INFRA", "auto")
    monkeypatch.setattr(I, "_net_up", lambda: True)
    monkeypatch.setattr(I, "collect", lambda d, resolver=None, get=None, **kw: calls.append((d, kw)) or {**REC_B, "errors": []})
    c = I.enrich(Case("n", sets={"host": {"nowa-domena.xyz"}}))
    assert "ns:prywatny-dns.xyz" in c.sets["infra"] and calls == [("nowa-domena.xyz", {})]   # bez crt.sh w trybie auto
    assert not I.CACHE_FILE.exists()
    I.enrich(Case("n2", sets={"host": {"nowa-domena.xyz"}}))
    assert len(calls) == 1                                     # drugi raz z pamięci


def test_auto_mode_offline_breaker(cache, monkeypatch):
    monkeypatch.setenv("EMBSIM_INFRA", "auto")
    monkeypatch.setattr(I, "_net_up", lambda: False)
    monkeypatch.setattr(I, "collect", lambda *a, **k: (_ for _ in ()).throw(AssertionError("sieć mimo bezpiecznika")))
    assert "infra" not in I.enrich(Case("n", sets={"host": {"nowa-domena.xyz"}})).sets
    with I.forced("cache"):
        assert I.mode() == "cache"
    assert I.mode() == "auto"


def test_shared_certificate_and_domain_age():
    rec = {**REC_B, "certs": [["across.live", "www.across.live", "civic.live"], ["across.live"]]}
    assert "cert:across.live+civic.live" in I.traces(rec)
    assert "wspólny certyfikat" in I.describe("cert:across.live+civic.live")
    from datetime import datetime, timezone
    assert I.age_days("2026-10-08T18:18:20Z", datetime(2026, 10, 22, tzinfo=timezone.utc)) == 13
    c = Case("x", meta={"infra": {"civic.live": {"created": "2026-10-08T18:18:20Z", "registrar": "Dynadot Inc", "wiek_dni": 13}}})
    assert I.summary(c) == ["civic.live: zarejestrowana 2026-10-08, 13 dni przed analizą, świeża domena, rejestrator Dynadot Inc"]


def test_no_double_counting_with_shared_domain(cache):
    """Ślady infra wyłącznie z domeny, którą oba materiały już dzielą (kanał host), nie liczą się drugi raz."""
    from embsim.score import Corpus
    I._CACHE["wspolna.live"] = REC_B
    a = I.enrich(Case("a", text="x", sets={"host": {"wspolna.live", "civic.live"}}))
    b = I.enrich(Case("b", text="y", sets={"host": {"wspolna.live"}}))
    c = I.enrich(Case("c", text="z", sets={"host": {"across.live"}}))   # ten sam rekord, ale INNA domena: ślad liczony
    corp = Corpus([a, b, c, Case("d", text="w", sets={"host": {"inna.pl"}})], None, {"infra": 1.0, "host": 1.0})
    assert corp.channel(a, b, "infra")[0] is None
    assert corp.channel(b, c, "infra")[0] > 0
