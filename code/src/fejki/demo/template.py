"""Schemat perswazji ponad tematami: embeddingi fragmentów tekstu + LEACE usuwające temat (hipoteza projektu).

Przebieg:
1. tekst materiału (strona + OCR, bez adresów) dzielimy na fragmenty ~400 znaków;
2. fragmenty kodujemy zamrożonym enkoderem wielojęzycznym (bge-m3; cache embeddingów na dysku);
3. każdy fragment dostaje etykietę TEMATU ze słownika (`material.topics`), nigdy etykietę kampanii/sieci;
4. LEACE dopasowane do tematu usuwa liniowo informację o temacie; kontrola: usunięcie losowej podprzestrzeni tego samego rzędu;
5. wektor materiału = średnia fragmentów (po normalizacji).

Walidacja bez cyrkularności: sieci (operatorzy) pochodzą z infrastruktury i śledzenia, a ten kanał widzi tylko tekst.
Teza jest potwierdzona, gdy po LEACE materiały tej samej sieci o RÓŻNYCH tematach są bliżej siebie niż przed LEACE
i niż po kontroli losowej, a odstęp do materiałów spoza sieci rośnie.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import numpy as np

from ..config import ROOT
from .material import Material, topics

CACHE = ROOT / "artifacts" / "demo" / "emb"
MODEL = "BAAI/bge-m3"


def chunks(m: Material, size: int = 400, limit: int = 40) -> list[str]:
    text = " ".join(m.titles) + ". " + m.text
    text = re.sub(r"https?://\S+|www\.\S+|\b[\w-]+\.(?:pl|com|org|live|pro|xyz|top|icu|info|net|media)\b", " ", text)
    sents = re.split(r"(?<=[.!?])\s+", " ".join(text.split()))
    out, cur = [], ""
    for s in sents:
        if len(cur) + len(s) > size and cur:
            out.append(cur.strip())
            cur = ""
        cur += " " + s
    if cur.strip():
        out.append(cur.strip())
    out = [c for c in out if len(c) >= 60]
    if len(out) > limit:  # równomiernie z całej strony, nie tylko z początku
        idx = np.linspace(0, len(out) - 1, limit).astype(int)
        out = [out[i] for i in idx]
    return out


def chunk_topic(text: str) -> str:
    t = topics(text)
    return next(iter(t)) if t else "inne"


_MODEL = None


def encode(texts: list[str], model: str = MODEL) -> np.ndarray:
    """Embeddingi z cache (jeden plik .npy na fragment, klucz = sha1 modelu i tekstu)."""
    global _MODEL
    CACHE.mkdir(parents=True, exist_ok=True)
    keys = [hashlib.sha1((model + "\n" + t).encode()).hexdigest() for t in texts]
    out: list[np.ndarray | None] = [None] * len(texts)
    todo = []
    for i, k in enumerate(keys):
        p = CACHE / f"{k}.npy"
        if p.exists():
            out[i] = np.load(p)
        else:
            todo.append(i)
    if todo:
        if _MODEL is None:
            if not model_available(model):
                raise RuntimeError(f"model {model} nie jest pobrany; użyj encoder='lsa' albo pobierz model świadomie")
            from sentence_transformers import SentenceTransformer

            from ..config import pick_device

            _MODEL = SentenceTransformer(model, device=pick_device("auto"))
            _MODEL.max_seq_length = 256
        X = _MODEL.encode([texts[i] for i in todo], batch_size=16, normalize_embeddings=True, show_progress_bar=False)
        for j, i in enumerate(todo):
            np.save(CACHE / f"{keys[i]}.npy", X[j])
            out[i] = X[j]
    return np.vstack(out) if out else np.zeros((0, 1024))


def encode_lsa(texts: list[str], dim: int = 128, seed: int = 1) -> np.ndarray:
    """Enkoder offline: TF-IDF słów (1–2) na tekście bez polskich znaków + SVD. Słabszy semantycznie niż bge-m3,
    ale bez pobierania modelu; LEACE działa na dowolnych wektorach."""
    from sklearn.decomposition import TruncatedSVD
    from sklearn.feature_extraction.text import TfidfVectorizer

    from .persuasion import fold

    T = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1, token_pattern=r"(?u)\b[^\W\d_]{3,}\b").fit_transform(
        [fold(t) for t in texts])
    k = max(2, min(dim, T.shape[0] - 1, T.shape[1] - 1))
    X = TruncatedSVD(n_components=k, random_state=seed).fit_transform(T)
    return _l2(X)


def model_available(model: str = MODEL) -> bool:
    """Czy model jest już na dysku (żeby nie uruchomić po cichu pobierania ~2 GB)."""
    try:
        from huggingface_hub import snapshot_download

        snapshot_download(model, local_files_only=True)
        return True
    except Exception:
        return False


def _l2(X: np.ndarray) -> np.ndarray:
    return X / np.maximum(np.linalg.norm(X, axis=1, keepdims=True), 1e-9)


def _random_erase(X: np.ndarray, rank: int, seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    Q, _ = np.linalg.qr(rng.standard_normal((X.shape[1], max(1, rank))))
    return X - (X @ Q) @ Q.T


class TemplateSpace:
    """Wektory materiałów w trzech wariantach: surowe, po LEACE (temat usunięty), kontrola losowa (ten sam rząd)."""

    def __init__(self, materials: list[Material], fit_ids: set[str] | None = None, seed: int = 1, encoder: str = "lsa"):
        """encoder: "lsa" (TF-IDF + SVD, offline, bez pobierania modelu) albo "bge-m3" (wymaga modelu na dysku)."""
        try:
            import torch
            from concept_erasure import LeaceEraser
        except ImportError:  # obraz podstawowy bez części badawczej: bez LEACE (warianty „LEACE” = surowe)
            torch = LeaceEraser = None
        self.leace_available = torch is not None
        self.ids = [m.id for m in materials]
        self.encoder = encoder
        self.chunks = {m.id: chunks(m) for m in materials}
        flat = [(m.id, c) for m in materials for c in self.chunks[m.id]]
        self.chunk_ids = [x[0] for x in flat]
        self.chunk_topics = [chunk_topic(x[1]) for x in flat]
        texts = [x[1] for x in flat]
        if not flat:
            X = np.zeros((0, 8))
        elif encoder == "lsa":
            X = encode_lsa(texts)
        else:
            X = encode(texts)
        # LEACE dopasowane tylko na fragmentach z `fit_ids` (np. bez materiału, który testujemy) i tylko do etykiet tematu
        fit = [i for i, mid in enumerate(self.chunk_ids) if fit_ids is None or mid in fit_ids]
        classes = sorted({self.chunk_topics[i] for i in fit})
        self.topic_classes = classes
        if len(classes) >= 2 and self.leace_available:
            z = torch.nn.functional.one_hot(torch.tensor([classes.index(self.chunk_topics[i]) for i in fit]), len(classes)).float()
            er = LeaceEraser.fit(torch.tensor(X[fit], dtype=torch.float32), z)
            with torch.no_grad():
                Xl = er(torch.tensor(X, dtype=torch.float32)).numpy()
            self.rank = len(classes) - 1
        else:
            Xl, self.rank = X.copy(), 0
        Xr = _random_erase(X, self.rank, seed)
        self.X = {"surowe": self._agg(X), "LEACE (bez tematu)": self._agg(Xl), "kontrola losowa": self._agg(Xr)}
        self.chunk_X = {"surowe": X, "LEACE (bez tematu)": Xl}

    def _agg(self, X: np.ndarray) -> dict[str, np.ndarray]:
        out = {}
        for mid in self.ids:
            rows = [i for i, c in enumerate(self.chunk_ids) if c == mid]
            if rows:
                out[mid] = _l2(X[rows]).mean(axis=0)
        return {k: v / max(np.linalg.norm(v), 1e-9) for k, v in out.items()}

    def sim(self, a: str, b: str, variant: str = "LEACE (bez tematu)") -> float | None:
        V = self.X[variant]
        if a not in V or b not in V:
            return None
        return float(V[a] @ V[b])

    def matrix(self, variant: str) -> tuple[list[str], np.ndarray]:
        ids = [i for i in self.ids if i in self.X[variant]]
        V = np.vstack([self.X[variant][i] for i in ids]) if ids else np.zeros((0, 1))
        return ids, V @ V.T


def separation(space: TemplateSpace, groups: dict[str, str], main_topic: dict[str, str]) -> list[dict]:
    """Dla każdego wariantu: średnie podobieństwo par w tej samej grupie (ogółem i przy RÓŻNYM temacie) i par z różnych grup.

    `groups`: materiał → grupa (np. sieć z infrastruktury); materiały bez pary w grupie nie wchodzą do „w grupie”.
    Pary-duplikaty (podobieństwo surowe ≥ 0,95) pomijamy we wszystkich wariantach.
    """
    rows = []
    ids0, S0 = space.matrix("surowe")
    dupes = {(ids0[i], ids0[j]) for i in range(len(ids0)) for j in range(i + 1, len(ids0)) if S0[i, j] >= 0.95}
    for variant in space.X:
        ids, S = space.matrix(variant)
        same, same_cross, diff = [], [], []
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a, b = ids[i], ids[j]
                if (a, b) in dupes:  # duplikaty (np. ta sama strona na dwóch domenach) zawyżałyby średnią
                    continue
                if groups.get(a) is not None and groups.get(a) == groups.get(b):
                    same.append(S[i, j])
                    if main_topic.get(a) != main_topic.get(b):
                        same_cross.append(S[i, j])
                else:
                    diff.append(S[i, j])
        mean = lambda x: round(float(np.mean(x)), 3) if x else None  # noqa: E731
        rows.append({"wariant": variant, "ta sama sieć": mean(same), "ta sama sieć, inny temat": mean(same_cross),
                     "różne sieci": mean(diff),
                     "odstęp (ta sama − różne)": round(mean(same) - mean(diff), 3) if same and diff else None,
                     "pary w sieci": len(same), "w tym międzytematowe": len(same_cross)})
    return rows


def project_2d(space: TemplateSpace, variant: str) -> dict[str, tuple[float, float]]:
    """Rzut 2D (PCA) wektorów materiałów do wykresu."""
    ids, _ = space.matrix(variant)
    if len(ids) < 3:
        return {i: (0.0, 0.0) for i in ids}
    V = np.vstack([space.X[variant][i] for i in ids])
    V = V - V.mean(axis=0)
    U, s, _ = np.linalg.svd(V, full_matrices=False)
    P = U[:, :2] * s[:2]
    return {i: (float(P[k, 0]), float(P[k, 1])) for k, i in enumerate(ids)}


def save_dir() -> Path:
    p = ROOT / "artifacts" / "demo" / "template"
    p.mkdir(parents=True, exist_ok=True)
    return p
