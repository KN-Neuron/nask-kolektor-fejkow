"""Explainable domain-domain links from passive infrastructure evidence.

Each rule contributes (code, weight, human-readable reason); weights are combined with noisy-OR, so independent weak signals add up
but a single weak one (e.g. a shared Cloudflare IP) cannot create a link on its own. Every edge carries its reasons.
"""
from __future__ import annotations

import re
from datetime import datetime
from itertools import combinations

from pydantic import BaseModel

from .collect import GENERIC_PARAMS, InfraRecord, registered_domain

DEFAULTS = {
    "min_score": 0.5,
    "shared_ip": 0.9, "shared_ip_cdn": 0.15,
    "shared_ns_provider": 0.45, "shared_ns_provider_mass": 0.05,
    "same_registrar": 0.15, "same_ns_set": 0.7, "same_ns_set_mass": 0.4, "same_subnet24": 0.35,
    "created_within_1h": 0.8, "created_within_24h": 0.4, "created_within_3d": 0.2, "created_within_14d": 0.08,
    "same_cert": 0.9, "same_issuer_day": 0.35,
    "same_path_template": 0.5, "shared_tracker_params": 0.2, "same_platform_hint": 0.4,
    "same_registrant_country": 0.08, "random_names": 0.08,
    "cdn_asns": ["13335", "54113", "20940", "16509", "14618", "15169", "8075", "209242", "132892"],
    "mass_ns_providers": ["cloudflare.com", "awsdns-", "googledomains.com", "domaincontrol.com", "registrar-servers.com"],
}


class Evidence(BaseModel):
    code: str
    weight: float
    reason: str


class Link(BaseModel):
    src: str
    dst: str
    score: float
    evidence: list[Evidence]


