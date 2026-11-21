"""Passive collection of infrastructure features for a domain.

Only third-party sources are queried (DNS resolvers, Team Cymru ASN-over-DNS, RDAP, crt.sh). The scam sites themselves are never contacted.
"""
from __future__ import annotations

import logging
import math
import re
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlsplit

import tldextract
from pydantic import BaseModel, Field

from ..config import path

log = logging.getLogger(__name__)
_TLD = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)

CLICK_IDS = {"gclid", "fbclid", "ttclid", "msclkid", "gbraid", "wbraid", "gad_source", "gad_campaignid"}
GENERIC_PARAMS = CLICK_IDS | {"utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "utm_id",
                              # makra adresów docelowych Meta Ads: ma je prawie każda reklama z Facebooka, więc nie łączą kampanii
                              "ad_id", "adset_id", "adset_name", "ad_name", "campaign_id", "campaign_name", "placement",
                              "site_source_name", "media_type"}
TRIVIAL_PATHS = {"/", "", "/favicon.ico", "/robots.txt", "/index.html", "/index.php", "/sw.js", "/manifest.json"}


class UrlShape(BaseModel):
    host: str
    path_template: str
    params: list[str] = Field(default_factory=list)
    hints: dict[str, str] = Field(default_factory=dict)


class AsnInfo(BaseModel):
    asn: str | None = None
    country: str | None = None
    org: str | None = None


class Rdap(BaseModel):
    registrar: str | None = None
    created: str | None = None
    updated: str | None = None
    expires: str | None = None
    status: list[str] = Field(default_factory=list)
    nameservers: list[str] = Field(default_factory=list)
    registrant_country: str | None = None


class Cert(BaseModel):
    issuer: str | None = None
    not_before: str | None = None
    serial: str | None = None
    names: list[str] = Field(default_factory=list)


class InfraRecord(BaseModel):
    domain: str
    collected_at: str
    a: list[str] = Field(default_factory=list)
    aaaa: list[str] = Field(default_factory=list)
    ns: list[str] = Field(default_factory=list)
    mx: list[str] = Field(default_factory=list)
    asn: dict[str, AsnInfo] = Field(default_factory=dict)
    rdap: Rdap = Field(default_factory=Rdap)
    certs: list[Cert] = Field(default_factory=list)
    urls: list[UrlShape] = Field(default_factory=list)
    name_entropy: float = 0.0
    name_vowel_ratio: float = 0.0
    errors: list[str] = Field(default_factory=list)


def registered_domain(host: str) -> str:
    ext = _TLD(host.strip().lower().strip("."))
    return f"{ext.domain}.{ext.suffix}" if ext.domain and ext.suffix else host.lower()


def url_shape(url: str) -> UrlShape:
    u = urlsplit(url.strip())
    tmpl = re.sub(r"\d{6,}", "<N>", u.path or "/")
    tmpl = re.sub(r"\b[0-9a-f]{16,}\b", "<H>", tmpl)
    q = parse_qsl(u.query, keep_blank_values=True)
    hints = {k: v.lower() for k, v in q if k == "utm_origin"}
    return UrlShape(host=(u.hostname or "").lower(), path_template=tmpl, params=sorted({k for k, _ in q}), hints=hints)


def name_features(domain: str) -> tuple[float, float]:
    label = _TLD(domain).domain or domain.split(".")[0]
    if not label:
        return 0.0, 0.0
    p = [label.count(c) / len(label) for c in set(label)]
    ent = -sum(x * math.log2(x) for x in p)
    vow = sum(c in "aeiouy" for c in label) / len(label)
    return round(ent, 3), round(vow, 3)


# --- DNS ---------------------------------------------------------------------------------------------------------

def _txt(resolver, name: str) -> list[str]:
    try:
        return [b"".join(r.strings).decode() for r in resolver.resolve(name, "TXT")]
    except Exception:
        return []


def _records(resolver, domain: str, rtype: str) -> list[str]:
    try:
        return sorted(str(r.exchange if rtype == "MX" else r).rstrip(".").lower() for r in resolver.resolve(domain, rtype))
    except Exception:
        return []


_ASN_CACHE: dict[str, AsnInfo] = {}


