"""Karty kampanii dla analityka CERT: okno czasowe, domeny kampanii, lista domen do weryfikacji z uzasadnieniem.

Okno czasowe to czas ZEBRANIA materiałów (znaczniki w logach HAR, daty w nazwach zrzutów), a nie czas emisji reklam.
Daty emisji da dopiero Meta Ad Library (identyfikatory reklam są w kartach).
"""
from __future__ import annotations

import csv
import io
from datetime import datetime

from pydantic import BaseModel, Field

from .material import Material
from .similar import Campaign, Pair

PRIORITY = {"wysoki": 0, "średni": 1, "niski": 2}


class DomainToVerify(BaseModel):
    domain: str
    priority: str
    roles: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    registered: str | None = None
    notes: list[str] = Field(default_factory=list)


class CampaignCard(BaseModel):
    id: str
    name: str
    network: str | None
    members: list[str]
    network_members: list[str] = Field(default_factory=list)
    window_start: str | None = None
    window_end: str | None = None
    window_days: float | None = None
    observations: list[dict] = Field(default_factory=list)
    titles: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    persons: list[str] = Field(default_factory=list)
    products: list[str] = Field(default_factory=list)
    advertisers: list[str] = Field(default_factory=list)
    ad_ids: list[str] = Field(default_factory=list)
    pixel_ids: list[str] = Field(default_factory=list)
    tracker_ids: list[str] = Field(default_factory=list)
    campaign_domains: list[str] = Field(default_factory=list)
    domains_to_verify: list[DomainToVerify] = Field(default_factory=list)
    links: list[dict] = Field(default_factory=list)  # krawędzie wewnątrz kampanii i do reszty sieci
    cloaking: list[str] = Field(default_factory=list)
    missing: dict[str, list[str]] = Field(default_factory=dict)
    strength: float = 0.0


def _uniq(xs):
    return list(dict.fromkeys(x for x in xs if x))


def _parse(d: str) -> datetime | None:
    try:
        return datetime.fromisoformat(d.replace("Z", ""))
    except ValueError:
        return None


def build_cards(materials: list[Material], pairs: list[Pair], camps: list[Campaign], nets: list[Campaign],
                thr: float = 0.7, infra: dict | None = None) -> list[CampaignCard]:
    by_id = {m.id: m for m in materials}
    net_of = {mid: n for n in nets for mid in n.members}
    cards = []
    for c in camps:
        ms = [by_id[x] for x in c.members]
        net = net_of.get(c.members[0])
        others = [x for x in (net.members if net else []) if x not in c.members]
        obs = sorted(({"material": m.id, **o} for m in ms for o in m.observed), key=lambda o: o["date"])
        dts = [d for d in (_parse(o["date"]) for o in obs) if d]
        card = CampaignCard(
            id=c.id, name=c.name, network=net.id if net and len(net.members) > 1 else None, members=c.members,
            network_members=others, observations=obs, strength=c.strength,
            window_start=min(dts).isoformat(sep=" ")[:16] if dts else None,
            window_end=max(dts).isoformat(sep=" ")[:16] if dts else None,
            window_days=round((max(dts) - min(dts)).total_seconds() / 86400, 1) if dts else None,
            titles=_uniq(t for m in ms for t in m.titles)[:6],
            topics=c.topics, persons=c.persons,
            products=_uniq(p for m in ms for p in m.products),
            advertisers=_uniq(a for m in ms for a in m.advertisers),
            ad_ids=_uniq(a for m in ms for a in m.ad_ids),
            pixel_ids=_uniq(p for m in ms for p in m.pixel_ids),
            tracker_ids=_uniq(t for m in ms for t in m.tracker_ids),
            campaign_domains=_uniq(d for m in ms for d in m.landing_domains),
            cloaking=[f"{m.id}: {x}" for m in ms for x in m.cloaking],
            missing={m.id: m.missing for m in ms if m.missing},
        )
        # domeny do weryfikacji: role i priorytet
        dv: dict[str, DomainToVerify] = {}

        def put(domain, priority, role, mid, note=None):
            if not domain:
                return
            x = dv.setdefault(domain, DomainToVerify(domain=domain, priority=priority))
            if PRIORITY[priority] < PRIORITY[x.priority]:
                x.priority = priority
            if role not in x.roles:
                x.roles.append(role)
            if mid not in x.materials:
                x.materials.append(mid)
            if note and note not in x.notes:
                x.notes.append(note)

        for m in ms:
            for d in m.landing_domains:
                put(d, "wysoki", "domena docelowa reklamy w kampanii", m.id)
            for h in m.third_party_hosts:
                put(h, "średni", "nietypowa usługa zewnętrzna ładowana przez stronę kampanii", m.id)
            for r in m.redirects:
                dst = r.split(" → ")[-1].split(" ")[0]
                put(dst, "średni", "cel przekierowania", m.id)
        for x in others:
            for d in by_id[x].landing_domains:
                put(d, "średni", f"domena innej kampanii tej samej sieci ({net.id})", x,
                    "ten sam operator wg wspólnej infrastruktury; możliwa rotacja domen")
        first_seen = {}
        for m in materials:
            ds = [d for d in (_parse(o["date"]) for o in m.observed) if d]
            if ds:
                first_seen[m.id] = min(ds)
        for d, x in dv.items():
            rec = (infra or {}).get(d)
            if rec is not None:
                x.registered = (rec.rdap.created or "")[:10] or None
                if rec.rdap.registrar:
                    x.notes.append(f"rejestrator: {rec.rdap.registrar}")
                reg = _parse((rec.rdap.created or "")[:19])
                seen = [first_seen[mid] for mid in x.materials if mid in first_seen]
                if reg and seen:
                    age = (min(seen) - reg).total_seconds() / 86400
                    x.notes.append(f"wiek domeny przy pierwszej obserwacji: {age:.1f} dni" + (" (świeża domena)" if 0 <= age <= 7 else ""))
        card.domains_to_verify = sorted(dv.values(), key=lambda x: (PRIORITY[x.priority], -len(x.materials), x.domain))
        # krawędzie (przesłanki) w kampanii i do reszty sieci
        scope = set(c.members) | set(others)
        for p in pairs:
            if p.score >= thr and (p.a in c.members or p.b in c.members) and p.a in scope and p.b in scope:
                card.links.append({"a": p.a, "b": p.b, "score": p.score, "relation": p.relation,
                                   "evidence": [e.reason for e in p.evidence[:5]]})
        cards.append(card)
    return cards


