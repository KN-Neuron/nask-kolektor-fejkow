"""Podobieństwo ważone, bez uczenia. Jedno wyrażenie:

    S(a, b) = Σ_c  w_c · m_c · s_c(a, b)  /  Σ_c  w_c · m_c

  m_c = 1, gdy OBA materiały mają kanał c (brakujące dane nie karzą wyniku, tylko zmniejszają „dowód”);
        dla kanałów „rotujących” (host, piksel) m_c = 1 tylko, gdy istnieje wspólny ślad: brak wspólnej domeny nie jest
        dowodem różnicy, bo kampanie je wymieniają; kanały trwałe (zestaw strony, schemat adresu) liczą też brak zgodności,
  s_c ∈ [0, 1]:
    - kanał leksykalny `text_lex` (opcjonalny, wagi LEX_WEIGHTS): to samo dla kosinusa TF-IDF znaków (bez modelu);
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
LEX_WEIGHTS = {**DEFAULT_WEIGHTS, "text_lex": 1.0}   # + kanał leksykalny: TF-IDF znaków (bez modelu), obok semantycznego `text`
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
                 rotating: set[str] | None = ROTATING, adjust_ref: float | None = None, trace_mode: str = "jaccard",
                 combine: str = "mean", embed_fix: str = "none"):
        self.rotating = set(rotating or ())
        self.adjust_ref = adjust_ref
        assert trace_mode in ("jaccard", "contain", "overlap") and combine in ("mean", "noisy_or")
        assert embed_fix in ("none", "center", "abtt1")
        self.trace_mode, self.combine, self.embed_fix = trace_mode, combine, embed_fix
        self._mean = self._pc = None
        self.cases = cases
        self.w = dict(weights or DEFAULT_WEIGHTS)
        self.n = len(cases)
        if vecs is not None:                              # None = zostaw wektory ustawione w Case (np. galeria)
            for c, v in zip(cases, vecs):
                c.vec = v
        self.df: dict[str, dict[str, int]] = {}
        for c in cases:
            for ch, s in c.sets.items():
                d = self.df.setdefault(ch, {})
                for x in s:
                    d[x] = d.get(x, 0) + 1
        self.lex = None                                   # macierz kosinusów TF-IDF (n×n) albo None (duże korpusy: liczone na żądanie)
        self.mu_lex = 0.0
        self._tfidf = None                                # dopasowany TfidfVectorizer (do zapytań spoza korpusu)
        self._X = None                                    # rzadka macierz TF-IDF korpusu
        if self.w.get("text_lex", 0) > 0:
            self._fit_lexical()
        self._fit_embed_fix()
        self.mu = 0.0
        have = [self._sv(c) for c in cases if self._sv(c) is not None]
        if len(have) > 1:                                 # μ: mediana kosinusów (duże korpusy: z losowej podpróby)
            if len(have) > 1500:
                have = [have[i] for i in np.random.default_rng(0).choice(len(have), size=1500, replace=False)]
            S = np.asarray(have) @ np.asarray(have).T
            self.mu = float(np.median(S[np.triu_indices(len(have), 1)]))

    def _fit_lexical(self) -> None:
        """TF-IDF n-gramów znaków (3–5) na tekstach korpusu, bez etykiet i bez modelu. Wynik: kosinus znormalizowany jak kanał tekstowy."""
        from sklearn.feature_extraction.text import TfidfVectorizer

        idx = [i for i, c in enumerate(self.cases) if c.text.strip()]
        if len(idx) < 2:
            return
        X = vec = None
        for min_df in (2, 1):                             # małe korpusy: bez progu częstości
            try:
                vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=min_df, sublinear_tf=True)
                X = vec.fit_transform([self.cases[i].text for i in idx])
                break
            except ValueError:
                continue
        if X is None:
            return
        for r, i in enumerate(idx):
            self.cases[i].lex_i = r
        self._tfidf, self._X = vec, X
        if X.shape[0] <= 1500:                            # małe korpusy: pełna macierz (szybkie macierze w harnessie)
            self.lex = (X @ X.T).toarray()
            iu = np.triu_indices(self.lex.shape[0], 1)
            self.mu_lex = float(np.median(self.lex[iu])) if len(iu[0]) else 0.0
        else:                                             # duże: μ z losowej podpróby wierszy, reszta na żądanie
            sub = np.random.default_rng(0).choice(X.shape[0], size=1500, replace=False)
            S = (X[sub] @ X[sub].T).toarray()
            self.mu_lex = float(np.median(S[np.triu_indices(len(sub), 1)]))

    def _fit_embed_fix(self) -> None:
        """Korekta anizotropii embeddingów (bez etykiet): odjęcie średniej korpusu (`center`) i usunięcie pierwszej głównej składowej
        (`abtt1`, „all-but-the-top”). Średnia i składowa zostają zapamiętane, więc nowy materiał jest korygowany tak samo."""
        if self.embed_fix == "none":
            return
        have = [c for c in self.cases if c.vec is not None]
        if len(have) < 3:
            return
        X = np.stack([np.asarray(c.vec, dtype=np.float64) for c in have])
        if len(X) > 5000:
            X = X[np.random.default_rng(0).choice(len(X), size=5000, replace=False)]
        self._mean = X.mean(0)
        if self.embed_fix == "abtt1":
            self._pc = np.linalg.svd(X - self._mean, full_matrices=False)[2][0]
        for c in have:
            c.vec_t = self._fix(c.vec)

    def _fix(self, v):
        x = np.asarray(v, dtype=np.float64) - self._mean
        if self._pc is not None:
            x = x - (x @ self._pc) * self._pc
        n = np.linalg.norm(x)
        return (x / n if n > 1e-9 else x).astype(np.float32)

    @staticmethod
    def _sv(c: Case):
        return c.vec_t if c.vec_t is not None else c.vec

    def _lex_row(self, c: Case):
        if c.lex_vec is not None:
            return c.lex_vec
        return self._X[c.lex_i] if (self._X is not None and c.lex_i is not None) else None

    def prepare(self, q: Case) -> Case:
        """Przygotowuje materiał spoza korpusu do punktowania względem tego korpusu (wiersz TF-IDF z już dopasowanego słownika)."""
        if self._tfidf is not None and q.text.strip():
            q.lex_vec = self._tfidf.transform([q.text])
        if self._mean is not None and q.vec is not None:
            q.vec_t = self._fix(q.vec)
        return q

    def add_late(self, c: Case) -> Case:
        """Dodaje materiał do korpusu BEZ ponownego dopasowania (słownik TF-IDF, idf i μ zostają z ostatniego dopasowania)."""
        self.cases.append(self.prepare(c))
        return c

    def idf(self, ch: str, x: str) -> float:
        return math.log((self.n + 1) / (self.df[ch].get(x, 0) + 0.5))

    def channel(self, a: Case, b: Case, ch: str) -> tuple[float | None, list[str]]:
        if ch == "text_lex":
            ra, rb = self._lex_row(a), self._lex_row(b)
            if ra is None or rb is None:
                return None, []
            if self.lex is not None and a.lex_vec is None and b.lex_vec is None:
                cos = self.lex[a.lex_i, b.lex_i]
            else:
                cos = float(ra.multiply(rb).sum())
            return float(np.clip((cos - self.mu_lex) / (1 - self.mu_lex), 0, 1)), []
        if ch in SEMANTIC:
            va, vb = self._sv(a), self._sv(b)
            if va is None or vb is None:
                return None, []
            return float(np.clip((float(va @ vb) - self.mu) / (1 - self.mu), 0, 1)), []
        sa, sb = a.sets.get(ch), b.sets.get(ch)
        if not sa or not sb:
            return None, []
        inter, union = sa & sb, sa | sb
        if ch in self.rotating and not inter:
            return None, []   # brak wspólnego śladu to nie dowód różnicy (domeny i piksele się rotuje): kanał milczy
        top = sorted(inter, key=lambda x: -self.idf(ch, x))[:5]
        if self.trace_mode == "overlap":                   # tylko dowody dodatnie: noisy-OR po wspólnych śladach, bez kary za resztę
            if not inter:
                return None, []
            return 1.0 - float(np.prod([math.exp(-self.idf(ch, x)) for x in inter])), top
        if self.trace_mode == "contain":                   # zawieranie: wspólna waga / mniejsza z wag zbiorów (bez rozcieńczenia
            wa = sum(self.idf(ch, x) for x in sa)          # przez to, że jeden zrzut ma więcej żądań)
            wb = sum(self.idf(ch, x) for x in sb)
            num = sum(self.idf(ch, x) for x in inter)
            den = min(wa, wb)
            return ((num / den) * (1 - math.exp(-num)) if den > 1e-9 else 0.0), top
        num = sum(self.idf(ch, x) for x in inter)
        den = sum(self.idf(ch, x) for x in union)
        # stosunek ważony × nasycenie masy dowodu: pospolity ślad (mała idf) nie daje wysokiego wyniku nawet wtedy, gdy jest jedynym
        return ((num / den) * (1 - math.exp(-num)) if den else 0.0), sorted(inter, key=lambda x: -self.idf(ch, x))[:5]

    def has(self, a: Case, b: Case, ch: str) -> bool:
        """Czy OBA materiały mają dane w kanale (niezależnie od tego, czy cokolwiek się pokrywa)."""
        if ch == "text_lex":
            return self._lex_row(a) is not None and self._lex_row(b) is not None
        if ch in SEMANTIC:
            return self._sv(a) is not None and self._sv(b) is not None
        return bool(a.sets.get(ch)) and bool(b.sets.get(ch))

    def availability(self, a: Case, b: Case) -> float:
        """e = Σ w_c · [oba mają kanał c] / Σ w_c: ile dowodu w ogóle da się porównać (0..1)."""
        total = sum(self.w.values())
        return sum(w for ch, w in self.w.items() if self.has(a, b, ch)) / total if total else 0.0

    def score(self, a: Case, b: Case) -> Score:
        num = den = 0.0
        ch_scores, shared = {}, {}
        wmax = max(self.w.values()) if self.w else 1.0
        keep = 1.0                                            # iloczyn (1 − w·s) dla łączenia noisy-OR
        for ch, w in self.w.items():
            s, sh = self.channel(a, b, ch)
            if s is None:
                continue
            num += w * s
            den += w
            keep *= 1.0 - (w / wmax) * s
            ch_scores[ch] = round(s, 3)
            if sh:
                shared[ch] = sh
        total = sum(self.w.values())
        raw = (num / den if den else 0.0) if self.combine == "mean" else (1.0 - keep if den else 0.0)
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
