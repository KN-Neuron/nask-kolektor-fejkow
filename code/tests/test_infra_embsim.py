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
    monkeypatch.delenv("EMBSIM_INFRA", raising=False)


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
    monkeypatch.setattr(I, "collect", lambda d, resolver=None, get=None: {**REC_B, "errors": []})
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
