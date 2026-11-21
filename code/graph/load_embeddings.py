"""Wpina wektory tekstów (policzone przez `python -m embsim.batch`) do grafu: (:Ad)-[:HAS_TEXT]->(:Text {hash, embedding}).

    .venv/bin/python graph/load_embeddings.py artifacts/qwen_ads --dim 1024

Wektor jest przycięty do pierwszych `dim` współrzędnych i znormalizowany (Qwen3-VL-Embedding uczono z MRL). Schemat: schema.cypher.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from load import driver, run_batches, schema  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dir", type=Path)
    ap.add_argument("--dim", type=int, default=1024)
    a = ap.parse_args()
    hashes = json.loads((a.dir / "hashes.json").read_text())
    V = np.load(a.dir / "vectors.npy").astype(np.float32)[:, : a.dim]
    V /= np.linalg.norm(V, axis=1, keepdims=True)
    assert len(hashes) == len(V), "hashes.json i vectors.npy mają różną długość"
    rows = [{"h": h, "e": v.tolist()} for h, v in zip(hashes, V)]
    drv = driver()
    with drv.session() as s:
        schema(s)
        run_batches(s, "UNWIND $rows AS r MERGE (t:Text {hash: r.h}) SET t.embedding = r.e, t.name = left(r.h, 8)", rows, "Text")
        run_batches(s, "UNWIND $rows AS r MATCH (t:Text {hash: r.h}) MATCH (a:Ad {text_hash: r.h}) MERGE (a)-[:HAS_TEXT]->(t)",
                    [{"h": h} for h in hashes], "HAS_TEXT")
        print(dict(s.run("MATCH (t:Text) RETURN count(t) AS texts").single()),
              dict(s.run("MATCH (:Ad)-[r:HAS_TEXT]->() RETURN count(r) AS ads_z_wektorem").single()))
    drv.close()


if __name__ == "__main__":
    main()
