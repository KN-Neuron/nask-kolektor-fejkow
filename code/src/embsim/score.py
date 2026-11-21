"""Podobieństwo ważone, bez uczenia. Jedno wyrażenie:

    S(a, b) = Σ_c  w_c · m_c · s_c(a, b)  /  Σ_c  w_c · m_c

  m_c = 1, gdy OBA materiały mają kanał c (brakujące dane nie karzą wyniku, tylko zmniejszają „dowód”);
        dla kanałów „rotujących” (host, piksel) m_c = 1 tylko, gdy istnieje wspólny ślad: brak wspólnej domeny nie jest
        dowodem różnicy, bo kampanie je wymieniają; kanały trwałe (zestaw strony, schemat adresu) liczą też brak zgodności,
  s_c ∈ [0, 1]:
    - kanał semantyczny (tekst, w przyszłości obraz): (cos − μ) / (1 − μ), obcięte do [0, 1],
      gdzie μ = mediana kosinusów w korpusie (rozkład zerowy liczony z danych, bez etykiet);
    - kanały śladów (piksel, zestaw strony, schemat adresu, host): ważony Jaccard (waga śladu = idf w korpusie) razy
      (1 − exp(−Σ idf wspólnych śladów)), więc ślad pospolity (hub) prawie nic nie waży, a rzadki wspólny ślad waży dużo.
  Wagi w_c są ustalone z góry (DEFAULT_WEIGHTS), jawne i nieuczone.

Korekta o dostępność dowodu (opcjonalna, `adjust_ref` = typowa dostępność przy pełnych danych, z dev):
    λ = min(1, e / e_ref),  S' = max(0, 1 − (1 − S) / λ),  e = Σ w_c [oba mają dane w kanale c] / Σ w_c.
  Im mniej kanałów da się porównać, tym wyższy S jest potrzebny, by przekroczyć ten sam próg (przy λ = 1 nic się nie zmienia).

Każdy wynik niesie rozbicie na kanały i wspólne ślady, czyli przesłanki do pokazania człowiekowi.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .features import Case

DEFAULT_WEIGHTS = {"text": 1.0, "pixel": 1.0, "kit": 1.0, "scheme": 1.0, "host": 1.0}
SEMANTIC = {"text", "image"}
ROTATING = {"host", "pixel"}   # ślady, które kampanie wymieniają (krótko żyjące domeny, piksele): brak zgodności to nie dowód


@dataclass
class Score:
    value: float
    raw: float                                  # wynik przed korektą o dostępność dowodu
    evidence: float                                   # Σ w_c m_c / Σ w_c: ile kanałów faktycznie porównano (0..1)
    channels: dict[str, float] = field(default_factory=dict)
    shared: dict[str, list[str]] = field(default_factory=dict)


class Corpus:
    def __init__(self, cases: list[Case], vecs: np.ndarray | None = None, weights: dict[str, float] | None = None,
                 rotating: set[str] | None = ROTATING, adjust_ref: float | None = None):
        self.rotating = set(rotating or ())
        self.adjust_ref = adjust_ref
        self.cases = cases
        self.w = dict(weights or DEFAULT_WEIGHTS)
        self.n = len(cases)
        for c, v in zip(cases, vecs if vecs is not None else [None] * len(cases)):
            c.vec = v
        self.df: dict[str, dict[str, int]] = {}
        for c in cases:
            for ch, s in c.sets.items():
                d = self.df.setdefault(ch, {})
                for x in s:
                    d[x] = d.get(x, 0) + 1
        self.mu = 0.0
        if vecs is not None and len(vecs) > 1:
            S = np.asarray(vecs) @ np.asarray(vecs).T
            self.mu = float(np.median(S[np.triu_indices(len(vecs), 1)]))

    def idf(self, ch: str, x: str) -> float:
        return math.log((self.n + 1) / (self.df[ch].get(x, 0) + 0.5))

    def channel(self, a: Case, b: Case, ch: str) -> tuple[float | None, list[str]]:
        if ch in SEMANTIC:
            if a.vec is None or b.vec is None:
                return None, []
            return float(np.clip((float(a.vec @ b.vec) - self.mu) / (1 - self.mu), 0, 1)), []
        sa, sb = a.sets.get(ch), b.sets.get(ch)
        if not sa or not sb:
            return None, []
        inter, union = sa & sb, sa | sb
        if ch in self.rotating and not inter:
            return None, []   # brak wspólnego śladu to nie dowód różnicy (domeny i piksele się rotuje): kanał milczy
        num = sum(self.idf(ch, x) for x in inter)
        den = sum(self.idf(ch, x) for x in union)
        # stosunek ważony × nasycenie masy dowodu: pospolity ślad (mała idf) nie daje wysokiego wyniku nawet wtedy, gdy jest jedynym
        return ((num / den) * (1 - math.exp(-num)) if den else 0.0), sorted(inter, key=lambda x: -self.idf(ch, x))[:5]

    def has(self, a: Case, b: Case, ch: str) -> bool:
        """Czy OBA materiały mają dane w kanale (niezależnie od tego, czy cokolwiek się pokrywa)."""
        if ch in SEMANTIC:
            return a.vec is not None and b.vec is not None
        return bool(a.sets.get(ch)) and bool(b.sets.get(ch))

    def availability(self, a: Case, b: Case) -> float:
        """e = Σ w_c · [oba mają kanał c] / Σ w_c: ile dowodu w ogóle da się porównać (0..1)."""
        total = sum(self.w.values())
        return sum(w for ch, w in self.w.items() if self.has(a, b, ch)) / total if total else 0.0

    def score(self, a: Case, b: Case) -> Score:
        num = den = 0.0
        ch_scores, shared = {}, {}
        for ch, w in self.w.items():
            s, sh = self.channel(a, b, ch)
            if s is None:
                continue
            num += w * s
            den += w
            ch_scores[ch] = round(s, 3)
            if sh:
                shared[ch] = sh
        total = sum(self.w.values())
        raw = num / den if den else 0.0
        val = raw
        if self.adjust_ref:
            e = self.availability(a, b)
            lam = min(1.0, e / self.adjust_ref)
            val = max(0.0, 1.0 - (1.0 - raw) / lam) if lam > 0 else 0.0
        return Score(val, raw, den / total if total else 0.0, ch_scores, shared)

    def matrix(self) -> tuple[np.ndarray, np.ndarray]:
        n = len(self.cases)
        S, E = np.zeros((n, n)), np.zeros((n, n))
        for i in range(n):
            for j in range(i, n):
                r = self.score(self.cases[i], self.cases[j])
                S[i, j] = S[j, i] = r.value
                E[i, j] = E[j, i] = r.evidence
        return S, E
