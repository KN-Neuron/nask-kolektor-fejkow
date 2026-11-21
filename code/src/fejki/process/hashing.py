"""SimHash (64 bit) and MinHash over character n-grams."""
from __future__ import annotations

import hashlib
import re
from collections import Counter

from datasketch import MinHash, MinHashLSH


def _h64(s: str) -> int:
    return int.from_bytes(hashlib.blake2b(s.encode(), digest_size=8).digest(), "big")


def tokens(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def simhash(text: str, bits: int = 64) -> int:
    toks = tokens(text)
    feats = Counter(toks[i] + " " + toks[i + 1] for i in range(len(toks) - 1)) if len(toks) > 1 else Counter(toks)
    v = [0] * bits
    for f, w in feats.items():
        h = _h64(f)
        for b in range(bits):
            v[b] += w if (h >> b) & 1 else -w
    return sum(1 << b for b in range(bits) if v[b] > 0)


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def shingles(text: str, n: int = 5) -> set[str]:
    t = re.sub(r"\s+", " ", text.lower())
    if len(t) <= n:
        return {t}
    return {t[i : i + n] for i in range(len(t) - n + 1)}


def minhash(text: str, perm: int = 128, n: int = 5) -> MinHash:
    m = MinHash(num_perm=perm, seed=1)
    for s in shingles(text, n):
        m.update(s.encode())
    return m


def hash_edges(texts: list[str], hamming_max: int = 3, lsh_threshold: float = 0.6, perm: int = 128, n: int = 5):
    """Near-duplicate edges (i, j) from SimHash Hamming and MinHash-LSH Jaccard."""
    sims = [simhash(t) for t in texts]
    edges: set[tuple[int, int]] = set()
    # SimHash: band by 4 x 16 bits, then exact Hamming check (pigeonhole for d<=3)
    buckets: dict[tuple[int, int], list[int]] = {}
    for i, s in enumerate(sims):
        for band in range(4):
            buckets.setdefault((band, (s >> (16 * band)) & 0xFFFF), []).append(i)
    for idx in buckets.values():
        if len(idx) > 400:
            idx = idx[:400]
        for a in range(len(idx)):
            for b in range(a + 1, len(idx)):
                i, j = idx[a], idx[b]
                if hamming(sims[i], sims[j]) <= hamming_max:
                    edges.add((min(i, j), max(i, j)))
    lsh = MinHashLSH(threshold=lsh_threshold, num_perm=perm)
    mhs = [minhash(t, perm, n) for t in texts]
    for i, m in enumerate(mhs):
        lsh.insert(str(i), m)
    for i, m in enumerate(mhs):
        for k in lsh.query(m):
            j = int(k)
            if j != i:
                edges.add((min(i, j), max(i, j)))
    return sorted(edges)


def components(n: int, edges) -> list[int]:
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in edges:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    roots: dict[int, int] = {}
    return [roots.setdefault(find(i), len(roots)) for i in range(n)]
