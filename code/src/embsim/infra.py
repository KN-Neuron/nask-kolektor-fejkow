"""Ślady infrastruktury z publicznych metadanych domen: DNS (serwery nazw, poczta, adresy IP) i RDAP (rejestrator, data rejestracji).

Kanał `infra` to zbiór śladów jak `host` czy `pixel`, ważony rzadkością w korpusie (score.py). Łączy materiały, które mają RÓŻNE
domeny, ale tę samą obsługę: ten sam prywatny serwer nazw, ten sam adres IP, domeny zarejestrowane w tej samej godzinie u tego samego
rejestratora (typowe dla partii domen jednego operatora), ta sama para serwerów nazw Cloudflare (Cloudflare przydziela ją na konto). Wspólna domena jest już śladem `host`, więc tu jej nie powtarzamy.

Zapytania idą tylko do usług trzecich (resolwery DNS, Team Cymru ASN-over-DNS, rdap.org), nigdy do stron oszustów.

Tryby (zmienna `EMBSIM_INFRA`):
- `auto` (domyślnie): najpierw zapisany plik CACHE_FILE (dołączony do repozytorium i obrazu Dockera); domeny, których tam nie ma (np. nowe
  materiały jury), pytane krótko w sieci: DNS i RDAP, z limitem czasu, równolegle, bez crt.sh. Wynik tylko w pamięci (plik w repozytorium
  się nie zmienia). Bezpiecznik: gdy usługi nie odpowiadają (brak sieci, np. kontener offline), przez 10 minut nie próbujemy ponownie;
- `cache`: tylko plik, bez sieci (testy i test „jak jury”, żeby wynik nie zależał od sieci);
- `1` / `on`: pełne pobranie (DNS, RDAP, certyfikaty z crt.sh) i dopisanie do pliku (`python -m embsim.infra FOLDER`);
- `0` / `off`: kanał wyłączony.

Poza śladami: wiek domeny w chwili analizy (`meta["infra"][domena]["wiek_dni"]`), opisowo („świeża domena”): oszustwa żyją na domenach
sprzed dni lub tygodni. Do wyniku nie wchodzi, bo dwie świeże domeny nie mają przez to wspólnego operatora.

Pomijamy ślady wielkich dostawców (Cloudflare, AWS, Google, popularne DNS rejestratorów): w dużym korpusie idf sam je wycisza, ale
w małej galerii „ns:cloudflare.com” u dwóch z dziesięciu materiałów wyglądałby na rzadki wspólny ślad.
"""
from __future__ import annotations

import contextlib
import json
import os
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
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
_MEM: dict[str, dict] = {}         # tryb auto: rekordy pobrane w tej sesji (bez zapisu do pliku)
_FORCED: str | None = None
_NET_DOWN_UNTIL = 0.0
FRESH_DAYS = 30                    # „świeża domena” w opisie materiału


def mode() -> str:
    if _FORCED:
        return _FORCED
    v = os.environ.get("EMBSIM_INFRA", "auto").strip().lower()
    return ("off" if v in ("0", "off", "no", "false") else "net" if v in ("1", "on", "yes", "true", "net")
            else "cache" if v == "cache" else "auto")


@contextlib.contextmanager
def forced(m: str):
    """Tymczasowo wymuszony tryb (np. `cache` w teście „jak jury”, żeby wynik nie zależał od sieci)."""
    global _FORCED
    old, _FORCED = _FORCED, m
    try:
        yield
    finally:
        _FORCED = old


def _net_up() -> bool:
    """Czy usługi trzecie są osiągalne. Wynik negatywny pamiętany 10 minut (bezpiecznik: offline nie czekamy przy każdej domenie)."""
    global _NET_DOWN_UNTIL
    if time.monotonic() < _NET_DOWN_UNTIL:
        return False
    try:
        socket.create_connection((socket.gethostbyname("rdap.org"), 443), timeout=2).close()
        return True
    except OSError:
        _NET_DOWN_UNTIL = time.monotonic() + 600
        return False


def _quick_resolver():
    import dns.resolver

    r = dns.resolver.Resolver()
    r.lifetime = 3.0
    return r


def _quick_get(url: str):
    import httpx

    return httpx.get(url, timeout=8, follow_redirects=True, headers={"Accept": "application/rdap+json, application/json"})


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


def collect(domain: str, resolver=None, get=None, use_ct: bool = False) -> dict:
    """Zwięzły rekord domeny: a, ns, mx, asn (ip -> numer), registrar, created, certs (nazwy z certyfikatów). Błędy sieci dają puste pola."""
    from fejki.infra.collect import collect as _collect

    rec = _collect(domain, resolver=resolver, get=get or _get_retry, use_ct=use_ct)
    out = {"a": rec.a, "ns": rec.ns, "mx": rec.mx, "asn": {ip: (i.asn or "") for ip, i in rec.asn.items()},
           "registrar": rec.rdap.registrar, "created": rec.rdap.created, "errors": rec.errors}
    if use_ct:
        out["certs"] = [c.names for c in rec.certs][:30]
    return out


