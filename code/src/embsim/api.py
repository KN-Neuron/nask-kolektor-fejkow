"""Kontrakt integracyjny embsim: jak dodać materiał (z scrapera, folderu, tekstu) i dostać dopasowanie z przesłankami i decyzją.

Nic tu nie wymaga Neo4j: galeria to lista materiałów w pamięci z zapisem do JSONL. Warstwa grafu (Creator, płatnik itd.) może najpierw
sprawdzić dokładne zgodności kluczy (patrz `Decision.extra_shared`), a embsim obsługuje resztę.

    from embsim.api import Gallery, case_from_meta_ad, case_from_folder, case_from_text

    g = Gallery()                             # progi i wagi z zamrożonej konfiguracji (config/embsim/frozen_v3_mixed_pca.json)
    g = Gallery.load("galeria.jsonl")         # albo z pliku
    d = g.add(case_from_meta_ad(rekord))      # decyzja względem dotychczasowej galerii, potem materiał trafia do galerii
    d.verdict                                 # "znana_kampania" | "znany_operator_nowa_kampania" | "nowy_wzorzec"
    d.matches[0].shared, d.matches[0].channels  # przesłanki: wspólne ślady i wynik per kanał
    g.save("galeria.jsonl")

Dodawanie jest przyrostowe: nowy materiał dostaje wiersz TF-IDF ze słownika z ostatniego dopasowania i nie wymusza ponownego liczenia
całości. Dopóki galeria ma ≤ `refit_below` (domyślnie 200) materiałów, pełne dopasowanie (słownik TF-IDF, idf śladów, μ) robi się przy
każdym dodaniu; potem po urośnięciu galerii o `refit_fraction` (domyślnie 10%, min. 25).

Ograniczenia (świadomie, do wiadomości integratora):
  * Punktowanie porównuje zapytanie ze WSZYSTKIMI materiałami galerii (O(N)); do kilku tysięcy działa swobodnie, powyżej potrzebne jest
    blokowanie kandydatów (FAISS dla wektorów + indeks odwrócony dla śladów). To jeszcze nie jest zrobione.
  * Kanały spoza zamrożonej konfiguracji (np. `payer`, `page`, `text_hash` z reklam Mety) NIE wchodzą do wyniku, bo nie były
    oceniane w harnessie; są tylko zwracane jako `extra_shared` (dokładne zgodności) dla warstwy grafu.
  * Progi pochodzą z kalibracji na syntetyce; na prawdziwych danych mogą wymagać ponownej kalibracji.
  * Domyślna konfiguracja `v3_mixed_pca` była dobrana na syntetyce v2 (szum jak w prawdziwym HAR); na prawdziwych kampaniach niesprawdzona.
    Błędne dołączanie nowych wzorców do znanych kampanii zostaje najsłabszym punktem (ok. 0,15–0,19 w teście syntetycznym).
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .bench import Config, load_frozen
from .embed import text_vectors
from .faces import best_match, identify
from .imghash import near_pairs
from .features import Case, load_case, registered
from .score import Corpus, Score

__all__ = ["Case", "Decision", "Gallery", "Match", "case_from_folder", "case_from_meta_ad", "case_from_text", "case_to_dict",
           "case_from_dict"]

FLAGS = ("removed because it didn", "later disabled for not following")
_CHANNEL_PL = {"text": "podobieństwo treści", "text_lex": "podobne brzmienie tekstu", "kit": "ten sam zestaw zasobów strony",
               "scheme": "ten sam schemat parametrów adresu", "host": "wspólna domena", "pixel": "ten sam piksel śledzący",
               "image": "podobny wygląd", "img": "te same obrazy na stronie",
               "infra": "ta sama obsługa domen (serwer nazw, IP, rejestracja)"}
_EXTRA_PL = {"face": "wizerunek", "person": "znana osoba z bazy wizerunków", "dhash": "bardzo podobny obraz", "payer": "ten sam płatnik", "page": "ta sama strona reklamodawcy", "text_hash": "identyczny tekst"}
# Konfiguracja domyślna (progi z kalibracji na syntetyce v2 z szumem jak w HAR): kampania = nakładanie śladów, operator = zawieranie,
# kanał leksykalny, korekta PCA embeddingów, korekta o dostępność dowodu. Starsze: "adj", "lex" (syntetyka v1, gorzej przenoszą się).
DEFAULT_CONFIG = "v4_rare4"
HOST = re.compile(r"^(?:[a-z0-9-]+\.)+[a-z]{2,}$")
# Kanały dokładnych zgodności dokładane do zamrożonej konfiguracji (nie było ich w kalibracji na syntetyce, która nie ma obrazów):
# waga jak pozostałych śladów, „rotujący” (brak wspólnego obrazu nie jest dowodem różnicy, bo często po prostu brak danych).
EXACT_CHANNELS = {"img": 1.0, "infra": 1.0}   # infra: metadane domen (embsim/infra.py), brak danych to nie różnica
AMBIGUITY_MARGIN = 0.05                                          # różnica wyniku do drugiej kampanii, poniżej której pokazujemy obie hipotezy
EVIDENCE_SETS = ("host", "kit", "scheme", "pixel", "img", "infra")      # ślady, które mogą być podstawą decyzji (page, payer, text_hash są metadanymi)


def has_evidence(case: Case) -> bool:
    return bool(case.text.strip()) or any(case.sets.get(k) for k in EVIDENCE_SETS)
DEMO_CALIBRATION = Path(__file__).resolve().parents[2] / "config" / "embsim" / "demo_calibration.json"


LINK_FRAC = 0.8                    # regroup: grupy łączone, gdy średni wynik par między nimi ≥ 0,8 progu kampanii (docs/WYNIKI.md §5a)
META_CAMPAIGN_THRESHOLD = 0.5     # optimum na reklamach Meta w teście po czasie i przyrostowo (docs/WYNIKI.md); progi z syntetyki (0,95) i ze stron (0,725) są tam za wysokie


def demo_thresholds() -> dict:
    """Progi demonstratora skalibrowane na stronach (zob. plik `demo_calibration.json`, pole „skąd”); {} gdy pliku brak."""
    return json.loads(DEMO_CALIBRATION.read_text(encoding="utf-8")).get("thresholds", {}) if DEMO_CALIBRATION.exists() else {}


def case_from_folder(root: str | Path) -> Case:
    """Materiał z folderu w ścieżce demonstratora: bez śladów z pospolitych usług (Google, Meta, CDN), zob. features.load_case."""
    from .infra import enrich

    return enrich(load_case(Path(root), drop_common=True))


def with_exact_channels(cfg: Config) -> Config:
    """Kopia konfiguracji z kanałami EXACT_CHANNELS. e_ref (typowa dostępność dowodu) przeskalowane tak, żeby dla materiałów bez tych
    kanałów korekta o dostępność dawała dokładnie to samo co przed dodaniem kanału (k/n kanałów → k/(n+1), e_ref·n/(n+1))."""
    cfg = copy.deepcopy(cfg)
    for lv, w in (("campaign", cfg.weights_campaign), ("operator", cfg.weights_operator)):
        old = sum(w.values())
        for ch, wt in EXACT_CHANNELS.items():
            w.setdefault(ch, wt)
        if lv in (cfg.e_ref or {}) and old:
            cfg.e_ref[lv] *= old / sum(w.values())
    cfg.rotating = sorted(set(cfg.rotating) | set(EXACT_CHANNELS))
    return cfg


# --------------------------------------------------------------------------------------------------------------------
# materiał <-> słownik JSON (format wymiany)


def case_to_dict(c: Case) -> dict:
    """Format wymiany: {"id", "text", "sets": {kanał: [ślady]}, "meta": {...}}. Kanały zbiorów: host, kit, scheme, pixel (+ własne)."""
    return {"id": c.id, "text": c.text, "sets": {k: sorted(v) for k, v in c.sets.items()}, "meta": c.meta}


def case_from_dict(d: dict) -> Case:
    return Case(id=str(d["id"]), text=d.get("text", "") or "", sets={k: set(v) for k, v in (d.get("sets") or {}).items() if v},
                meta=dict(d.get("meta") or {}))


def case_from_text(id: str, text: str, **sets) -> Case:
    return Case(id=id, text=text, sets={k: set(v) for k, v in sets.items() if v})


def _first(v):
    if isinstance(v, str) and v[:1] in "[{":
        import ast

        try:
            v = ast.literal_eval(v)
        except (ValueError, SyntaxError):
            return v
    return v[0] if isinstance(v, list) and v else v


def case_from_meta_ad(r: dict) -> Case:
    """Rekord z Meta Ad Library (pola jak w ads.jsonl) -> Case.

    Do wyniku wchodzą: tekst (tytuł + treść) i host (domena z podpisu linku). Reklamy usunięte przez Metę nie mają treści ani domeny.
    Dodatkowo (poza wynikiem, tylko jako dokładne przesłanki): payer, page, text_hash.
    """
    body, title, cap = (_first(r.get(k)) for k in ("ad_creative_bodies", "ad_creative_link_titles", "ad_creative_link_captions"))
    flagged = any(f in " ".join(str(_first(r.get(k)) or "") for k in ("ad_creative_bodies", "ad_creative_link_captions")) for f in FLAGS)
    text = "" if flagged else "\n".join(x for x in (title, body) if isinstance(x, str) and x.strip())
    sets: dict[str, set[str]] = {}
    if not flagged and isinstance(cap, str) and HOST.match(cap.lower().strip()):
        sets["host"] = {registered(cap.lower().strip())}
    pays = r.get("beneficiary_payers")
    payers = {p["payer"] for p in pays if isinstance(p, dict) and p.get("payer")} if isinstance(pays, list) else set()
    if payers:
        sets["payer"] = payers
    if r.get("page_id"):
        sets["page"] = {str(r["page_id"])}
    if text.strip():
        sets["text_hash"] = {hashlib.sha1(text.encode()).hexdigest()[:12]}
    meta = {k: r.get(k) for k in ("page_id", "page_name", "ad_creation_time", "ad_delivery_start_time", "ad_delivery_stop_time",
                                  "_query") if r.get(k) is not None}
    meta["flagged_by_meta"] = flagged
    return Case(id=str(r["id"]), text=text, sets=sets, meta=meta)


# --------------------------------------------------------------------------------------------------------------------
# wynik


@dataclass
class Match:
    id: str
    group: str | None                                 # kampania (grupa) tego materiału w galerii
    operator: str | None
    campaign_score: float
    operator_score: float
    evidence: float                                   # ile kanałów faktycznie porównano (0..1)
    channels: dict[str, float] = field(default_factory=dict)
    shared: dict[str, list[str]] = field(default_factory=dict)        # wspólne ślady w kanałach wyniku
    extra_shared: dict[str, list[str]] = field(default_factory=dict)  # dokładne zgodności kanałów spoza wyniku (payer, page...)


@dataclass
class Decision:
    verdict: str
    group: str | None                                 # grupa przypisana (znana kampania) albo None
    operator: str | None
    campaign_score: float
    operator_score: float
    thresholds: dict
    matches: list[Match]
    duplicate_of: str | None = None                   # id już obecne w galerii (nic nie dodano)
    exact_of: str | None = None                       # wszystkie obrazy materiału są w tym materiale galerii (reguła dokładna)
    profile: str | None = None                        # profil progów galerii ("strony", "meta"), z którym wydano werdykt
    alternative: tuple | None = None                  # (kampania, wynik) drugiej kampanii o zbliżonym wyniku (różnica < AMBIGUITY_MARGIN)

    def to_dict(self) -> dict:
        from dataclasses import asdict

        return asdict(self)

    def key_match(self) -> Match | None:
        """Materiał, który uzasadnia werdykt: przy „ten sam operator” ten z najwyższym wynikiem operatora, inaczej najbliższy kampanii."""
        if not self.matches:
            return None
        if self.verdict == "znany_operator_nowa_kampania":
            return max(self.matches, key=lambda m: m.operator_score)
        return self.matches[0]

    def explain(self, top_channels: int = 3) -> str:
        """Wyjaśnienie po polsku dla analityka (dezinformacja/CERT): wniosek, najbliższy materiał, powody, dowody spoza wyniku."""
        t = self.thresholds
        if self.verdict == "brak_danych":
            head = "Brak danych do porównania (ani tekstu, ani śladów infrastruktury, ani obrazów): materiału nie przypisano do żadnej grupy."
        elif self.verdict == "duplikat_id" or self.duplicate_of:
            head = f"Ten materiał ({self.duplicate_of}) jest już w galerii; nic nie dodano."
        elif self.verdict == "znana_kampania" and self.exact_of:
            head = (f"Znana kampania {self.group} (operator {self.operator}): każdy obraz tego materiału jest identyczny (ten sam plik, "
                    f"SHA-256) z obrazem materiału {self.exact_of}, a co najmniej jeden występuje w galerii tylko tam. "
                    f"Wynik podobieństwa {self.campaign_score:.2f} nie był potrzebny.")
        elif self.verdict == "znana_kampania":
            head = (f"Znana kampania {self.group} (operator {self.operator}): wynik {self.campaign_score:.2f}"
                    f" przy progu {t.get('campaign'):.2f}.")
            if self.alternative:
                head += (f" Uwaga, niejednoznaczne: kampania {self.alternative[0]} ma zbliżony wynik {self.alternative[1]:.2f}; "
                         "sprawdź obie hipotezy.")
        elif self.verdict == "znany_operator_nowa_kampania":
            head = (f"Ten sam operator co {self.operator}, ale treść nie pasuje do znanej kampanii: wynik kampanii {self.campaign_score:.2f}"
                    f" (próg {t.get('campaign'):.2f}), wynik operatora {self.operator_score:.2f} (próg {t.get('operator'):.2f}).")
        else:
            head = (f"Nowy wzorzec: najlepszy wynik kampanii {self.campaign_score:.2f} (próg {t.get('campaign') or 0:.2f}),"
                    f" operatora {self.operator_score:.2f}. Nie łączę z żadną znaną grupą.")
        if not self.matches:
            return head
        m = self.key_match()
        lines = [head, f"Najbliższy materiał: {m.id}" + (f" (kampania {m.group}, operator {m.operator})" if m.group else "") + "."]
        ch = sorted(m.channels.items(), key=lambda kv: -kv[1])[:top_channels]
        if ch:
            lines.append("Powody (wynik 0–1 per kanał): " + "; ".join(f"{_CHANNEL_PL.get(k, k)} {v:.2f}" for k, v in ch) + ".")
        for k, v in m.shared.items():
            lines.append(f"Wspólne ślady, {_CHANNEL_PL.get(k, k)}: " + ", ".join(v[:3]) + ("…" if len(v) > 3 else "") + ".")
        for k, v in m.extra_shared.items():
            lines.append(f"Dokładna zgodność poza wynikiem ({_EXTRA_PL.get(k, k)}): " + ", ".join(v[:3]) + ".")
        if m.evidence < 0.999:
            lines.append(f"Porównano {m.evidence:.0%} kanałów wyniku. Gdy porównano mniej kanałów niż typowo, wynik jest korygowany w dół "
                         "(korekta o dostępność dowodu, docs/14), więc np. sam tekst bez śladów strony rzadko wystarcza do połączenia, "
                         "nawet przy podobnej treści.")
        else:
            lines.append("Porównano wszystkie kanały wyniku.")
        return "\n".join(lines)


# --------------------------------------------------------------------------------------------------------------------
# galeria


def _default_embed(model: str):
    return lambda texts: text_vectors(model, list(texts))


PROFILES = {
    "strony": lambda: demo_thresholds(),                                  # HTML, HAR, zrzuty (NASK i syntetyka): próg kampanii 0,725
    "meta": lambda: {"campaign": META_CAMPAIGN_THRESHOLD},                # reklamy z Meta Ad Library: próg kampanii 0,5
}


class Gallery:
    """`profile` ("strony" albo "meta") ustawia progi decyzji dla rodzaju źródła; ten sam profil daje ten sam werdykt w UI, CLI i scraperze,
    a jego nazwa trafia do `Decision.profile`. Jawne `thresholds` mają pierwszeństwo."""

    def __init__(self, config: str | Config = DEFAULT_CONFIG, embed_fn=None, refit_below: int = 200, refit_fraction: float = 0.10,
                 min_refit: int = 25, thresholds: dict | None = None, profile: str | None = None):
        self.cfg = with_exact_channels(config if isinstance(config, Config) else load_frozen(config)[0])
        self.profile = profile
        self.cfg.thresholds.update({**(PROFILES[profile]() if profile else {}), **(thresholds or {})})
        self.embed_fn = embed_fn if embed_fn is not None else _default_embed(self.cfg.model)
        # pełne dopasowanie przy KAŻDYM dodaniu, dopóki galeria ma ≤ refit_below materiałów (mały korpus: słownik i idf z kilku
        # dokumentów byłyby bezwartościowe); potem późne dodawanie i dopasowanie po urośnięciu o refit_fraction (min. min_refit)
        self.refit_below, self.refit_fraction, self.min_refit = refit_below, refit_fraction, min_refit
        self.link_frac = float(os.environ.get("EMBSIM_LINK_FRAC", LINK_FRAC))   # regroup: średnie wiązanie, ułamek progu kampanii (0 = bez)
        self.items: list[dict] = []                   # {"case": Case, "group": str, "operator": str}
        self._ids: set[str] = set()
        self._corp: tuple[Corpus, Corpus] | None = None
        self._fit_n = 0
        self._counter = {"K": 0, "O": 0}

    # ---- dopasowanie korpusu
    def _fit(self) -> None:
        cases = [it["case"] for it in self.items]
        for c in cases:
            c.lex_vec = None                          # po pełnym dopasowaniu wiersze bierzemy z macierzy korpusu
            c.vec_t = None
        mk = lambda w, lv: Corpus(list(cases), None, w, rotating=set(self.cfg.rotating),
                                  adjust_ref=self.cfg.e_ref.get(lv) if lv in self.cfg.adjust_levels else None,
                                  trace_mode=(self.cfg.trace_mode_operator or self.cfg.trace_mode) if lv == "operator" else self.cfg.trace_mode,
                                  combine=self.cfg.combine, embed_fix=self.cfg.embed_fix, hub_frac=self.cfg.hub_frac, hub_abs=self.cfg.hub_abs)
        self._corp = (mk(self.cfg.weights_campaign, "campaign"), mk(self.cfg.weights_operator, "operator"))
        self._fit_n = len(cases)

    def _ensure(self) -> None:
        if self._corp is None and self.items:
            self._fit()

    def _embed(self, c: Case) -> None:
        if c.vec is None and c.text.strip():
            c.vec = np.asarray(self.embed_fn([c.text])[0], dtype=np.float32)

    # ---- zapytanie
    def query(self, case: Case, k: int = 5, exclude_id: str | None = None) -> Decision:
        d = self._query(case, k, exclude_id)
        d.profile = self.profile
        return d

    def _query(self, case: Case, k: int, exclude_id: str | None) -> Decision:
        self._ensure()
        thr = {lv: self.cfg.thresholds.get(lv) for lv in ("campaign", "operator")}
        if not self.items:
            return Decision("nowy_wzorzec", None, None, 0.0, 0.0, thr, [])
        q = copy.deepcopy(case)
        self._embed(q)
        cc, co = self._corp
        qc = cc.prepare(copy.copy(q))
        q = co.prepare(copy.copy(q))
        rows = []
        for it in self.items:
            g = it["case"]
            if exclude_id is not None and g.id == exclude_id:
                continue
            rows.append((cc.score(qc, g), co.score(q, g), it))
        if not rows:
            return Decision("nowy_wzorzec", None, None, 0.0, 0.0, thr, [])
        rows.sort(key=lambda t: -t[0].value)
        best_o = max(rows, key=lambda t: t[1].value)
        rare = self.cfg.op_rare_df
        if rare is not None:                          # operator tylko przy wspólnym rzadkim śladzie (pospolite ślady nie dowodzą wspólnego operatora)
            def has_rare(t):
                return any(co.df[ch].get(x, 0) <= rare for ch, v in t[1].shared.items() if ch in co.df for x in v)
            ok = [t for t in rows if has_rare(t)]
            if ok:
                best_o = max(ok, key=lambda t: t[1].value)
            else:
                best_o = (best_o[0], type(best_o[1])(0.0, 0.0, 0.0, {}, {}), best_o[2])
        scored = {*self.cfg.weights_campaign, *self.cfg.weights_operator}

        def mk(t) -> Match:
            sc, so, it = t
            extra = {ch: sorted(q.sets[ch] & it["case"].sets.get(ch, set()))[:5] for ch in q.sets
                     if ch not in scored and q.sets[ch] & it["case"].sets.get(ch, set())}
            if "face" not in scored and (fm := best_match(q.meta.get("faces"), it["case"].meta.get("faces"))) is not None:
                extra["face"] = [f"ta sama osoba na obrazach (podobieństwo twarzy {fm:.2f})"]      # przesłanka, poza wynikiem (zob. faces.py)
            if (both := sorted(set(identify(q.meta.get("faces"))) & set(identify(it["case"].meta.get("faces"))))):
                extra["person"] = both   # różne zdjęcia tej samej osoby z bazy (faces.py)
            if "dhash" not in scored and (np_ := near_pairs(q.meta.get("dhash"), it["case"].meta.get("dhash"))):
                extra["dhash"] = [f"{a} ≈ {b}" for a, b, _ in np_[:2]]      # ten sam obraz po zmianie rozmiaru lub kompresji
            names = {**it["case"].meta.get("img_names", {}), **q.meta.get("img_names", {})}
            shared = {ch: [names.get(x, x) for x in v] if ch == "img" else v for ch, v in sc.shared.items()}
            return Match(it["case"].id, it["group"], it["operator"], round(sc.value, 4), round(so.value, 4),
                         round(sc.evidence, 3), sc.channels, shared, extra)

        exact = self._exact(q, rows)
        if exact is not None:                         # reguła dokładna: identyczne obrazy wygrywają z podobieństwem
            rows.insert(0, rows.pop(exact))
        top = [mk(t) for t in rows[:k]]
        if all(best_o[2] is not t[2] for t in rows[:k]):    # materiał, który uzasadnia poziom operatora, zawsze na liście przesłanek
            top.append(mk(best_o))
        bc, bo = rows[0], best_o
        if exact is not None:
            return Decision("znana_kampania", bc[2]["group"], bc[2]["operator"], bc[0].value, bo[1].value, thr, top,
                            exact_of=bc[2]["case"].id)
        if thr["campaign"] is not None and bc[0].value >= thr["campaign"]:
            alt = next((t for t in rows if t[2]["group"] != bc[2]["group"]), None)       # druga kampania o zbliżonym wyniku: niejednoznaczność
            ambiguous = (alt[2]["group"], round(alt[0].value, 3)) if alt and alt[0].value >= thr["campaign"] and bc[0].value - alt[0].value < AMBIGUITY_MARGIN else None
            return Decision("znana_kampania", bc[2]["group"], bc[2]["operator"], bc[0].value, bo[1].value, thr, top, alternative=ambiguous)
        if thr["operator"] is not None and bo[1].value >= thr["operator"]:
            return Decision("znany_operator_nowa_kampania", None, bo[2]["operator"], bc[0].value, bo[1].value, thr, top)
        return Decision("nowy_wzorzec", None, None, bc[0].value, bo[1].value, thr, top)

    def _exact(self, q: Case, rows: list) -> int | None:
        """Indeks wiersza, którego materiał zawiera WSZYSTKIE obrazy zapytania (dokładny SHA-256), z co najmniej jednym obrazem
        obecnym w galerii tylko w jednej kampanii. Wspólny obraz sieci (np. ikona z CDN operatora u kilku kampanii) reguły nie uruchomi."""
        qi = q.sets.get("img")
        if not qi:
            return None
        only_img = (not q.text.strip() or q.meta.get("screenshot_only")) and not any(v for k, v in q.sets.items() if k in EVIDENCE_SETS and k != "img")
        if len(qi) < 2 and not only_img:                  # jedno wspólne zdjęcie to zasób (logo, szablon), nie dowód kampanii; wystarczy dopiero
            return None                                   # jako jedyna informacja (zrzut bez tekstu) albo przy kompletnym zestawie ≥ 2 obrazów
        groups: dict[str, set] = {}
        for it in self.items:
            for x in it["case"].sets.get("img", set()) & qi:
                groups.setdefault(x, set()).add(it["group"])
        for i, (_, _, it) in enumerate(rows):
            if qi <= it["case"].sets.get("img", set()) and any(groups.get(x) == {it["group"]} for x in qi):
                return i
        return None

    # ---- dodawanie
    def add(self, case: Case, group: str | None = None, operator: str | None = None, k: int = 5) -> Decision:
        """Decyzja względem dotychczasowej galerii, potem dopisanie. Ten sam `id` drugi raz niczego nie dodaje (idempotentne)."""
        if case.id in self._ids:
            d = self.query(case, k, exclude_id=case.id)
            d.duplicate_of = case.id
            return d
        if not has_evidence(case):                        # sam identyfikator strony nie jest podstawą do utworzenia kampanii ani operatora
            return Decision("brak_danych", None, None, 0.0, 0.0, {lv: self.cfg.thresholds.get(lv) for lv in ("campaign", "operator")}, [])
        d = self.query(case, k)
        if group is None:
            group = d.group if d.verdict == "znana_kampania" else self._new("K")
        if operator is None:
            operator = d.operator if d.verdict in ("znana_kampania", "znany_operator_nowa_kampania") else self._new("O")
        c = copy.deepcopy(case)
        self._embed(c)
        self.items.append({"case": c, "group": group, "operator": operator})
        self._ids.add(c.id)
        grown = len(self.items) - self._fit_n
        if len(self.items) <= self.refit_below or grown >= max(self.min_refit, int(self.refit_fraction * max(self._fit_n, 1))):
            self._fit()
        else:
            for corp in self._corp:                   # bez ponownego dopasowania słownika; liczniki śladów w obu poziomach
                corp.add_late(c)
        d.group, d.operator = d.group or group, d.operator or operator
        return d

    def regroup(self) -> dict:
        """Drugi przebieg po wczytaniu całego zbioru: każdy materiał porównany z resztą pełnej galerii (rzadkość śladów i centrowanie tekstu
        liczone na wszystkich), kampanie i operatorzy policzeni od nowa (spójne składowe krawędzi powyżej progów). Usuwa zależność od
        kolejności wczytywania: przy galerii z 1-2 materiałów pierwsze decyzje zapadały bez tła. Zwraca liczbę kampanii i operatorów."""
        if len(self.items) < 2:
            return {"kampanie": len(self.items), "operatorzy": len(self.items)}
        self._fit()
        ids = [it["case"].id for it in self.items]
        pos = {x: i for i, x in enumerate(ids)}
        pc, po = list(range(len(ids))), list(range(len(ids)))

        def find(p, i):
            while p[i] != i:
                p[i] = p[p[i]]
                i = p[i]
            return i

        edges = []                                    # (wynik, i, j, dokładna): krawędzie kampanii, łączone od najsilniejszej
        for i, it in enumerate(self.items):
            d = self._query(it["case"], 5, ids[i])
            key = d.key_match() if d.verdict == "znany_operator_nowa_kampania" else (d.matches[0] if d.matches else None)
            if key is None or key.id not in pos:
                continue
            j = pos[key.id]
            if d.verdict == "znana_kampania":
                edges.append((d.campaign_score, i, j, d.exact_of is not None))
            to = self.cfg.thresholds.get("operator")
            bo = max(d.matches, key=lambda m: m.operator_score) if d.matches else None
            if to is not None and bo is not None and bo.operator_score >= to and bo.id in pos:   # operator niezależnie od kampanii
                po[find(po, i)] = find(po, pos[bo.id])
        cc, tc = self._corp[0], self.cfg.thresholds.get("campaign") or 0.0
        members = {i: [i] for i in range(len(ids))}
        pair: dict[tuple[int, int], float] = {}

        def sc(x, y):
            k = (x, y) if x < y else (y, x)
            if k not in pair:
                pair[k] = cc.score(self.items[x]["case"], self.items[y]["case"]).value
            return pair[k]

        for s_, i, j, exact in sorted(edges, key=lambda e: -e[0]):
            ri, rj = find(pc, i), find(pc, j)
            if ri == rj:
                continue
            if not exact and self.link_frac and len(members[ri]) + len(members[rj]) > 2:
                # średnie wiązanie: łączymy dwie grupy tylko, gdy przeciętna para między nimi jest blisko progu kampanii; jedna mocna para
                # nie skleja łańcuchem A≈B, B≈C dwóch różnych kampanii (zob. docs/WYNIKI.md §5a)
                mean = sum(sc(x, y) for x in members[ri] for y in members[rj]) / (len(members[ri]) * len(members[rj]))
                if mean < self.link_frac * tc:
                    continue
            pc[ri] = rj
            members[rj] += members.pop(ri)
            po[find(po, i)] = find(po, j)
        for i in range(len(ids)):                     # kampania należy do jednego operatora
            po[find(po, i)] = find(po, find(pc, i))
        kn, on = {}, {}
        for i, it in enumerate(self.items):
            it["group"] = kn.setdefault(find(pc, i), f"K{len(kn) + 1}")
            it["operator"] = on.setdefault(find(po, find(pc, i)), f"O{len(on) + 1}")
        self._counter["K"], self._counter["O"] = len(kn), len(on)
        return {"kampanie": len(kn), "operatorzy": len(on)}

    def _new(self, prefix: str) -> str:
        used = {it["group" if prefix == "K" else "operator"] for it in self.items}
        while True:
            self._counter[prefix] += 1
            name = f"{prefix}{self._counter[prefix]}"
            if name not in used:
                return name

    def __len__(self) -> int:
        return len(self.items)

    # ---- zapis / odczyt
    def save(self, path: str | Path) -> None:
        with Path(path).open("w", encoding="utf-8") as f:
            for it in self.items:
                c = it["case"]
                f.write(json.dumps({"case": case_to_dict(c), "group": it["group"], "operator": it["operator"],
                                    "vec": None if c.vec is None else [round(float(x), 6) for x in c.vec]}, ensure_ascii=False) + "\n")

    @classmethod
    def load(cls, path: str | Path, config: str | Config = DEFAULT_CONFIG, embed_fn=None, **kw) -> "Gallery":
        g = cls(config, embed_fn, **kw)
        for line in Path(path).open(encoding="utf-8"):
            r = json.loads(line)
            c = case_from_dict(r["case"])
            c.vec = None if r.get("vec") is None else np.asarray(r["vec"], dtype=np.float32)
            g.items.append({"case": c, "group": r["group"], "operator": r["operator"]})
            g._ids.add(c.id)
        for prefix, key in (("K", "group"), ("O", "operator")):
            nums = [int(m.group(1)) for it in g.items if (m := re.fullmatch(prefix + r"(\d+)", str(it[key] or "")))]
            g._counter[prefix] = max(nums, default=0)
        return g
