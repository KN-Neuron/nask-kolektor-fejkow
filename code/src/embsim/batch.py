"""Wsadowe kodowanie unikalnych tekstów (np. z grafu) z wznawianiem. Wyjście: <out>/vectors.npy (float16) + hashes.json.

    python -m embsim.batch ad_texts.jsonl OUT_DIR [--model M] [--limit N] [--max-len 192] [--batch 16]

Domyślnie Qwen3-VL-Embedding (wolny: ~3-4 teksty/s na Macu); dowolny model sentence-transformers (np. lekki
paraphrase-multilingual-MiniLM-L12-v2) dostaje zwykłe napisy zamiast słowników i nie dostaje instrukcji.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from .embed import DEFAULT_MODEL, Embedder

CHUNK = 512


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--max-len", type=int, default=192)
    ap.add_argument("--batch", type=int, default=16)
    a = ap.parse_args()
    uniq: dict[str, str] = {}
    for line in a.src.open(encoding="utf-8"):
        r = json.loads(line)
        uniq.setdefault(r["h"], r["text"])
    hashes = sorted(uniq, key=lambda h: len(uniq[h]))  # podobne długości w jednym wsadzie = mniej paddingu
    if a.limit:
        hashes = hashes[-a.limit:]
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "hashes.json").write_text(json.dumps(hashes))
    qwen = "Qwen3-VL" in a.model
    emb = Embedder(a.model)
    emb.model.max_seq_length = a.max_len
    t0, done = time.time(), 0
    for k in range(0, len(hashes), CHUNK):
        f = a.out / f"chunk_{k // CHUNK:04d}.npy"
        part = hashes[k:k + CHUNK]
        if not f.exists():
            inp = [{"text": uniq[h]} if qwen else uniq[h] for h in part]
            v = emb.model.encode(inp, prompt=emb.prompt if qwen else None, batch_size=a.batch,
                                 normalize_embeddings=True, show_progress_bar=False)
            np.save(f, np.asarray(v, dtype=np.float16))
        done += len(part)
        print(f"{done}/{len(hashes)}  {done / max(time.time() - t0, 1e-9):.1f}/s", flush=True)
    chunks = sorted(a.out.glob("chunk_*.npy"))
    np.save(a.out / "vectors.npy", np.concatenate([np.load(c) for c in chunks]))
    print("gotowe:", a.out / "vectors.npy")


if __name__ == "__main__":
    main()
