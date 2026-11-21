"""Kontrakt integracyjny embsim: jak dodać materiał (z scrapera, folderu, tekstu) i dostać dopasowanie z przesłankami i decyzją.

Nic tu nie wymaga Neo4j: galeria to lista materiałów w pamięci z zapisem do JSONL. Warstwa grafu (Creator, płatnik itd.) może najpierw
sprawdzić dokładne zgodności kluczy (patrz `Decision.extra_shared`), a embsim obsługuje resztę.

    from embsim.api import Gallery, case_from_meta_ad, case_from_folder, case_from_text

    g = Gallery("adj")                        # progi i wagi z zamrożonej konfiguracji (artifacts/bench/frozen_adj.json)
    g = Gallery.load("galeria.jsonl", "adj")  # albo z pliku
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
  * Domyślna konfiguracja `adj` (korekta o dostępność dowodu) ma mniej fałszywych połączeń nowych wzorców niż `lex`; `lex` lepiej
    grupuje znane kampanie, ale zbyt często dołącza nowe wzorce do znanych (zob. wyniki w harnessie).
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .bench import Config, load_frozen
from .embed import text_vectors
from .features import Case, load_case as case_from_folder, registered
from .score import Corpus, Score

__all__ = ["Case", "Decision", "Gallery", "Match", "case_from_folder", "case_from_meta_ad", "case_from_text", "case_to_dict",
           "case_from_dict"]

FLAGS = ("removed because it didn", "later disabled for not following")
_CHANNEL_PL = {"text": "podobieństwo treści", "text_lex": "podobne brzmienie tekstu", "kit": "ten sam zestaw zasobów strony",
               "scheme": "ten sam schemat parametrów adresu", "host": "wspólna domena", "pixel": "ten sam piksel śledzący",
               "image": "podobny wygląd"}
_EXTRA_PL = {"payer": "ten sam płatnik", "page": "ta sama strona reklamodawcy", "text_hash": "identyczny tekst"}
HOST = re.compile(r"^(?:[a-z0-9-]+\.)+[a-z]{2,}$")


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

    def to_dict(self) -> dict:
        from dataclasses import asdict

        return asdict(self)

    def explain(self, top_channels: int = 3) -> str:
        """Wyjaśnienie po polsku dla analityka (dezinformacja/CERT): wniosek, najbliższy materiał, powody, dowody spoza wyniku."""
        t = self.thresholds
        if self.verdict == "duplikat_id" or self.duplicate_of:
            head = f"Ten materiał ({self.duplicate_of}) jest już w galerii; nic nie dodano."
        elif self.verdict == "znana_kampania":
            head = (f"Znana kampania {self.group} (operator {self.operator}): wynik {self.campaign_score:.2f}"
                    f" przy progu {t.get('campaign'):.2f}.")
        elif self.verdict == "znany_operator_nowa_kampania":
            head = (f"Ten sam operator co {self.operator}, ale treść nie pasuje do znanej kampanii: wynik kampanii {self.campaign_score:.2f}"
                    f" (próg {t.get('campaign'):.2f}), wynik operatora {self.operator_score:.2f} (próg {t.get('operator'):.2f}).")
        else:
            head = (f"Nowy wzorzec: najlepszy wynik kampanii {self.campaign_score:.2f} (próg {t.get('campaign') or 0:.2f}),"
                    f" operatora {self.operator_score:.2f}. Nie łączę z żadną znaną grupą.")
        if not self.matches:
            return head
        m = self.matches[0]
        lines = [head, f"Najbliższy materiał: {m.id}" + (f" (kampania {m.group}, operator {m.operator})" if m.group else "") + "."]
        ch = sorted(m.channels.items(), key=lambda kv: -kv[1])[:top_channels]
        if ch:
            lines.append("Powody (wynik 0–1 per kanał): " + "; ".join(f"{_CHANNEL_PL.get(k, k)} {v:.2f}" for k, v in ch) + ".")
        for k, v in m.shared.items():
            lines.append(f"Wspólne ślady, {_CHANNEL_PL.get(k, k)}: " + ", ".join(v[:3]) + ("…" if len(v) > 3 else "") + ".")
        for k, v in m.extra_shared.items():
            lines.append(f"Dokładna zgodność poza wynikiem ({_EXTRA_PL.get(k, k)}): " + ", ".join(v[:3]) + ".")
        lines.append(f"Porównano {m.evidence:.0%} kanałów wyniku; brakujące dane obniżają pewność, nie wynik.")
        return "\n".join(lines)


# --------------------------------------------------------------------------------------------------------------------
# galeria


def _default_embed(model: str):
    return lambda texts: text_vectors(model, list(texts))


class Gallery:
    def __init__(self, config: str | Config = "adj", embed_fn=None, refit_below: int = 200, refit_fraction: float = 0.10,
                 min_refit: int = 25):
        self.cfg = config if isinstance(config, Config) else load_frozen(config)[0]
        self.embed_fn = embed_fn if embed_fn is not None else _default_embed(self.cfg.model)
        # pełne dopasowanie przy KAŻDYM dodaniu, dopóki galeria ma ≤ refit_below materiałów (mały korpus: słownik i idf z kilku
        # dokumentów byłyby bezwartościowe); potem późne dodawanie i dopasowanie po urośnięciu o refit_fraction (min. min_refit)
        self.refit_below, self.refit_fraction, self.min_refit = refit_below, refit_fraction, min_refit
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
        mk = lambda w, lv: Corpus(list(cases), None, w, rotating=set(self.cfg.rotating),
                                  adjust_ref=self.cfg.e_ref.get(lv) if lv in self.cfg.adjust_levels else None)
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
        self._ensure()
        thr = {lv: self.cfg.thresholds.get(lv) for lv in ("campaign", "operator")}
        if not self.items:
            return Decision("nowy_wzorzec", None, None, 0.0, 0.0, thr, [])
        q = copy.deepcopy(case)
        self._embed(q)
        cc, co = self._corp
        qc = cc.prepare(copy.copy(q))
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
        scored = {*self.cfg.weights_campaign, *self.cfg.weights_operator}

        def mk(t) -> Match:
            sc, so, it = t
            extra = {ch: sorted(q.sets[ch] & it["case"].sets.get(ch, set()))[:5] for ch in q.sets
                     if ch not in scored and q.sets[ch] & it["case"].sets.get(ch, set())}
            return Match(it["case"].id, it["group"], it["operator"], round(sc.value, 4), round(so.value, 4),
                         round(sc.evidence, 3), sc.channels, sc.shared, extra)

        top = [mk(t) for t in rows[:k]]
        bc, bo = rows[0], best_o
        if thr["campaign"] is not None and bc[0].value >= thr["campaign"]:
            return Decision("znana_kampania", bc[2]["group"], bc[2]["operator"], bc[0].value, bo[1].value, thr, top)
        if thr["operator"] is not None and bo[1].value >= thr["operator"]:
            return Decision("znany_operator_nowa_kampania", None, bo[2]["operator"], bc[0].value, bo[1].value, thr, top)
        return Decision("nowy_wzorzec", None, None, bc[0].value, bo[1].value, thr, top)

    # ---- dodawanie
    def add(self, case: Case, group: str | None = None, operator: str | None = None, k: int = 5) -> Decision:
        """Decyzja względem dotychczasowej galerii, potem dopisanie. Ten sam `id` drugi raz niczego nie dodaje (idempotentne)."""
        if case.id in self._ids:
            d = self.query(case, k, exclude_id=case.id)
            d.duplicate_of = case.id
            return d
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
            self._corp[0].add_late(c)                 # bez ponownego dopasowania słownika
        d.group, d.operator = d.group or group, d.operator or operator
        return d

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
    def load(cls, path: str | Path, config: str | Config = "adj", embed_fn=None, **kw) -> "Gallery":
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
