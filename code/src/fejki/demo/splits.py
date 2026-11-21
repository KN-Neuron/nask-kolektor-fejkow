"""Podział danych odporny na wyciek: „podmiot” (subject) = wszystko, co może dzielić informację, idzie w całości do jednego zbioru.

Odpowiednik podziału subject-wise z badań medycznych (ten sam pacjent nigdy w treningu i teście). U nas „pacjentem” jest
grupa materiałów połączonych JAKIMKOLWIEK wspólnym śladem, z progiem znacznie niższym niż przy grupowaniu kampanii:
wspólna domena, piksel, identyfikator reklamy, kontakt, niemal identyczny tekst (duplikat), podobny obraz, ta sama nazwa
produktu. Składowe spójne takiego grafu to podmioty. Pojedyncze materiały („solowe”) są osobnymi podmiotami i trafiają do
testu jako przykłady „nowego wzorca” (open-set: model nie może ich nigdzie dokleić).

Dodatkowo `audit()` sprawdza gotowy podział i wypisuje każdy możliwy przeciek między treningiem a testem.
"""
from __future__ import annotations

import random
from collections import defaultdict
from itertools import combinations

from pydantic import BaseModel, Field

from .material import Material, hamming
from .similar import TextSpace

# Ślady, które przenoszą informację o kampanii (jeśli są wspólne między zbiorami, test jest „podglądany”)
LEAK_RULES = ("domena docelowa", "piksel Meta", "identyfikator reklamy", "identyfikator śledzenia", "kontakt",
              "niemal identyczny tekst", "podobny obraz", "ten sam produkt", "ten sam tytuł", "ten sam reklamodawca")


class Leak(BaseModel):
    a: str
    b: str
    rule: str
    detail: str


class Split(BaseModel):
    subjects: dict[str, str]  # materiał → podmiot
    folds: dict[str, int] = Field(default_factory=dict)  # podmiot → numer foldu
    solo: list[str] = Field(default_factory=list)  # podmioty jednoelementowe (test „nowego wzorca”)


def leaks_between(a: Material, b: Material, ts: TextSpace | None = None, text_thr: float = 0.9, img_thr: int = 6) -> list[Leak]:
    out = []

    def add(rule, detail):
        out.append(Leak(a=a.id, b=b.id, rule=rule, detail=detail))

    for d in set(a.landing_domains) & set(b.landing_domains):
        add("domena docelowa", d)
    for x in set(a.pixel_ids) & set(b.pixel_ids):
        add("piksel Meta", x)
    for x in set(a.ad_ids) & set(b.ad_ids):
        add("identyfikator reklamy", x)
    for x in set(a.tracker_ids) & set(b.tracker_ids):
        add("identyfikator śledzenia", x)
    for x in set(a.contacts) & set(b.contacts):
        add("kontakt", x)
    for x in {p.lower() for p in a.products} & {p.lower() for p in b.products}:
        add("ten sam produkt", x)
    for x in {t.lower() for t in a.titles if len(t) > 15} & {t.lower() for t in b.titles if len(t) > 15}:
        add("ten sam tytuł", x[:60])
    for x in {v.lower() for v in a.advertisers} & {v.lower() for v in b.advertisers}:
        add("ten sam reklamodawca", x)
    if ts is not None:
        s, _ = ts.sim(a.id, b.id)
        if s >= text_thr:
            add("niemal identyczny tekst", f"podobieństwo {s:.2f}")
    for x in a.images:
        hit = next((y for y in b.images if x.role == y.role and hamming(x.phash, y.phash) <= img_thr), None)
        if hit:
            add("podobny obraz", f"{x.file} ~ {hit.file}")
            break
    return out


def subjects(materials: list[Material], extra_groups: dict[str, str] | None = None) -> dict[str, str]:
    """Podmioty = składowe spójne grafu przecieków (+ opcjonalnie znane grupy, np. sieci z infrastruktury lub etykiety pivotów)."""
    ts = TextSpace(materials)
    parent = {m.id: m.id for m in materials}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in combinations(materials, 2):
        if leaks_between(a, b, ts):
            parent[find(a.id)] = find(b.id)
    by_group = defaultdict(list)
    for mid, g in (extra_groups or {}).items():
        if mid in parent:
            by_group[g].append(mid)
    for mids in by_group.values():
        for x in mids[1:]:
            parent[find(x)] = find(mids[0])
    roots = defaultdict(list)
    for m in materials:
        roots[find(m.id)].append(m.id)
    out = {}
    for k, (_, mids) in enumerate(sorted(roots.items(), key=lambda r: (-len(r[1]), sorted(r[1])))):
        name = f"P{k + 1}" if len(mids) > 1 else f"solo:{mids[0]}"
        for x in mids:
            out[x] = name
    return out


def group_kfold(subject_of: dict[str, str], k: int = 5, seed: int = 1) -> Split:
    """Podmioty wieloelementowe rozdzielone na k foldów (zbalansowane po liczbie materiałów); solowe osobno."""
    sizes = defaultdict(int)
    for s in subject_of.values():
        sizes[s] += 1
    multi = [s for s in sizes if not s.startswith("solo:")]
    rnd = random.Random(seed)
    rnd.shuffle(multi)
    multi.sort(key=lambda s: -sizes[s])  # największe najpierw, zachłannie do najmniejszego foldu
    load = [0] * k
    folds = {}
    for s in multi:
        f = load.index(min(load))
        folds[s] = f
        load[f] += sizes[s]
    return Split(subjects=subject_of, folds=folds, solo=sorted(s for s in sizes if s.startswith("solo:")))


def audit(train: list[Material], test: list[Material]) -> list[Leak]:
    """Każdy możliwy przeciek między treningiem a testem. Pusta lista = podział czysty."""
    pool = train + test
    ts = TextSpace(pool)
    return [lk for a in train for b in test for lk in leaks_between(a, b, ts)]


def fold_sets(split: Split, fold: int) -> tuple[set[str], set[str]]:
    """(trening, test) dla foldu: test = podmioty z tego foldu; solowe zawsze w teście (open-set)."""
    test = {m for m, s in split.subjects.items() if split.folds.get(s) == fold or s in split.solo}
    train = {m for m, s in split.subjects.items() if m not in test}
    return train, test
