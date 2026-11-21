"""Kanał wizualny: embeddingi obrazu (Meta Perception Encoder, PE-Core B/16, Apache-2.0) dla zrzutów, kreacji i klatek wideo.

Dlaczego: pHash łapie tylko identyczne obrazki, więc samych zrzutów reklam nie dało się łączyć. Embedding obrazu uchwytuje wygląd i układ
(karta reklamy, wizerunek, kolorystyka), a podobieństwo kosinusowe daje dowód „podobny wygląd” z przesłanką.

Model jest opcjonalny: bez pobranych wag (`model_available()`) kanał się wyłącza, a reszta narzędzia działa bez zmian.
Cache wektorów na dysku (klucz = sha1 treści pliku + model), więc kolejne uruchomienia są szybkie.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from ..config import ROOT
from .material import Material

HUB = "hf-hub:timm/PE-Core-B-16"
REPO = "timm/PE-Core-B-16"
CACHE = ROOT / "artifacts" / "demo" / "vemb"
_M = None


def model_available() -> bool:
    """Czy wagi są na dysku (żeby nie uruchomić po cichu pobierania 1,8 GB)."""
    try:
        import open_clip  # noqa: F401
        from huggingface_hub import snapshot_download

        snapshot_download(REPO, local_files_only=True, allow_patterns=["open_clip_model.safetensors"])
        return True
    except Exception:
        return False


def _load():
    global _M
    if _M is None:
        import open_clip
        import torch

        from ..config import pick_device

        model, _, pre = open_clip.create_model_and_transforms(HUB)
        model.eval().to(pick_device("auto"))
        _M = (model, pre, torch)
    return _M


def _key(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()[:2_000_000] + path.name.encode() + HUB.encode()).hexdigest()


def embed_files(paths: list[Path]) -> dict[str, np.ndarray]:
    """Wektory (znormalizowane) dla plików obrazów; z cache, nowe liczone partiami."""
    from PIL import Image

    CACHE.mkdir(parents=True, exist_ok=True)
    out: dict[str, np.ndarray] = {}
    todo = []
    for p in paths:
        c = CACHE / f"{_key(p)}.npy"
        if c.exists():
            out[str(p)] = np.load(c)
        else:
            todo.append((p, c))
    if todo:
        model, pre, torch = _load()
        dev = next(model.parameters()).device
        for k in range(0, len(todo), 16):
            batch = todo[k:k + 16]
            imgs = []
            for p, _ in batch:
                try:
                    imgs.append(pre(Image.open(p).convert("RGB")))
                except Exception:
                    imgs.append(None)
            ok = [i for i, x in enumerate(imgs) if x is not None]
            if not ok:
                continue
            with torch.no_grad():
                v = model.encode_image(torch.stack([imgs[i] for i in ok]).to(dev))
                v = torch.nn.functional.normalize(v, dim=-1).cpu().numpy()
            for j, i in enumerate(ok):
                np.save(batch[i][1], v[j])
                out[str(batch[i][0])] = v[j]
    return out


def material_vectors(materials: list[Material], base: dict[str, Path] | None = None, roles=("zrzut", "kreacja")) -> dict[str, np.ndarray]:
    """Wektor materiału = średnia z jego zrzutów i kreacji (obrazy zasobów stron pomijamy: to elementy, nie wygląd reklamy).

    `base`: materiał → katalog z plikami (potrzebny do odnalezienia obrazów po nazwie).
    """
    files, owner = [], {}
    for m in materials:
        d = (base or {}).get(m.id) or m.base_dir
        if d is None or not Path(d).exists():
            continue
        names = {i.file for i in m.images if i.role in roles}
        for f in Path(d).rglob("*"):
            if f.is_file() and f.name in names and "_files" not in str(f):
                files.append(f)
                owner[str(f)] = m.id
    vecs = embed_files(files)
    per: dict[str, list[np.ndarray]] = {}
    for f, v in vecs.items():
        per.setdefault(owner[f], []).append(v)
    out = {}
    for mid, vs in per.items():
        v = np.mean(vs, axis=0)
        out[mid] = v / max(np.linalg.norm(v), 1e-9)
    return out