def lookup(domain: str, net: bool | None = None, resolver=None, get=None) -> dict | None:
    """Rekord domeny z pliku albo z sieci. None, gdy brak danych.

    `net=True` (tryb `1`): pełne pobranie z crt.sh i zapis do pliku. Tryb `auto` (net=None): szybkie pobranie bez crt.sh, tylko w pamięci."""
    m = mode()
    full = m == "net" if net is None else net
    with _LOCK:
        cache = _load()
        if domain in cache and not (full and cache[domain].get("errors")):    # w trybie sieci rekord z błędem pobieramy ponownie
            return cache[domain]
        if domain in _MEM:
            return _MEM[domain]
    if full:
        rec = collect(domain, resolver=resolver, get=get, use_ct=True)
        with _LOCK:
            _load()[domain] = rec
            _save()
        return rec
    if net is None and m == "auto" and (resolver is not None or _net_up()):
        rec = collect(domain, resolver=resolver or _quick_resolver(), get=get or _quick_get)
        if not (rec.get("a") or rec.get("ns") or rec.get("registrar")):          # nic nie przyszło: zwykle brak sieci albo domeny
            if rec.get("errors"):
                return None
        with _LOCK:
            _MEM[domain] = rec
        return rec
    return None


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
    for names in rec.get("certs") or ():                 # jeden certyfikat na kilka RÓŻNYCH domen: wspólne zamówienie certyfikatu
        regs = sorted({r for n in names if (r := registered(n.lstrip("*.").lower())) and r not in COMMON_HOSTS})
        if 2 <= len(regs) <= 20:
            out.add("cert:" + "+".join(regs))
    return out


def age_days(created: str | None, at: datetime | None = None) -> int | None:
    """Wiek domeny w dniach w chwili `at` (domyślnie teraz). None, gdy brak daty rejestracji."""
    if not created:
        return None
    try:
        c = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
    except ValueError:
        return None
    if c.tzinfo is None:
        c = c.replace(tzinfo=timezone.utc)
    return max(0, ((at or datetime.now(timezone.utc)) - c).days)


def summary(case: Case) -> list[str]:
    """Opis domen materiału po polsku (rejestrator, data, wiek), do karty i interfejsu."""
    out = []
    for d, r in (case.meta.get("infra") or {}).items():
        if not r.get("created"):
            continue
        age = r.get("wiek_dni")
        fresh = ", świeża domena" if age is not None and age <= FRESH_DAYS else ""
        har = bool(case.meta.get("observed"))
        if age == 0:
            rel = "w dniu zapisu ruchu (HAR)" if har else "dziś"
        else:
            rel = f"{age} {'dzień' if age == 1 else 'dni'} przed " + ("zapisem ruchu (HAR)" if har else "analizą")
        out.append(f"{d}: zarejestrowana {str(r['created'])[:10]}" + (f", {rel}{fresh}" if age is not None else "")
                   + (f", rejestrator {r['registrar']}" if r.get("registrar") else ""))
    return out


def describe(token: str) -> str:
    """Ślad `infra` po polsku (do przesłanek i tabeli śladów klastra)."""
    kind, _, v = token.partition(":")
    if kind == "rej":
        reg, _, when = v.partition("|")
        return f"rejestracja domeny: {reg}, {when[:10]} ok. {when[11:13]}:00 UTC" if len(when) >= 13 else f"rejestracja domeny: {reg}, {when}"
    if kind == "cf":
        return f"ta sama para serwerów nazw Cloudflare ({v.replace('+', ', ')}): to samo konto"
    if kind == "cert":
        return f"wspólny certyfikat TLS na domeny {v.replace('+', ', ')}"
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
    found, recs, src = set(), {}, {}

    def one(d):
        try:
            return d, lookup(d, net=net, resolver=resolver, get=get)
        except Exception:                   # sieć, format odpowiedzi: materiał zostaje bez tego kanału
            return d, None

    obs = None
    if case.meta.get("observed"):
        try:
            obs = datetime.fromisoformat(str(case.meta["observed"]).replace("Z", "+00:00"))
            obs = obs if obs.tzinfo else obs.replace(tzinfo=timezone.utc)
        except ValueError:
            obs = None
    doms = domains_of(case)
    with ThreadPoolExecutor(max_workers=max(1, min(4, len(doms)))) as ex:   # równolegle: w trybie auto kilka domen naraz z sieci
        results = list(ex.map(one, doms))
    for d, rec in results:
        if rec:
            recs[d] = {k: rec.get(k) for k in ("ns", "registrar", "created")}
            recs[d]["wiek_dni"] = age_days(rec.get("created"), obs)   # w chwili obserwacji (HAR), inaczej teraz
            for t in traces(rec):
                src.setdefault(t, []).append(d)      # z której domeny ślad (score.py nie liczy drugi raz śladu wspólnej domeny)
                found.add(t)
    if found:
        case.sets["infra"] = found
        case.meta["infra_src"] = src
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
