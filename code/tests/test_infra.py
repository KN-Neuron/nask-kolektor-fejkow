from datetime import UTC, datetime

import numpy as np

from fejki.analyze.graph import build_graph
from fejki.config import load_config
from fejki.infra import collect as C
from fejki.infra.link import evidence, graph_edges, link, score
from fejki.schema import Ad


class Rr:  # minimal dnspython-like answer
    def __init__(self, v, txt=False):
        self.strings, self.exchange, self._v = [v.encode()], v, v

    def __str__(self):
        return self._v


class FakeResolver:
    def __init__(self, table):
        self.t = table

    def resolve(self, name, rtype):
        v = self.t.get((name, rtype))
        if not v:
            raise KeyError(name)
        return [Rr(x) for x in v]


class Resp:
    def __init__(self, j):
        self._j = j

    def raise_for_status(self):
        pass

    def json(self):
        return self._j


def rdap(created, registrar="Reg A"):
    return {"events": [{"eventAction": "registration", "eventDate": created}], "status": ["ok"],
            "entities": [{"roles": ["registrar"], "vcardArray": ["vcard", [["fn", {}, "text", registrar]]]}],
            "nameservers": [{"ldhName": "NS1.EXAMPLE-DNS.NET"}]}


def make(domain, ip, created, url, registrar="Reg A", asn="64500", ns="ns1.x.net."):
    C._ASN_CACHE.clear()
    res = FakeResolver({(domain, "A"): [ip], (domain, "NS"): [ns],
                        (".".join(reversed(ip.split("."))) + ".origin.asn.cymru.com", "TXT"): [f"{asn} | 1.2.3.0/24 | US | arin | 2014-01-01"],
                        (f"AS{asn}.asn.cymru.com", "TXT"): [f"{asn} | US | arin | 2010-01-01 | ORG-{asn}, US"]})
    get = lambda u: Resp(rdap(created, registrar)) if "rdap" in u else Resp([])  # noqa: E731
    return C.collect(domain, [url], resolver=res, get=get)


def test_url_shape_and_names():
    u = C.url_shape("https://a.example/products/16075898962619453130670325?gclid=1&utm_origin=Shopline&adset_id=2")
    assert u.path_template == "/products/<N>" and u.hints == {"utm_origin": "shopline"} and "adset_id" in u.params
    ent, vow = C.name_features("tlbjyhce.com")
    assert vow < 0.3 and ent > 2.5


def test_collect_parses_dns_asn_rdap():
    r = make("a.com", "5.5.5.5", "2026-01-01T00:00:00Z", "https://a.com/x", asn="13335")
    assert r.a == ["5.5.5.5"] and r.asn["5.5.5.5"].asn == "13335" and "ORG-13335" in r.asn["5.5.5.5"].org
    assert r.rdap.registrar == "Reg A" and r.rdap.created.startswith("2026-01-01")


def test_cdn_ip_alone_is_not_a_link():
    a = make("a.com", "104.17.1.1", "2024-01-01T00:00:00Z", "https://a.com/", asn="13335")
    b = make("b.com", "104.17.1.1", "2026-06-01T00:00:00Z", "https://b.com/", registrar="Reg B", asn="13335", ns="ns9.y.org.")
    ev = evidence(a, b)
    assert [e.code for e in ev] == ["shared_ip_cdn"] and score(ev) < 0.5 and link([a, b]) == []


def test_dedicated_ip_links_and_has_reasons():
    a = make("a.com", "9.9.9.9", "2026-06-01T00:00:00Z", "https://a.com/")
    b = make("b.com", "9.9.9.9", "2026-06-05T00:00:00Z", "https://b.com/")
    ls = link([a, b])
    assert len(ls) == 1 and ls[0].score > 0.9
    codes = {e.code for e in ls[0].evidence}
    assert {"shared_ip", "created_within_14d", "same_registrar"} <= codes
    ge = graph_edges(ls)
    assert ge[0]["src"] == "d:a.com" and ge[0]["etype"] == "infra-domain" and "wspólny adres IP" in ge[0]["reason"]


def test_graph_accepts_infra_edges():
    cfg = load_config()
    now = datetime.now(UTC)
    ads = [Ad(ad_id="1", source="file", first_seen_at=now, body="x", domains=["a.com"]),
           Ad(ad_id="2", source="file", first_seen_at=now, body="y", domains=["b.com"])]
    X = np.eye(2, dtype=np.float32)
    G, edges = build_graph(ads, X, np.array([0, 1]), cfg, use_hash=False, use_content=False,
                           infra_edges=[{"src": "d:a.com", "dst": "d:b.com", "weight": 0.9, "etype": "infra-domain", "reason": "t"}])
    assert any(e["etype"] == "infra-domain" for e in edges)
    d = {v["name"]: v.index for v in G.vs}
    assert G.are_adjacent(d["d:a.com"], d["d:b.com"])
