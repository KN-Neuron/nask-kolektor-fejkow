"""Indeks wektorowy FAISS do wyszukiwania kandydatów (zamiast porównywania każdej pary).

Wektor materiału = [tekst: TF-IDF → LSA (128 wymiarów)] ⊕ [klucze strukturalne: domena, piksel, identyfikatory, schemat adresu,
katalogi, usługi, tytuł, reklamodawca… skrót cech (512 wymiarów)], oba znormalizowane. Podobieństwo kosinusowe (iloczyn skalarny w
`IndexFlatIP`; powyżej `IVF_ABOVE` materiałów `IndexIVFFlat`) zwraca najbliższych sąsiadów dla nowego materiału. Do indeksu trafia
wiedza o treści i o strukturze jednocześnie, więc kandydatem jest zarówno ten sam przekaz, jak i ta sama infrastruktura.

Indeks jest trwały (`artifacts/demo/faiss/`): `fejki demo build` go zapisuje, a `match` ładuje; gdy zbiór się zmienił, budowany jest od nowa.
Wynik indeksu to tylko wstępny wybór: o powiązaniu decydują dowody i wyuczony model par.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")  # macOS: FAISS i torch/sklearn ładują osobne libomp

import numpy as np

from ..config import ROOT
from .material import Material
from .similar import fold_pl

DIR = ROOT / "artifacts" / "demo" / "faiss"
IVF_ABOVE = 20_000
TEXT_DIM, KEY_DIM = 128, 512


def _faiss():
    import faiss

    faiss.omp_set_num_threads(1)  # bez tego na macOS zdarza się segfault przy współistnieniu z torch
    return faiss


def blocking_keys(m: Material) -> list[str]:
    """Klucze strukturalne materiału (te same, które służą do blokowania par)."""
    out = []
    for kind, vals in (("d", m.landing_domains), ("px", m.pixel_ids), ("ad", m.ad_ids), ("tr", m.tracker_ids),
                       ("sc", m.url_schemes), ("pf", m.path_prefixes), ("pt", [t for t in m.path_templates if t.count("/") >= 2]),
                       ("th", m.third_party_hosts), ("rd", [r.split(" → ")[-1].split(" ")[0] for r in m.redirects]),
                       ("ct", m.contacts), ("lg", m.logos), ("ti", [t.lower() for t in m.titles if len(t) > 15]),
                       ("av", [x.lower() for x in m.advertisers]), ("pr", [x.lower() for x in m.products])):
        out += [f"{kind}:{v}" for v in vals]
    return out


def _doc(m: Material) -> str:
    return fold_pl(((" ".join(m.titles) + " ") * 3 + m.text)[:60000])


def fingerprint(materials: list[Material]) -> str:
    h = hashlib.sha1()
    for m in sorted(materials, key=lambda x: x.id):
        h.update(m.id.encode())
        h.update(str(len(m.text)).encode())
        h.update("|".join(blocking_keys(m)).encode())
    return h.hexdigest()


class VectorIndex:
    def __init__(self):
        self.ids: list[str] = []
        self.fp = ""
        self.tfidf = self.svd = self.index = None

    def _keys(self, ms: list[Material]) -> np.ndarray:
        from sklearn.feature_extraction import FeatureHasher
        from sklearn.preprocessing import normalize

        X = FeatureHasher(n_features=KEY_DIM, input_type="string", alternate_sign=False).transform([blocking_keys(m) for m in ms])
        return normalize(np.sqrt(X.toarray())).astype("float32")

    def _text(self, ms: list[Material]) -> np.ndarray:
        from sklearn.preprocessing import normalize

        T = self.svd.transform(self.tfidf.transform([_doc(m) for m in ms]))
        return normalize(T).astype("float32")

    def vectors(self, ms: list[Material]) -> np.ndarray:
        from sklearn.preprocessing import normalize

        return normalize(np.hstack([self._text(ms), self._keys(ms)])).astype("float32")

    def fit(self, materials: list[Material]) -> VectorIndex:
        faiss = _faiss()
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer

        self.ids = [m.id for m in materials]
        self.fp = fingerprint(materials)
        self.tfidf = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, max_features=60000, token_pattern=r"(?u)\b[^\W\d_]{3,}\b")
        X = self.tfidf.fit_transform([_doc(m) for m in materials]) if materials else None
        self.svd = TruncatedSVD(n_components=max(2, min(TEXT_DIM, X.shape[0] - 1, X.shape[1] - 1)) if X is not None else 2,
                                random_state=0).fit(X)
        V = self.vectors(materials)
        d = V.shape[1]
        if len(materials) > IVF_ABOVE:
            q = faiss.IndexFlatIP(d)
            self.index = faiss.IndexIVFFlat(q, d, int(4 * len(materials) ** 0.5), faiss.METRIC_INNER_PRODUCT)
            self.index.train(V)
            self.index.nprobe = 16
        else:
            self.index = faiss.IndexFlatIP(d)
        self.index.add(V)
        return self

    def search(self, m: Material, k: int = 50) -> list[tuple[str, float]]:
        """k najbliższych materiałów (bez samego siebie) z podobieństwem kosinusowym."""
        k = min(k + 1, len(self.ids))
        sims, idx = self.index.search(self.vectors([m]), k)
        return [(self.ids[j], float(s)) for s, j in zip(sims[0], idx[0], strict=True) if j >= 0 and self.ids[j] != m.id]

    def neighbours(self, materials: list[Material], k: int = 12) -> set[tuple[str, str]]:
        """Pary (a, b) z k najbliższych sąsiadów każdego materiału: zastępuje pętlę O(n²)."""
        V = self.vectors(materials)
        sims, idx = self.index.search(V, min(k + 1, len(self.ids)))
        out = set()
        for i, m in enumerate(materials):
            for s, j in zip(sims[i], idx[i], strict=True):
                if j >= 0 and self.ids[j] != m.id and s > 0:
                    out.add(tuple(sorted((m.id, self.ids[j]))))
        return out

    def save(self, d: Path = DIR) -> Path:
        faiss = _faiss()
        import joblib

        d.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(d / "materialy.faiss"))
        joblib.dump({"ids": self.ids, "fp": self.fp, "tfidf": self.tfidf, "svd": self.svd}, d / "meta.joblib")
        return d

    @classmethod
    def load(cls, d: Path = DIR) -> VectorIndex | None:
        faiss = _faiss()
        import joblib

        if not (d / "materialy.faiss").exists() or not (d / "meta.joblib").exists():
            return None
        o = cls()
        meta = joblib.load(d / "meta.joblib")
        o.ids, o.fp, o.tfidf, o.svd = meta["ids"], meta["fp"], meta["tfidf"], meta["svd"]
        o.index = faiss.read_index(str(d / "materialy.faiss"))
        return o


_CACHE: dict[str, VectorIndex] = {}


def get_index(materials: list[Material], persist: bool = False) -> VectorIndex:
    """Indeks dla danego zbioru: z pamięci, z dysku (gdy zbiór się zgadza) albo budowany od nowa."""
    fp = fingerprint(materials)
    if fp in _CACHE:
        return _CACHE[fp]
    vi = VectorIndex.load()
    if vi is None or vi.fp != fp:
        vi = VectorIndex().fit(materials)
        if persist:
            vi.save()
    _CACHE[fp] = vi
    return vi