def card_markdown(c: CampaignCard) -> str:
    L = [f"# Karta kampanii {c.id}: {c.name}", ""]
    L.append(f"- **Materiały:** {', '.join(c.members)}" + (f" · **sieć operatora {c.network}:** także {', '.join(c.network_members)}"
                                                          if c.network and c.network_members else ""))
    if c.window_start:
        if c.window_start == c.window_end:
            span = f"{c.window_start} UTC"
        else:
            dur = f"{c.window_days} dni" if (c.window_days or 0) >= 1 else f"{round((c.window_days or 0) * 24, 1)} h"
            span = f"{c.window_start} → {c.window_end} UTC ({dur})"
        L.append(f"- **Okno obserwacji:** {span}; czas zebrania materiałów (logi HAR, daty w nazwach zrzutów), nie czas emisji reklam")
    else:
        L.append("- **Okno obserwacji:** brak dat w materiałach")
    for label, xs in [("Tematyka", c.topics), ("Osoby publiczne", c.persons), ("Produkty", c.products),
                      ("Reklamodawcy (z kreacji)", c.advertisers), ("Identyfikatory reklam Meta", c.ad_ids),
                      ("Piksele Meta", c.pixel_ids), ("Inne identyfikatory śledzenia", c.tracker_ids),
                      ("Domeny kampanii", c.campaign_domains)]:
        if xs:
            L.append(f"- **{label}:** {', '.join(xs)}")
    if c.titles:
        L += ["", "## Tytuły stron", *[f"- {t}" for t in c.titles]]
    L += ["", "## Domeny do weryfikacji", "", "| Domena | Priorytet | Dlaczego | Materiały | Rejestracja |", "|---|---|---|---|---|"]
    for d in c.domains_to_verify:
        why = "; ".join(d.roles + d.notes)
        L.append(f"| {d.domain} | {d.priority} | {why} | {', '.join(d.materials)} | {d.registered or '—'} |")
    if not c.domains_to_verify:
        L.append("| — | | brak domen w materiałach | | |")
    if c.links:
        L += ["", "## Przesłanki powiązań"]
        for k in c.links:
            L.append(f"- **{k['a']} ↔ {k['b']}** ({k['score']:.2f}, {k['relation']}): " + "; ".join(k["evidence"]))
    if c.cloaking:
        L += ["", "## Cloaking", *[f"- {x}" for x in c.cloaking]]
    if c.observations:
        L += ["", "## Obserwacje w czasie", *[f"- {o['date'].replace('T', ' ')}: materiał {o['material']} ({o['source']})"
                                              for o in c.observations[:20]]]
    if c.missing:
        L += ["", "## Braki danych", *[f"- {k}: {'; '.join(v)}" for k, v in c.missing.items()]]
    L += ["", "_Karta wygenerowana automatycznie. Domeny do weryfikacji to propozycje dla analityka, nie werdykt._"]
    return "\n".join(L)


def domains_csv(cards: list[CampaignCard]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["kampania", "siec", "domena", "priorytet", "role", "materialy", "rejestracja", "okno_od", "okno_do"])
    for c in cards:
        for d in c.domains_to_verify:
            w.writerow([c.id, c.network or "", d.domain, d.priority, " | ".join(d.roles), " ".join(d.materials),
                        d.registered or "", c.window_start or "", c.window_end or ""])
    return buf.getvalue()


def all_markdown(cards: list[CampaignCard]) -> str:
    return "\n\n---\n\n".join(card_markdown(c) for c in cards)