def _dt(s: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None
    except ValueError:
        return None


def _registrar(name: str | None) -> str | None:
    if not name:
        return None
    n = re.sub(r"[^a-z0-9 ]", " ", name.lower())
    n = re.sub(r"\b(inc|llc|ltd|co|corp|corporation|limited|group|international|technology|d b a)\b", " ", n)
    return " ".join(n.split()[:2]) or None


def _ns_providers(r: InfraRecord) -> set[str]:
    return {registered_domain(n) for n in r.ns}


def evidence(a: InfraRecord, b: InfraRecord, cfg: dict | None = None) -> list[Evidence]:
    c = {**DEFAULTS, **(cfg or {})}
    ev: list[Evidence] = []
    cdn = set(c["cdn_asns"])
    for ip in sorted(set(a.a) & set(b.a)):
        asn = next((x for x in (a.asn.get(ip), b.asn.get(ip)) if x and x.asn), None)  # either record may have missed the lookup
        is_cdn = bool(asn and asn.asn in cdn)
        label = f"AS{asn.asn}" + (f" {asn.org}" if asn.org else "") if asn else "ASN nieznany"
        ev.append(Evidence(code="shared_ip_cdn" if is_cdn else "shared_ip", weight=c["shared_ip_cdn" if is_cdn else "shared_ip"],
                           reason=f"wspólny adres IP {ip} ({label})" + (": adres CDN współdzielony przez miliony stron, dowód słaby" if is_cdn else "")))
    for p in sorted(_ns_providers(a) & _ns_providers(b)):
        mass = any(m in p for m in c["mass_ns_providers"])
        ev.append(Evidence(code="shared_ns_provider", weight=c["shared_ns_provider_mass" if mass else "shared_ns_provider"],
                           reason=f"ten sam dostawca DNS {p}" + (" (masowy, słaby dowód)" if mass else "")))
    ra, rb = a.rdap, b.rdap
    if _registrar(ra.registrar) and _registrar(ra.registrar) == _registrar(rb.registrar):
        ev.append(Evidence(code="same_registrar", weight=c["same_registrar"], reason=f"ten sam rejestrator: {ra.registrar}"))
    if a.ns and set(a.ns) == set(b.ns):
        mass = any(m in p for p in _ns_providers(a) for m in c["mass_ns_providers"])
        ev.append(Evidence(code="same_ns_set", weight=c["same_ns_set_mass" if mass else "same_ns_set"],
                           reason=f"identyczny zestaw serwerów nazw ({', '.join(sorted(a.ns)[:2])}...)"
                                  + (": na Cloudflare para nazw jest przypisana do konta, ale pula jest skończona" if mass else "")))
    nets = {".".join(ip.split(".")[:3]) for ip in a.a if ":" not in ip} & {".".join(ip.split(".")[:3]) for ip in b.a if ":" not in ip}
    if nets and not set(a.a) & set(b.a):
        asn = next((x for ip in a.a for x in [a.asn.get(ip)] if x and x.asn), None)
        if not (asn and asn.asn in cdn):
            ev.append(Evidence(code="same_subnet24", weight=c["same_subnet24"], reason=f"sąsiednie adresy IP w podsieci {sorted(nets)[0]}.0/24"))
    da, db = _dt(ra.created), _dt(rb.created)
    if da and db:
        sec = abs((da - db).total_seconds())
        for code, lim, txt in (("created_within_1h", 3600, "masowa rejestracja"), ("created_within_24h", 86400, "rejestracja w tej samej dobie"),
                               ("created_within_3d", 3 * 86400, ""), ("created_within_14d", 14 * 86400, "")):
            if sec <= lim:
                ev.append(Evidence(code=code, weight=c[code], reason=f"domeny zarejestrowane w odstępie {int(sec // 60)} min" if sec < 86400 * 2 else f"domeny zarejestrowane w odstępie {int(sec // 86400)} dni"))
                break
    if ra.registrant_country and ra.registrant_country == rb.registrant_country:
        ev.append(Evidence(code="same_registrant_country", weight=c["same_registrant_country"], reason=f"ten sam kraj rejestranta: {ra.registrant_country}"))
    sa = {ce.serial for ce in a.certs if ce.serial}
    sb = {ce.serial for ce in b.certs if ce.serial}
    if sa & sb:
        ev.append(Evidence(code="same_cert", weight=c["same_cert"], reason="ten sam certyfikat TLS w dzienniku CT"))
    else:
        days_a = {(ce.issuer, (ce.not_before or "")[:10]) for ce in a.certs}
        days_b = {(ce.issuer, (ce.not_before or "")[:10]) for ce in b.certs}
        common = {x for x in days_a & days_b if x[1]}
        if common:
            iss, day = sorted(common)[0]
            ev.append(Evidence(code="same_issuer_day", weight=c["same_issuer_day"], reason=f"certyfikaty tego samego wystawcy tego samego dnia ({day})"))
    ta = {u.path_template for u in a.urls if u.path_template not in ("/", "")}
    tb = {u.path_template for u in b.urls if u.path_template not in ("/", "")}
    if ta & tb:
        ev.append(Evidence(code="same_path_template", weight=c["same_path_template"],
                           reason=f"ten sam wzorzec adresu w reklamie: {sorted(ta & tb)[0]} (typowy dla sklepów-szablonów, nie dowód sam w sobie)"))
    pa = {p for u in a.urls for p in u.params} - GENERIC_PARAMS
    pb = {p for u in b.urls for p in u.params} - GENERIC_PARAMS
    if len(pa & pb) >= 2:
        ev.append(Evidence(code="shared_tracker_params", weight=c["shared_tracker_params"],
                           reason=f"wspólne parametry śledzące w adresie reklamy: {', '.join(sorted(pa & pb))}"))
    ha = {(k, v) for u in a.urls for k, v in u.hints.items()}
    hb = {(k, v) for u in b.urls for k, v in u.hints.items()}
    if ha & hb:
        k, v = sorted(ha & hb)[0]
        ev.append(Evidence(code="same_platform_hint", weight=c["same_platform_hint"], reason=f"ta sama platforma w adresie: {k}={v}"))
    if min(a.name_vowel_ratio, b.name_vowel_ratio) < 0.25 and min(a.name_entropy, b.name_entropy) > 2.0:
        ev.append(Evidence(code="random_names", weight=c["random_names"], reason="obie nazwy wyglądają na losowe (mało samogłosek, wysoka entropia)"))
    return ev


def score(ev: list[Evidence]) -> float:
    p = 1.0
    for e in ev:
        p *= 1 - e.weight
    return round(1 - p, 3)


def link(records: list[InfraRecord], cfg: dict | None = None, min_score: float | None = None) -> list[Link]:
    thr = min_score if min_score is not None else {**DEFAULTS, **(cfg or {})}["min_score"]
    out = []
    for a, b in combinations(records, 2):
        ev = evidence(a, b, cfg)
        s = score(ev)
        if ev and s >= thr:
            out.append(Link(src=a.domain, dst=b.domain, score=s, evidence=sorted(ev, key=lambda e: -e.weight)))
    return sorted(out, key=lambda x: -x.score)


def graph_edges(links: list[Link]) -> list[dict]:
    """Edges in the format expected by analyze.graph.build_graph(infra_edges=...)."""
    return [{"src": f"d:{li.src}", "dst": f"d:{li.dst}", "weight": li.score, "etype": "infra-domain",
             "reason": "; ".join(e.reason for e in li.evidence)} for li in links]