def asn_lookup(resolver, ip: str, tries: int = 3) -> AsnInfo:
    """Team Cymru IP-to-ASN mapping over DNS (IPv4 only). Retries, because the service drops queries now and then."""
    if ":" in ip:
        return AsnInfo()
    if ip in _ASN_CACHE:
        return _ASN_CACHE[ip]
    rev = ".".join(reversed(ip.split(".")))
    t: list[str] = []
    for _ in range(tries):
        t = _txt(resolver, f"{rev}.origin.asn.cymru.com")
        if t:
            break
    if not t:
        return AsnInfo()
    parts = [x.strip() for x in t[0].split("|")]
    asn, country = parts[0].split()[0], (parts[2] if len(parts) > 2 else None)
    org = None
    for _ in range(tries):
        name = _txt(resolver, f"AS{asn}.asn.cymru.com")
        if name:
            org = name[0].split("|")[-1].strip()
            break
    info = AsnInfo(asn=asn, country=country, org=org)
    _ASN_CACHE[ip] = info
    return info


# --- RDAP / CT -----------------------------------------------------------------------------------------------------

def parse_rdap(j: dict) -> Rdap:
    ev = {e.get("eventAction"): e.get("eventDate") for e in j.get("events", [])}
    registrar = country = None
    for ent in j.get("entities", []):
        roles = ent.get("roles", [])
        vc = (ent.get("vcardArray") or [None, []])[1]
        fn = next((x[3] for x in vc if x and x[0] == "fn"), None)
        if "registrar" in roles and fn:
            registrar = fn
        if "registrant" in roles:
            adr = next((x for x in vc if x and x[0] == "adr"), None)
            if adr and isinstance(adr[3], list) and adr[3]:
                country = adr[3][-1] or None
    return Rdap(registrar=registrar, created=ev.get("registration"), updated=ev.get("last changed"), expires=ev.get("expiration"),
                status=j.get("status", []), nameservers=sorted(n.get("ldhName", "").lower() for n in j.get("nameservers", [])),
                registrant_country=country)


def rdap_lookup(get, domain: str) -> Rdap:
    r = get(f"https://rdap.org/domain/{domain}")
    r.raise_for_status()
    return parse_rdap(r.json())


def crtsh_lookup(get, domain: str, limit: int = 50) -> list[Cert]:
    r = get(f"https://crt.sh/?q={domain}&output=json")
    r.raise_for_status()
    out = {}
    for c in r.json():
        out[c.get("serial_number")] = Cert(issuer=c.get("issuer_name"), not_before=c.get("not_before"), serial=c.get("serial_number"),
                                          names=sorted(set(c.get("name_value", "").lower().split("\n"))))
    return list(out.values())[:limit]


# --- orchestration -------------------------------------------------------------------------------------------------

def _default_resolver():
    import dns.resolver

    r = dns.resolver.Resolver()
    r.lifetime = 6.0
    return r


def _default_get(url: str):
    import httpx

    return httpx.get(url, timeout=30, follow_redirects=True, headers={"Accept": "application/rdap+json, application/json"})


def collect(domain: str, urls: list[str] | None = None, resolver=None, get=None, use_ct: bool = True) -> InfraRecord:
    resolver = resolver or _default_resolver()
    get = get or _default_get
    ent, vow = name_features(domain)
    rec = InfraRecord(domain=domain, collected_at=datetime.now(UTC).isoformat(timespec="seconds"), name_entropy=ent, name_vowel_ratio=vow,
                      urls=[url_shape(u) for u in (urls or [])])
    rec.a, rec.aaaa = _records(resolver, domain, "A"), _records(resolver, domain, "AAAA")
    rec.ns, rec.mx = _records(resolver, domain, "NS"), _records(resolver, domain, "MX")
    rec.asn = {ip: asn_lookup(resolver, ip) for ip in rec.a}
    try:
        rec.rdap = rdap_lookup(get, domain)
        if not rec.ns:
            rec.ns = rec.rdap.nameservers
    except Exception as e:  # network/format: keep going with what we have
        rec.errors.append(f"rdap: {type(e).__name__}")
    if use_ct:
        try:
            rec.certs = crtsh_lookup(get, domain)
        except Exception as e:
            rec.errors.append(f"crtsh: {type(e).__name__}")
    return rec


def cache_path(domain: str):
    return path(f"data/raw/infra/{domain}.json")


def collect_cached(domain: str, urls: list[str] | None = None, refresh: bool = False, **kw) -> InfraRecord:
    p = cache_path(domain)
    if p.exists() and not refresh:
        return InfraRecord.model_validate_json(p.read_text())
    rec = collect(domain, urls, **kw)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(rec.model_dump_json(indent=1))
    return rec


def load_links(text: str) -> dict[str, list[str]]:
    """Extract URLs from a text file and group them by registered domain."""
    out: dict[str, list[str]] = {}
    for m in re.finditer(r"https?://[^\s<>\"']+", text):
        u = m.group(0)
        out.setdefault(registered_domain(urlsplit(u).hostname or ""), []).append(u)
    return out
