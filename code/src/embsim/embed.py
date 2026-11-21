"""Embedder multimodalny (domyślnie Qwen3-VL-Embedding). Wektory L2-znormalizowane, cache na dysku."""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
from PIL import Image

DEFAULT_MODEL = "Qwen/Qwen3-VL-Embedding-2B"
DEFAULT_PROMPT = "Represent this scam ad or landing page so that materials from the same campaign are close."
MAX_SIDE = 1024
CACHE = Path(__file__).resolve().parents[2] / "data" / "emb_mm"


def _load_image(p: Path) -> Image.Image:
    im = Image.open(p).convert("RGB")
    im.thumbnail((MAX_SIDE, MAX_SIDE))
    return im


class Embedder:
    def __init__(self, model: str = DEFAULT_MODEL, prompt: str = DEFAULT_PROMPT, device: str | None = None):
        self.name, self.prompt, self.device = model, prompt, device
        self._m = None

    @property
    def model(self):
        if self._m is None:
            import torch
            from sentence_transformers import SentenceTransformer

            dev = self.device or ("mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu")
            self._m = SentenceTransformer(self.name, device=dev, model_kwargs={"torch_dtype": torch.bfloat16 if dev != "cpu" else torch.float32})
        return self._m

    def _key(self, kind: str, payload: bytes) -> Path:
        h = hashlib.sha1(self.prompt.encode() + b"\0" + kind.encode() + b"\0" + payload).hexdigest()
        return CACHE / self.name.replace("/", "_") / f"{h}.npy"

    def _encode(self, kind: str, payloads: list[bytes], inputs) -> np.ndarray:
        files = [self._key(kind, p) for p in payloads]
        out: list[np.ndarray | None] = [np.load(f) if f.exists() else None for f in files]
        todo = [i for i, v in enumerate(out) if v is None]
        for i in todo:  # po jednym: zrzuty mają różne rozmiary, a pamięć MPS jest ograniczona
            v = self.model.encode([inputs[i]], prompt=self.prompt, normalize_embeddings=True)[0].astype(np.float32)
            files[i].parent.mkdir(parents=True, exist_ok=True)
            np.save(files[i], v)
            out[i] = v
        return np.stack(out) if out else np.zeros((0, 0), np.float32)

    def texts(self, texts: list[str]) -> np.ndarray:
        return self._encode("t", [t.encode() for t in texts], [{"text": t} for t in texts])

    def images(self, paths: list[Path]) -> np.ndarray:
        return self._encode("i", [p.read_bytes() for p in paths], [{"image": _load_image(p)} for p in paths])


def text_vectors(name: str, texts: list[str], prompt: str | None = None, max_len: int = 256) -> np.ndarray:
    """Wektory tekstów dowolnym modelem z sentence-transformers (lekkim lub Qwen3-VL). Znormalizowane."""
    import torch
    from sentence_transformers import SentenceTransformer

    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    m = SentenceTransformer(name, device=dev)
    m.max_seq_length = max_len
    inp = [{"text": t} for t in texts] if "Qwen3-VL" in name else texts
    return np.asarray(m.encode(inp, prompt=prompt or None, normalize_embeddings=True, batch_size=16, show_progress_bar=False))
