"""Czy kanał obrazu niesie sygnał na PRAWDZIWYCH zrzutach? Porównanie embeddingu Qwen3-VL z trywialnymi punktami odniesienia.

    python -m embsim.image_eval [--max-side 768]

Zbiory:
  * urlscan (data/urlscan, 117 zrzutów): etykieta = pivot (zestaw `aio-sdk`, schemat TDS `utm-visit`, produkt `uromexil-forte`).
    UWAGA: etykiety wynikają z infrastruktury (nazwa pliku zestawu, nazwy parametrów adresu), nie z wyglądu, więc są ŚLEPE na
    obraz: jeśli zrzuty tej samej grupy wyglądają podobnie, to dlatego, że ta sama infrastruktura daje podobny szablon. To pomiar
    „czy obraz widzi szablon”, nie „czy obraz poznaje kampanię”. Negatywy (neg-tvn24) nie mają grupy.
  * NASK-10: macierz podobieństw przypadków z obrazem; znane: 1 i 2 duplikat (2 bez zrzutu), 48 i 61 wariant, sieć {1,2,3,48,61}.
Punkty odniesienia (zero modeli): odcisk dHash 64 bity i histogram kolorów RGB 4×4×4.
"""
from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

import numpy as np
from PIL import Image

from . import embed
from .embed import Embedder
from .material import load_case as load_material
from .metrics import assignment, pairwise

ROOT = Path(__file__).resolve().parents[3]


def dhash(p: Path) -> np.ndarray:
    im = Image.open(p).convert("L").resize((9, 8), Image.LANCZOS)
    a = np.asarray(im, dtype=np.int16)
    return (a[:, 1:] > a[:, :-1]).ravel()


def color_hist(p: Path) -> np.ndarray:
    im = Image.open(p).convert("RGB").resize((128, 96))
    a = (np.asarray(im) // 64).reshape(-1, 3)
    h = np.bincount(a[:, 0] * 16 + a[:, 1] * 4 + a[:, 2], minlength=64).astype(np.float32)
    return h / np.linalg.norm(h)


def l2(V):
    V = np.asarray(V, dtype=np.float32)
    return V / np.maximum(np.linalg.norm(V, axis=1, keepdims=True), 1e-9)


def report(name: str, S: np.ndarray, labels: list) -> None:
    p = pairwise(S, labels)
    a = assignment(S, labels, 0.5)
    print(f"  {name:<24} AUC={p['AUC']:.3f}  AP={p['AP']:.3f}  top1={a['top1']:.3f}  znany_vs_nowy_AUC={a.get('znany_vs_nowy_AUC', float('nan')):.3f}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-side", type=int, default=768)
    a = ap.parse_args()
    embed.MAX_SIDE = a.max_side

    rows = [r for r in csv.DictReader((ROOT / "data/urlscan/labels.csv").open(encoding="utf-8"))
            if (ROOT / "data/urlscan" / r["case_id"] / "screenshot.png").exists()]
    paths = [ROOT / "data/urlscan" / r["case_id"] / "screenshot.png" for r in rows]
    labels = [r["label"] if r["kind"] == "pozytyw" else None for r in rows]
    print(f"urlscan: {len(rows)} zrzutów, grupy: " + ", ".join(f"{l}={labels.count(l)}" for l in sorted(set(x for x in labels if x))))

    t = time.time()
    D = np.stack([dhash(p) for p in paths]); Sd = 1 - (D[:, None, :] != D[None, :, :]).mean(-1)
    H = np.stack([color_hist(p) for p in paths]); Sh = H @ H.T
    print(f"punkty odniesienia policzone w {time.time() - t:.1f}s")

    emb = Embedder()
    t = time.time(); chunks = []
    for i in range(0, len(paths), 10):
        chunks.append(emb.images(paths[i:i + 10]))
        print(f"  Qwen obrazy {min(i + 10, len(paths))}/{len(paths)}  {time.time() - t:.0f}s", flush=True)
    Vq = l2(np.concatenate(chunks)); Sq = Vq @ Vq.T

    print("\n== urlscan: czy obraz widzi te same pivoty (pary w grupach vs różne grupy)")
    report("dHash (odcisk)", Sd, labels)
    report("histogram kolorów", Sh, labels)
    report("Qwen3-VL (obraz)", Sq, labels)
    for name, S in (("dHash", Sd), ("hist", Sh), ("Qwen", Sq)):
        same = np.array([[x is not None and x == y for y in labels] for x in labels]); np.fill_diagonal(same, False)
        diff = np.array([[x is not None and y is not None and x != y for y in labels] for x in labels])
        print(f"    {name:<6} średnie podobieństwo: ta sama grupa {S[same].mean():.3f} | różne grupy {S[diff].mean():.3f}")

    print("\n== NASK-10: podobieństwo przypadków (średni wektor obrazów); znane: 1≈2 (2 bez zrzutu), 48≈61, sieć {1,2,3,48,61}")
    nask = ROOT / "data/dane/do_udostępnienia"
    cases = {}
    for d in sorted((p for p in nask.iterdir() if p.is_dir()), key=lambda p: int(p.name)):
        imgs = load_material(d).images
        if imgs:
            cases[d.name] = l2(emb.images(imgs)).mean(0)
    ids = list(cases)
    M = l2(np.stack([cases[i] for i in ids])); S = M @ M.T
    print("  przypadki z obrazem:", ", ".join(f"{i}({len(load_material(nask / i).images)})" for i in ids))
    print("       " + "".join(f"{i:>7}" for i in ids))
    for i, r in zip(ids, S):
        print(f"  {i:>4} " + "".join(f"{x:>7.2f}" for x in r))
    net = {"1", "3", "48", "61"}
    inn = [S[a_, b_] for a_, x in enumerate(ids) for b_, y in enumerate(ids) if a_ < b_ and x in net and y in net]
    out = [S[a_, b_] for a_, x in enumerate(ids) for b_, y in enumerate(ids) if a_ < b_ and (x in net) != (y in net)]
    print(f"  średnio wewnątrz sieci (1,3,48,61): {np.mean(inn):.3f} | sieć vs reszta: {np.mean(out):.3f}")


if __name__ == "__main__":
    main()
