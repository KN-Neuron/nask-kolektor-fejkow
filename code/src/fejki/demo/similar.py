"""Wyjaśnialne podobieństwo materiałów, grupowanie w kampanie i dopasowanie nowego materiału.

Każdy kanał (tekst, osoby, produkt, śledzenie, adres, infrastruktura, obraz, szablon strony) daje dowody z wagą i opisem.
Dowody łączymy metodą noisy-OR najpierw w kanale, potem między kanałami. Słaby, pospolity sygnał (np. ta sama osoba publiczna
w wielu kampaniach) nie tworzy krawędzi sam; krawędź powstaje, gdy kilka niezależnych śladów się zgadza albo jeden jest bardzo
specyficzny (piksel, identyfikator reklamy, ta sama domena docelowa).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations

import numpy as np
from pydantic import BaseModel, Field
from rapidfuzz import fuzz

from .material import Material, clean_ocr, hamming

W = {
    "same_landing": 0.9, "shared_ad_id": 0.95, "shared_pixel": 0.9, "shared_tracker": 0.85, "shared_account": 0.6,
    "shared_contact": 0.9, "same_scheme": 0.6, "same_path_template": 0.7, "shared_prefix": 0.5, "shared_host": 0.6,
    "shared_redirect": 0.6, "text_dup": 0.9, "text_max": 0.8, "same_title": 0.7, "person": 0.3, "person_cap": 0.5,
    "same_product": 0.75, "img_shot": 0.7, "img_asset": 0.6, "dom_max": 0.35, "topic": 0.1, "infra_scale": 0.9,
    "shared_advertiser": 0.7, "semantic": 0.5, "same_logo": 0.3, "visual": 0.6,
}
CHANNELS = {
    "same_landing": "domena", "shared_ad_id": "śledzenie", "shared_pixel": "śledzenie", "shared_tracker": "śledzenie",
    "shared_account": "śledzenie", "shared_contact": "kontakt", "same_scheme": "adres", "same_path_template": "adres",
    "shared_prefix": "adres", "shared_host": "adres", "shared_redirect": "przekierowania", "text": "tekst", "same_title": "tekst",
    "person": "osoby", "same_product": "produkt", "img_shot": "obraz", "img_asset": "obraz", "dom": "szablon strony",
    "topic": "tematyka", "infra": "infrastruktura", "shared_advertiser": "reklamodawca", "semantic": "semantyka",
    "same_logo": "obraz", "visual": "obraz", "conflict": "konflikt",
}


VIS_FLOOR = 0.92  # embeddingi zrzutów odzwierciedlają głównie format (telefon vs komputer): 0,80 łączyłoby różnych operatorów (10↔14: 0,84), więc tylko niemal-duplikaty
DOM_MIN = 25  # minimalna liczba różnych klas/elementów HTML, by szablon był dowodem
SEM_FLOOR = 0.88  # poniżej tego podobieństwa bge-m3 nie jest dowodem: tło między różnymi sieciami sięga 0,86


class Evidence(BaseModel):
    code: str
    channel: str
    weight: float
    reason: str


class Pair(BaseModel):
    a: str
    b: str
    score: float
    relation: str
    text_sim: float = 0.0
    evidence: list[Evidence] = Field(default_factory=list)


class Campaign(BaseModel):
    id: str
    name: str
    members: list[str]
    strength: float
    signals: dict[str, int] = Field(default_factory=dict)
    persons: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)


class MatchResult(BaseModel):
    decision: str
    best_campaign: str | None
    best_score: float
    ranking: list[dict] = Field(default_factory=list)  # [{campaign, score, via, evidence}]
    pairs: list[Pair] = Field(default_factory=list)


# --- tekst ----------------------------------------------------------------------------------------------------------

_PL = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")


def fold_pl(s: str) -> str:
    return s.translate(_PL).lower()


class TextSpace:
    """TF-IDF (słowa 1–2) na tytułach i treści. Mały, szybki, a wspólne słowa da się pokazać jako uzasadnienie."""

    def __init__(self, materials: list[Material]):
        from sklearn.feature_extraction.text import TfidfVectorizer

        self.ids = [m.id for m in materials]
        # polskie znaki ujednolicone: OCR bez polskiego pakietu językowego gubi diakrytyki, HTML je ma
        docs = [fold_pl(((" ".join(m.titles) + " ") * 3 + m.text + " " + clean_ocr(m.ocr_text))[:60000]) for m in materials]
        self.vec = TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True, max_features=60000,
                                   token_pattern=r"(?u)\b[^\W\d_]{3,}\b", lowercase=True)
        self.X = self.vec.fit_transform(docs) if any(d.strip() for d in docs) else None
        self.terms = np.array(self.vec.get_feature_names_out()) if self.X is not None else np.array([])
        self.idx = {i: k for k, i in enumerate(self.ids)}
        self.sem: dict[str, np.ndarray] | None = None
        self.vis: dict[str, np.ndarray] | None = None

    def enable_semantic(self, materials: list[Material], encoder: str = "bge-m3") -> None:
        """Wektory znaczenia tekstu (średnia z fragmentów) z enkodera semantycznego; bez modelu na dysku nic nie robi."""
        from .template import TemplateSpace, model_available

        if encoder == "bge-m3" and not model_available():
            return
        sp = TemplateSpace(materials, encoder=encoder)
        self.sem = dict(sp.X["surowe"])

    def enable_visual(self, vectors: dict[str, np.ndarray]) -> None:
        """Wektory wyglądu (embeddingi zrzutów i kreacji) policzone w `demo/vision.py`."""
        self.vis = vectors or None

    def vis_sim(self, a: str, b: str) -> float | None:
        if not self.vis or a not in self.vis or b not in self.vis:
            return None
        return float(self.vis[a] @ self.vis[b])

    def sem_sim(self, a: str, b: str) -> float | None:
        if not self.sem or a not in self.sem or b not in self.sem:
            return None
        return float(self.sem[a] @ self.sem[b])

    def sim(self, a: str, b: str) -> tuple[float, list[str]]:
        if self.X is None:
            return 0.0, []
        va, vb = self.X[self.idx[a]], self.X[self.idx[b]]
        if va.nnz == 0 or vb.nnz == 0:
            return 0.0, []
        prod = va.multiply(vb)
        s = float(prod.sum())
        top = []
        if prod.nnz:
            coo = prod.tocoo()
            order = np.argsort(-coo.data)[:6]
            top = [str(self.terms[coo.col[i]]) for i in order]
        return round(s, 3), top


# --- dowody dla pary -------------------------------------------------------------------------------------------------

def _rarity(df: int) -> float:
    """Im więcej materiałów dzieli cechę, tym mniej mówi ona o wspólnej kampanii."""
    return 1.0 if df <= 2 else 2.0 / df


def doc_freq(materials: list[Material]) -> dict[str, Counter]:
    df: dict[str, Counter] = defaultdict(Counter)
    for m in materials:
        for p in set(m.persons):
            df["person"][p] += 1
        for t in list(m.topics)[:1]:
            df["topic"][t] += 1
        for h in set(m.third_party_hosts):
            df["host"][h] += 1
        for p in set(m.path_prefixes):
            df["prefix"][p] += 1
    return df


def evidence(a: Material, b: Material, ts: TextSpace, df: dict[str, Counter], infra: dict | None = None) -> tuple[list[Evidence], float]:
    ev: list[Evidence] = []

    def add(code, weight, reason, channel=None):
        ev.append(Evidence(code=code, channel=channel or CHANNELS.get(code, code), weight=round(weight, 3), reason=reason))

    for d in sorted(set(a.landing_domains) & set(b.landing_domains)):
        add("same_landing", W["same_landing"], f"ta sama domena docelowa: {d}")
    for x in sorted(set(a.ad_ids) & set(b.ad_ids)):
        add("shared_ad_id", W["shared_ad_id"], f"ten sam identyfikator reklamy Meta: {x}")
    for x in sorted(set(a.pixel_ids) & set(b.pixel_ids)):
        add("shared_pixel", W["shared_pixel"], f"ten sam piksel Meta: {x} (to samo konto reklamowe lub operator)")
    for x in sorted(set(a.tracker_ids) & set(b.tracker_ids)):
        add("shared_tracker", W["shared_tracker"], f"ten sam identyfikator śledzenia: {x}")
    for x in sorted(set(a.ad_accounts) & set(b.ad_accounts)):
        add("shared_account", W["shared_account"], f"ten sam oznacznik konta w adresie (acc={x})")
    for x in sorted(set(a.contacts) & set(b.contacts)):
        add("shared_contact", W["shared_contact"], f"ten sam kontakt: {x}")
    adv = [(x, y) for x in a.advertisers for y in b.advertisers if fuzz.ratio(fold_pl(x), fold_pl(y)) >= 90]
    if adv:
        add("shared_advertiser", W["shared_advertiser"], f"ten sam reklamodawca w kreacji: {adv[0][0]}")
    sch = sorted(set(a.url_schemes) & set(b.url_schemes))
    if sch:
        keys = ", ".join(s.split(":")[0] for s in sch[0].split("&")[:6])
        add("same_scheme", W["same_scheme"], f"identyczny schemat parametrów adresu (losowe wartości o stałej długości: {keys}): ten sam system kierowania ruchu")
    tm = sorted(t for t in set(a.path_templates) & set(b.path_templates) if len(t) > 6 and t.count("/") >= 2)
    if tm:
        add("same_path_template", W["same_path_template"], f"ten sam wzorzec ścieżki: {tm[0][:80]}")
    pf = sorted(set(a.path_prefixes) & set(b.path_prefixes))
    if pf and not tm:
        r = _rarity(df["prefix"][pf[0]])
        add("shared_prefix", W["shared_prefix"] * r, f"wspólny katalog zestawu strony: {pf[0][:70]}")
    for h in sorted(set(a.third_party_hosts) & set(b.third_party_hosts))[:3]:
        add("shared_host", W["shared_host"] * _rarity(df["host"][h]), f"ta sama nietypowa usługa zewnętrzna: {h}")
    ra = {r.split(" → ")[-1].split(" ")[0] for r in a.redirects}
    rb = {r.split(" → ")[-1].split(" ")[0] for r in b.redirects}
    for h in sorted(ra & rb)[:2]:
        add("shared_redirect", W["shared_redirect"], f"przekierowania prowadzą do tego samego hosta: {h}")
    # tekst
    s, top = ts.sim(a.id, b.id)
    if s >= 0.9:
        add("text", W["text_dup"], f"niemal identyczny tekst (podobieństwo {s:.2f}); wspólne: {', '.join(top[:4])}")
    elif s >= 0.3:
        add("text", W["text_max"] * min(1.0, (s - 0.25) / 0.6), f"podobny tekst (podobieństwo {s:.2f}); wspólne: {', '.join(top[:5])}")
    sm = ts.sem_sim(a.id, b.id)
    if sm is not None and sm >= SEM_FLOOR:  # tło: wszystkie strony oszustw są do siebie podobne (~0,68), więc liczy się tylko nadwyżka
        add("semantic", W["semantic"] * min(1.0, (sm - SEM_FLOOR) / (1 - SEM_FLOOR)),
            f"podobne znaczenie tekstu (bge-m3, podobieństwo {sm:.2f}, tło oszustw {SEM_FLOOR:.2f})")
    vs = ts.vis_sim(a.id, b.id)
    if vs is not None and vs >= VIS_FLOOR:
        add("visual", W["visual"] * min(1.0, (vs - VIS_FLOOR) / (1 - VIS_FLOOR)),
            f"podobny wygląd reklamy lub strony (embedding obrazu, podobieństwo {vs:.2f})")
    lg = sorted(set(a.logos) & set(b.logos))
    if lg:
        add("same_logo", W["same_logo"], f"podrabiana ta sama marka / portal: {', '.join(lg[:3])} (logo w zasobach strony)")
    tt = [(x, y) for x in a.titles for y in b.titles if x and y and fuzz.ratio(x.lower(), y.lower()) >= 92]
    if tt:
        add("same_title", W["same_title"], f"ten sam tytuł strony: „{tt[0][0][:70]}”")
    # osoby (słaby sygnał: te same znane twarze bywają w wielu kampaniach)
    pw = 0.0
    for p in sorted(set(a.persons) & set(b.persons)):
        r = _rarity(df["person"][p])
        w = W["person"] * r
        pw = 1 - (1 - pw) * (1 - w)
        add("person", w, f"ta sama osoba publiczna: {p}" + ("" if r == 1 else f" (występuje w {df['person'][p]} materiałach, słaby sygnał)"))
    # produkt
    pr = [(x, y) for x in a.products for y in b.products if fuzz.ratio(x.lower(), y.lower()) >= 88]
    if pr:
        add("same_product", W["same_product"], f"ten sam produkt: {pr[0][0]}")
    else:  # nazwa produktu jednego materiału pada w treści drugiego (np. wejście „nazwa produktu” albo OCR kreacji)
        for x, other in [(p, b) for p in a.products] + [(p, a) for p in b.products]:
            if len(x) >= 5 and fold_pl(x) in fold_pl(" ".join(other.titles) + " " + other.text[:20000]):
                add("same_product", W["same_product"], f"nazwa produktu „{x}” występuje w treści drugiego materiału")
                break
    # obraz
    shots = [(x, y, hamming(x.phash, y.phash)) for x in a.images for y in b.images
             if x.role != "zasob" and y.role != "zasob"]
    close = sorted([t for t in shots if t[2] <= 8], key=lambda t: t[2])
    if close:
        x, y, d = close[0]
        add("img_shot", W["img_shot"], f"podobny obraz/zrzut ({x.file} ~ {y.file}, różnica pHash {d}/64)")
    assets = {}
    for x in a.images:
        if x.role != "zasob":
            continue
        for y in b.images:
            if y.role == "zasob" and hamming(x.phash, y.phash) <= 4:
                assets[x.file] = y.file
    if assets:
        n = len(assets)
        add("img_asset", min(0.9, W["img_asset"] + 0.05 * (n - 1)), f"te same obrazy użyte na obu stronach ({n}, np. {next(iter(assets))})")
    # szablon strony (struktura DOM)
    if len(a.dom_tokens) >= DOM_MIN and len(b.dom_tokens) >= DOM_MIN:  # mała strona zawsze „pasuje” do małej strony
        sa, sb = set(a.dom_tokens), set(b.dom_tokens)
        j = len(sa & sb) / max(1, len(sa | sb))
        if j >= 0.45:
            add("dom", W["dom_max"] * min(1.0, (j - 0.4) / 0.4), f"podobna struktura strony (wspólne klasy HTML: {j:.0%})")
    # tematyka (bardzo słaby)
    ta, tb = list(a.topics)[:1], list(b.topics)[:1]
    if ta and ta == tb:
        add("topic", W["topic"] * _rarity(df["topic"][ta[0]]), f"ta sama główna tematyka: {ta[0]}")
    # infrastruktura bierna (DNS/RDAP/CT), jeśli zebrana
    if infra:
        from ..infra.link import evidence as infra_ev
        from ..infra.link import score as infra_score

        best = None
        for da in a.landing_domains:
            for dbn in b.landing_domains:
                if da == dbn or da not in infra or dbn not in infra:
                    continue
                e = infra_ev(infra[da], infra[dbn])
                sc = infra_score(e)
                if e and (best is None or sc > best[0]):
                    best = (sc, da, dbn, e)
        if best and best[0] >= 0.3:
            sc, da, dbn, e = best
            add("infra", sc * W["infra_scale"], f"infrastruktura {da} ↔ {dbn}: " + "; ".join(x.reason for x in sorted(e, key=lambda x: -x.weight)[:3]))
    return ev, s


CONFLICT_FACTOR = 0.6


def conflict(a: Material, b: Material) -> str | None:
    """Ślady wykluczające wspólnego operatora: różne piksele Meta albo różne schematy TDS przy braku jakiegokolwiek wspólnego śladu
    identyfikującego (domena, piksel, identyfikator reklamy, tracker). Wspólny zestaw stron sam nie wystarcza, by uznać jednego operatora."""
    shared_id = (set(a.landing_domains) & set(b.landing_domains)) or (set(a.pixel_ids) & set(b.pixel_ids)) \
        or (set(a.ad_ids) & set(b.ad_ids)) or (set(a.tracker_ids) & set(b.tracker_ids))
    if shared_id:
        return None
    if a.pixel_ids and b.pixel_ids and not set(a.pixel_ids) & set(b.pixel_ids):
        return f"różne piksele Meta ({a.pixel_ids[0]} vs {b.pixel_ids[0]}): przeciw wspólnemu kontu reklamowemu"
    if a.url_schemes and b.url_schemes and not set(a.url_schemes) & set(b.url_schemes):
        return "różne schematy parametrów adresu (inny system kierowania ruchu): przeciw wspólnemu operatorowi"
    return None


def combine(ev: list[Evidence]) -> float:
    """noisy-OR w kanale (osoby z limitem), potem noisy-OR między kanałami."""
    per: dict[str, float] = defaultdict(float)
    for e in ev:
        per[e.channel] = 1 - (1 - per[e.channel]) * (1 - e.weight)
    if "osoby" in per:
        per["osoby"] = min(per["osoby"], W["person_cap"])
    p = 1.0
    for v in per.values():
        p *= 1 - min(v, 0.97)
    return round(1 - p, 3)


def relation(ev: list[Evidence], text_sim: float) -> str:
    codes = {e.code for e in ev}
    if "shared_ad_id" in codes or (text_sim >= 0.95 and ({"same_title", "same_landing"} & codes or "img_shot" in codes)):
        return "duplikat"
    if text_sim >= 0.6 or "same_title" in codes or "same_product" in codes or ("dom" in codes and text_sim >= 0.4):
        return "wariant tego samego przekazu"
    tech = {"same_landing", "shared_ad_id", "shared_pixel", "shared_tracker", "shared_account", "same_scheme", "same_path_template",
            "shared_prefix", "shared_host", "shared_redirect", "infra", "shared_contact", "img_asset", "shared_advertiser"}
    if codes & tech:
        return "wspólna infrastruktura / operator"
    return "podobieństwo treści" if codes else "brak"


def pair(a: Material, b: Material, ts: TextSpace, df, infra=None, model: dict | None = None) -> Pair:
    from .learn import resolve

    ev, s = evidence(a, b, ts, df, infra)
    model = resolve(model)
    if model:
        from .learn import score_with

        score = round(score_with(model, ev, s), 3)  # wynik z wyuczonych wag; przesłanki bez zmian
    else:
        score = combine(ev)
    why = conflict(a, b)
    if why:  # dowód PRZECIWKO wspólnemu operatorowi: obniżamy wynik i mówimy dlaczego
        score = round(score * CONFLICT_FACTOR, 3)
        ev = [*ev, Evidence(code="conflict", channel="konflikt", weight=0.0, reason=why)]
    return Pair(a=a.id, b=b.id, score=score, relation=relation(ev, s), text_sim=s, evidence=sorted(ev, key=lambda e: -e.weight))


COVERAGE = 0.3  # minimalny udział par faktycznie policzonych przy średnim wiązaniu (w trybie pełnym = 100%)
FAISS_FROM = 60  # powyżej tylu materiałów kandydatów dla nowego materiału wybiera indeks FAISS
FAISS_K = 40  # ilu najbliższych sąsiadów z indeksu bierzemy (poza blokowaniem po kluczach)
BLOCK_ABOVE = 300  # powyżej tylu materiałów liczymy tylko pary-kandydatów (skalowalność)


def candidate_pairs(materials: list[Material], ts: TextSpace, k: int = 12) -> set[tuple[str, str]]:
    """Pary-kandydaci: wspólny klucz blokujący (domena, piksel, identyfikator, schemat, katalog, tytuł, reklamodawca, logo,
    kontakt) albo k najbliższych sąsiadów w tekście. Pozostałych par nie liczymy (wynik 0), więc koszt rośnie ~liniowo."""
    keys: dict[tuple[str, str], list[str]] = defaultdict(list)
    for m in materials:
        for kind, vals in (("d", m.landing_domains), ("px", m.pixel_ids), ("ad", m.ad_ids), ("tr", m.tracker_ids),
                           ("sc", m.url_schemes), ("pf", m.path_prefixes), ("pt", [t for t in m.path_templates if t.count("/") >= 2]),
                           ("th", m.third_party_hosts), ("rd", [r.split(" → ")[-1].split(" ")[0] for r in m.redirects]), ("ct", m.contacts), ("lg", m.logos),
                           ("ti", [t.lower() for t in m.titles if len(t) > 15]), ("av", [x.lower() for x in m.advertisers]),
                           ("pr", [x.lower() for x in m.products])):
            for v in vals:
                keys[(kind, v)].append(m.id)
    out: set[tuple[str, str]] = set()
    for ids in keys.values():
        if 1 < len(ids) <= 200:  # klucze „masowe” (np. wspólny CDN) nie blokują
            for a, b in combinations(sorted(set(ids)), 2):
                out.add((a, b))
    if len(materials) > 2:  # k najbliższych sąsiadów z indeksu FAISS (zamiast macierzy n×n)
        from .vindex import get_index

        out |= get_index(materials).neighbours(materials, k)
    return out


def all_pairs(materials: list[Material], infra: dict | None = None, semantic: bool = False,
              visual: dict[str, np.ndarray] | None = None, model: dict | None = None, block: bool | None = None) -> list[Pair]:
    """Wszystkie pary z wynikiem. `model`: wyuczony klasyfikator par (zamiast noisy-OR); `block`: tylko pary-kandydaci
    (domyślnie włączone powyżej BLOCK_ABOVE materiałów)."""
    ts = TextSpace(materials)
    if semantic:
        ts.enable_semantic(materials)
    if visual:
        ts.enable_visual(visual)
    df = doc_freq(materials)
    use_block = block if block is not None else len(materials) > BLOCK_ABOVE
    cand = candidate_pairs(materials, ts) if use_block else None
    pairs = []
    for a, b in combinations(materials, 2):
        if cand is not None and tuple(sorted((a.id, b.id))) not in cand:
            continue
        pairs.append(pair(a, b, ts, df, infra, model))
    return sorted(pairs, key=lambda p: -p.score)


# --- kampanie -------------------------------------------------------------------------------------------------------

CONTENT_RELATIONS = ("duplikat", "wariant tego samego przekazu")


def _components(ids: list[str], keep: list[Pair]) -> dict[str, list[str]]:
    parent = {i: i for i in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for p in keep:
        parent[find(p.a)] = find(p.b)
    groups: dict[str, list[str]] = defaultdict(list)
    for i in ids:
        groups[find(i)].append(i)
    return groups


def _average_linkage(ids: list[str], keep: list[Pair], pairs: list[Pair], thr: float, min_support: float) -> dict[str, list[str]]:
    """Łączenie bez łańcuchowania: dwie grupy scalamy tylko wtedy, gdy łączy je krawędź ≥ thr ORAZ średni wynik
    wszystkich par między nimi ≥ min_support (pary bez dowodów liczą się jako 0). Dzięki temu A~B i B~C nie skleja A z C,
    jeśli A i C nie mają ze sobą nic wspólnego (zjawisko „czarnej dziury” w łączeniu rekordów)."""
    score = {(p.a, p.b): p.score for p in pairs}
    score.update({(p.b, p.a): p.score for p in pairs})
    allowed = {(p.a, p.b) for p in keep} | {(p.b, p.a) for p in keep}
    clusters = {i: [i] for i in ids}
    while True:
        best, best_avg = None, -1.0
        keys = list(clusters)
        for x in range(len(keys)):
            for y in range(x + 1, len(keys)):
                A, B = clusters[keys[x]], clusters[keys[y]]
                if not any((a, b) in allowed for a in A for b in B):
                    continue
                got = [score[(a, b)] for a in A for b in B if (a, b) in score]
                # pary nieliczone (blokowanie kandydatów) pomijamy, ale wymagamy pokrycia ≥ COVERAGE, by nie wrócić do łańcuchowania
                avg = sum(got) / max(len(got), COVERAGE * len(A) * len(B))
                if avg >= min_support and avg > best_avg:
                    best, best_avg = (keys[x], keys[y]), avg
        if best is None:
            break
        clusters[best[0]] += clusters.pop(best[1])
    return clusters


def campaigns(materials: list[Material], pairs: list[Pair], thr: float = 0.7, level: str = "kampania",
              method: str = "average", min_support: float = 0.15) -> list[Campaign]:
    """Grupy z krawędzi o wyniku >= thr. Pojedyncze materiały zostają osobnymi grupami.

    method="average" (domyślnie): średnie wiązanie z wymogiem wsparcia (bez łańcuchowania);
    method="components": składowe spójne (stara wersja, podatna na łańcuchowanie).

    level="kampania": tylko krawędzie typu duplikat/wariant (ten sam przekaz).
    level="sieć": każda krawędź (także sama wspólna infrastruktura), czyli prawdopodobnie ten sam operator.
    """
    keep = [p for p in pairs if p.score >= thr and (level != "kampania" or p.relation in CONTENT_RELATIONS)]
    groups = _average_linkage([m.id for m in materials], keep, pairs, thr, min_support) if method == "average" \
        else _components([m.id for m in materials], keep)
    by_id = {m.id: m for m in materials}
    out = []
    prefix = "K" if level == "kampania" else "S"
    for k, (root, mem) in enumerate(sorted(groups.items(), key=lambda g: (-len(g[1]), g[1][0]))):
        mem = sorted(mem, key=lambda x: (len(x), x))
        inner = [p for p in keep if p.a in mem and p.b in mem]
        sig = Counter(e.channel for p in inner for e in p.evidence)
        ms = [by_id[x] for x in mem]
        persons = [p for p, _ in Counter(p for m in ms for p in m.persons).most_common(4)]
        topics = [t for t, _ in Counter(next(iter(m.topics), "") for m in ms if m.topics).most_common(2)]
        domains = sorted({d for m in ms for d in m.landing_domains})
        products = Counter(p for m in ms for p in m.products)
        titles = Counter(t for m in ms for t in m.titles[:1])
        name_bits = [topics[0] if topics else "bez tematu"]
        common_prod = [p for p, n in products.most_common() if n * 2 >= len(ms)]
        if common_prod:
            name_bits.append(common_prod[0])
        elif persons:
            name_bits.append(", ".join(persons[:2]))
        elif titles:
            name_bits.append(titles.most_common(1)[0][0][:40])
        out.append(Campaign(id=f"{prefix}{k + 1}", name=" · ".join(name_bits), members=mem,
                            strength=round(float(np.mean([p.score for p in inner])) if inner else 0.0, 3),
                            signals=dict(sig.most_common()), persons=persons, domains=domains, topics=topics))
    return out


def match(new: Material, materials: list[Material], camps: list[Campaign], nets: list[Campaign] | None = None, thr: float = 0.7,
          maybe: float = 0.4, infra: dict | None = None, semantic: bool = False, visual: dict | None = None,
          model: dict | None = None) -> MatchResult:
    """Porównuje nowy materiał ze zbiorem.

    - ten sam przekaz (duplikat/wariant) z wynikiem >= thr: przypisanie do istniejącej kampanii,
    - tylko wspólna infrastruktura >= thr: nowa kampania w znanej sieci operatora,
    - wynik między `maybe` a `thr`: możliwe powiązanie do weryfikacji,
    - poniżej: nowy wzorzec.
    """
    pool = [m for m in materials if m.id != new.id] + [new]
    ts = TextSpace(pool)
    if semantic:
        ts.enable_semantic(pool)
    if visual:
        ts.enable_visual(visual)
    df = doc_freq(pool)
    others = [m for m in pool if m.id != new.id]
    if len(others) > FAISS_FROM:  # wstępny wybór z indeksu FAISS: tekst + klucze strukturalne; reszta par ma wynik 0
        from .vindex import blocking_keys, get_index

        near = {i for i, _ in get_index(others).search(new, FAISS_K)}
        nk = set(blocking_keys(new))
        near |= {m.id for m in others if nk & set(blocking_keys(m))}
        others = [m for m in others if m.id in near]
    prs = sorted((pair(new, m, ts, df, infra, model) for m in others), key=lambda p: -p.score)
    camp_of = {mid: c.id for c in camps for mid in c.members}
    net_of = {mid: c.id for c in (nets or []) for mid in c.members}
    best: dict[str, Pair] = {}
    for p in prs:
        c = camp_of.get(p.b)
        if c and (c not in best or p.score > best[c].score):
            best[c] = p
    ranking = [{"campaign": c, "network": net_of.get(p.b), "score": p.score, "via": p.b, "relation": p.relation,
                "evidence": [e.reason for e in p.evidence[:6]]} for c, p in sorted(best.items(), key=lambda x: -x[1].score)]
    members = {c.id: c.members for c in camps}

    def cname(cid):  # numery kampanii zależą od zbioru, więc zawsze podajemy też materiały
        return f"{cid} [materiały: {', '.join(members.get(cid, []))}]"

    content = [r for r in ranking if r["relation"] in CONTENT_RELATIONS and r["score"] >= thr]
    top = ranking[0] if ranking else None
    assigned = None
    if content:
        assigned = content[0]["campaign"]
        decision = f"przypisano do kampanii {cname(assigned)}" + (f" (sieć {content[0]['network']})" if content[0]["network"] else "")
    elif top and top["score"] >= thr:
        decision = (f"nowy przekaz, ale ta sama infrastruktura co kampania {cname(top['campaign'])}"
                    + (f": prawdopodobnie ten sam operator (sieć {top['network']})" if top["network"] else ""))
    elif top and top["score"] >= maybe:
        decision = f"możliwe powiązanie z {cname(top['campaign'])} (słabe ślady, do weryfikacji przez analityka)"
    else:
        decision = "nowy wzorzec: brak wystarczających wspólnych śladów ze znanymi kampaniami"
    return MatchResult(decision=decision, best_campaign=assigned, best_score=top["score"] if top else 0.0, ranking=ranking, pairs=prs)


def confidence_label(score: float) -> str:
    return "silne" if score >= 0.85 else "umiarkowane" if score >= 0.7 else "słabe" if score >= 0.4 else "brak"
