"""Ślady infrastruktury z publicznych metadanych domen: DNS (serwery nazw, poczta, adresy IP) i RDAP (rejestrator, data rejestracji).

Kanał `infra` to zbiór śladów jak `host` czy `pixel`, ważony rzadkością w korpusie (score.py). Łączy materiały, które mają RÓŻNE
domeny, ale tę samą obsługę: ten sam prywatny serwer nazw, ten sam adres IP, domeny zarejestrowane w tej samej godzinie u tego samego
rejestratora (typowe dla partii domen jednego operatora), ta sama para serwerów nazw Cloudflare (Cloudflare przydziela ją na konto). Wspólna domena jest już śladem `host`, więc tu jej nie powtarzamy.

Zapytania idą tylko do usług trzecich (resolwery DNS, Team Cymru ASN-over-DNS, rdap.org), nigdy do stron oszustów.

Tryby (zmienna `EMBSIM_INFRA`):
- `cache` (domyślnie): tylko zapisany wynik z pliku CACHE_FILE (dołączony do repozytorium i do obrazu Dockera), bez sieci;
- `1` / `on`: brakujące domeny pobierane z sieci i dopisywane do pliku;
- `0` / `off`: kanał wyłączony.

Pomijamy ślady wielkich dostawców (Cloudflare, AWS, Google, popularne DNS rejestratorów): w dużym korpusie idf sam je wycisza, ale
w małej galerii „ns:cloudflare.com” u dwóch z dziesięciu materiałów wyglądałby na rzadki wspólny ślad.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from .features import COMMON_HOSTS, Case, registered

CACHE_FILE = Path(os.environ.get("EMBSIM_INFRA_CACHE", Path(__file__).resolve().parents[2] / "config" / "embsim" / "infra_cache.json"))
MAX_DOMAINS = 6                    # najwyżej tyle domen na materiał (strona docelowa i jej zasoby; reszta to zwykle trackery)

# Serwery nazw i poczty u wielkich dostawców: obsługują miliony domen, więc wspólny NS/MX niczego nie dowodzi.
COMMON_NS = frozenset((
    "cloudflare.com", "awsdns-00.com", "googledomains.com", "google.com", "azure-dns.com", "azure-dns.net", "azure-dns.org",
    "azure-dns.info", "domaincontrol.com", "registrar-servers.com", "ovh.net", "ovh.ca", "nsone.net", "dnsmadeeasy.com",
    "name-services.com", "hostinger.com", "dns-parking.com", "wixdns.net", "squarespacedns.com", "vercel-dns.com", "netlify.com",
    "digitalocean.com", "linode.com", "hetzner.com", "hetzner.de", "nazwa.pl", "home.pl", "cyberfolks.pl", "lh.pl", "dhosting.pl",
    "zenbox.pl", "hostingers.pl", "ultradns.net", "ultradns.com", "akam.net", "dynect.net", "gandi.net", "namecheaphosting.com",
    "porkbun.com", "dnsowl.com", "afternic.com", "sedoparking.com", "bodis.com", "parkingcrew.net", "above.com", "ns1.com",
    "worldnic.com", "networksolutions.com", "hostgator.com", "bluehost.com", "ionos.com", "ui-dns.com", "ui-dns.de", "ui-dns.org",
    "ui-dns.biz", "websitewelcome.com", "shopify.com", "myshopify.com", "github.com", "tilda.ws", "dyna-ns.net", "bunnydns.com",
    "name.com", "namesilo.com", "dnspod.net", "dnspod.com", "hichina.com", "nicenic.net", "parklogic.com",
))
COMMON_MX = frozenset(("google.com", "googlemail.com", "outlook.com", "protection.outlook.com", "zoho.com", "zoho.eu", "yandex.net",
                       "mailgun.org", "sendgrid.net", "amazonses.com", "icloud.com", "mx.cloudflare.net", "cloudflare.net",
                       "registrar-servers.com", "secureserver.net", "ovh.net", "hostinger.com", "titan.email", "nazwa.pl", "home.pl"))
# Systemy autonomiczne CDN i chmur: ten sam adres IP to tam wspólny serwer brzegowy, nie wspólny operator.
CDN_ASN = frozenset(("13335", "209242", "16509", "14618", "8987", "15169", "396982", "19527", "54113", "20940", "16625", "8075",
                     "8068", "13238", "24940", "16276", "14061", "63949", "20473", "47583", "397273", "46606", "26496"))

# Platformy, na których stoją strony wielu niezależnych osób (subdomeny klientów) albo publiczne API: ich metadane opisują
# platformę, nie operatora.
SERVICE_DOMAINS = frozenset((
    "b-cdn.net", "netlify.app", "vercel.app", "pages.dev", "workers.dev", "github.io", "herokuapp.com", "web.app", "firebaseapp.com",
    "blogspot.com", "wixsite.com", "weebly.com", "wordpress.com", "tilda.ws", "carrd.co", "glitch.me", "onrender.com", "fly.dev",
    "azurewebsites.net", "appspot.com", "r2.dev", "ngrok.io", "ngrok-free.app", "er-api.com", "exchangerate-api.com", "ipapi.co",
    "ipify.org", "ip-api.com", "jsdelivr.net", "cdnjs.com", "bunny.net", "imgur.com", "postimg.cc", "ibb.co",
))
CF_NS = ".ns.cloudflare.com"       # Cloudflare przydziela parę serwerów nazw na konto: ta sama para = to samo konto Cloudflare

_LOCK = threading.Lock()
_CACHE: dict[str, dict] | None = None


def mode() -> str:
    v = os.environ.get("EMBSIM_INFRA", "cache").strip().lower()
    return "off" if v in ("0", "off", "no", "false") else "net" if v in ("1", "on", "yes", "true", "net") else "cache"


def _load() -> dict[str, dict]:
    global _CACHE
    if _CACHE is None:
        try:
            _CACHE = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _CACHE = {}
    return _CACHE


def _save() -> None:
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(_load(), ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    except OSError:                         # np. katalog tylko do odczytu w kontenerze: wynik zostaje w pamięci
        pass


def _get_retry(url: str):
    """GET do RDAP z ponowieniem: rdap.org i rejestry odrzucają serie zapytań (429), co przy kilkunastu domenach zdarza się często."""
    import time

    import httpx

    for i in range(4):
        r = httpx.get(url, timeout=20, follow_redirects=True, headers={"Accept": "application/rdap+json, application/json"})
        if r.status_code not in (429, 500, 502, 503, 504):
            return r
        time.sleep(1.5 * (i + 1))
    return r


def collect(domain: str, resolver=None, get=None) -> dict:
    """Zwięzły rekord domeny: a, ns, mx, asn (ip -> numer), registrar, created. Błędy sieci dają puste pola."""
    from fejki.infra.collect import collect as _collect

    rec = _collect(domain, resolver=resolver, get=get or _get_retry, use_ct=False)
    return {"a": rec.a, "ns": rec.ns, "mx": rec.mx, "asn": {ip: (i.asn or "") for ip, i in rec.asn.items()},
            "registrar": rec.rdap.registrar, "created": rec.rdap.created, "errors": rec.errors}


def lookup(domain: str, net: bool | None = None, resolver=None, get=None) -> dict | None:
    """Rekord domeny z pliku albo (w trybie sieci) świeżo pobrany i zapisany. None, gdy brak danych."""
    net = mode() == "net" if net is None else net
    with _LOCK:
        cache = _load()
        if domain in cache and not (net and cache[domain].get("errors")):     # w trybie sieci rekord z błędem pobieramy ponownie
            return cache[domain]
    if not net:
        return None
    rec = collect(domain, resolver=resolver, get=get)
    with _LOCK:
        _load()[domain] = rec
        _save()
    return rec


def traces(rec: dict) -> set[str]:
    """Ślady z rekordu domeny (bez wielkich dostawców)."""
    out: set[str] = set()
    cf = sorted(n.rstrip(".").lower() for n in rec.get("ns") or () if n.rstrip(".").lower().endswith(CF_NS))
    if len(cf) >= 2:
        out.add("cf:" + "+".join(n[: -len(CF_NS)] for n in cf))
    for ns in rec.get("ns") or ():
        if (r := registered(ns.rstrip(".").lower())) and r not in COMMON_NS and not r.startswith("awsdns-"):
            out.add("ns:" + r)
    for mx in rec.get("mx") or ():
        r = registered(mx.rstrip(".").lower())
        if r and r not in COMMON_MX and r not in COMMON_NS:
            out.add("mx:" + r)
    asn = rec.get("asn") or {}
    for ip in rec.get("a") or ():
        if asn.get(ip) and asn[ip] not in CDN_ASN:        # bez ASN nie wiemy, czy to CDN: pomijamy
            out.add("ip:" + ip)
    if rec.get("registrar") and rec.get("created"):
        out.add(f"rej:{rec['registrar']}|{str(rec['created'])[:13]}")   # ta sama godzina: partia domen, nie zbieg dnia
    return out


def describe(token: str) -> str:
    """Ślad `infra` po polsku (do przesłanek i tabeli śladów klastra)."""
    kind, _, v = token.partition(":")
    if kind == "rej":
        reg, _, when = v.partition("|")
        return f"rejestracja domeny: {reg}, {when[:10]} ok. {when[11:13]}:00 UTC" if len(when) >= 13 else f"rejestracja domeny: {reg}, {when}"
    if kind == "cf":
        return f"ta sama para serwerów nazw Cloudflare ({v.replace('+', ', ')}): to samo konto"
    return {"ns": f"serwer nazw {v}", "mx": f"serwer poczty {v}", "ip": f"adres IP {v}"}.get(kind, token)


def domains_of(case: Case) -> list[str]:
    """Domeny materiału do sprawdzenia: najpierw adres podany wprost, potem pozostałe domeny (bez pospolitych usług)."""
    first = [registered(h) for h in (case.meta.get("landing_hosts") or ())]
    rest = sorted(case.sets.get("host", ()))
    out = [d for d in dict.fromkeys(first + rest) if d and d not in COMMON_HOSTS and d not in SERVICE_DOMAINS and "." in d]
    return out[:MAX_DOMAINS]


def enrich(case: Case, net: bool | None = None, resolver=None, get=None) -> Case:
    """Dopisuje kanał `infra` (i opis rekordów w `meta["infra"]`). Bez danych kanał nie powstaje (brak danych, nie różnica)."""
    if mode() == "off" and net is None:
        return case
    found, recs = set(), {}
    for d in domains_of(case):
        try:
            rec = lookup(d, net=net, resolver=resolver, get=get)
        except Exception:                   # sieć, format odpowiedzi: materiał zostaje bez tego kanału
            rec = None
        if rec:
            recs[d] = {k: rec.get(k) for k in ("ns", "registrar", "created")}
            found |= traces(rec)
    if found:
        case.sets["infra"] = found
    if recs:
        case.meta["infra"] = recs
    return case


def main(argv: list[str] | None = None) -> None:
    """Uzupełnia plik CACHE_FILE dla domen z folderów przypadków: `python -m embsim.infra /ścieżka/do/przypadków`."""
    import argparse

    from .api import case_from_folder

    ap = argparse.ArgumentParser(description=main.__doc__)
    ap.add_argument("root", type=Path)
    a = ap.parse_args(argv)
    os.environ["EMBSIM_FACES"] = "0"
    for d in sorted(p for p in a.root.iterdir() if p.is_dir()):
        c = enrich(case_from_folder(d), net=True)
        print(f"{d.name:30s} {sorted(c.sets.get('infra', ()))}")


if __name__ == "__main__":
    main()
