"""Campaign graph: creative / advertiser / domain / artifact nodes, kNN + near-dup edges, Leiden communities."""
from __future__ import annotations

import json
from pathlib import Path

import igraph as ig
import leidenalg
import numpy as np

from ..process.hashing import hash_edges
from ..schema import Ad


def build_graph(ads: list[Ad], X: np.ndarray, labels: np.ndarray, cfg: dict, use_hash: bool = True, use_content: bool = True,
                infra_edges: list[dict] | None = None) -> tuple[ig.Graph, list[dict]]:
    g = cfg["graph"]
    names: dict[str, int] = {}
    kinds: list[str] = []
    edges: list[tuple[int, int, float, str]] = []

    def node(key: str, kind: str) -> int:
        if key not in names:
            names[key] = len(names)
            kinds.append(kind)
        return names[key]

    cre = [node(f"c:{a.ad_id}", "creative") for a in ads]
    infra: dict[int, set] = {}
    for a, c in zip(ads, cre):
        keys = ([(f"a:{a.page_id}", "advertiser")] if a.page_id else []) + [(f"d:{d}", "domain") for d in a.domains] \
            + [(f"x:{x.value}", "artifact") for x in a.artifacts if x.kind != "url"]
        for k, kind in keys:
            n = node(k, kind)
            infra.setdefault(n, set()).add(c)
            edges.append((c, n, 1.0, f"creative-{kind}"))
    # decoy weighting: infrastructure that spans many unrelated content clusters is down-weighted
    lab_of = {c: labels[i] for i, c in enumerate(cre)}
    w_infra = {n: (g["decoy_weight"] if len({lab_of[c] for c in cs}) > 2 else 1.0) for n, cs in infra.items()}
    edges = [(a, b, (w_infra[b] if et.startswith("creative-") else w), et) for a, b, w, et in edges]
    S = X @ X.T if use_content else np.full((len(ads), len(ads)), -1.0)
    np.fill_diagonal(S, -1)
    seen: set[tuple[int, int]] = set()
    for i in range(len(ads)):
        for j in np.argsort(-S[i])[: g["knn_k"]]:
            if S[i, j] >= g["edge_cos_min"]:
                key = (min(i, int(j)), max(i, int(j)))
                if key not in seen:
                    seen.add(key)
                    edges.append((cre[key[0]], cre[key[1]], float(S[i, j]), "creative-creative"))
    h = cfg["hash"]
    for i, j in (hash_edges if use_hash else lambda *a: [])([a.text_norm for a in ads], h["simhash_hamming_max"], h["lsh_threshold"], h["minhash_perm"], h["shingle_char_n"]):
        edges.append((cre[i], cre[j], 1.0, "near-duplicate"))
    for e in infra_edges or []:  # explainable domain-domain links from fejki.infra.link.graph_edges
        edges.append((node(e["src"], "domain"), node(e["dst"], "domain"), float(e["weight"]), e["etype"]))
    G = ig.Graph(n=len(names), edges=[(a, b) for a, b, _, _ in edges])
    G.es["weight"] = [w for _, _, w, _ in edges]
    G.es["etype"] = [et for _, _, _, et in edges]
    inv = {v: k for k, v in names.items()}
    G.vs["name"] = [inv[i] for i in range(len(names))]
    G.vs["kind"] = kinds
    return G, [{"src": inv[a], "dst": inv[b], "etype": et, "weight": w} for a, b, w, et in edges]


def communities(G: ig.Graph, resolution: float = 1.0, seed: int = 1) -> np.ndarray:
    part = leidenalg.find_partition(G, leidenalg.RBConfigurationVertexPartition, weights="weight",
                                    resolution_parameter=resolution, seed=seed)
    return np.array(part.membership)


def export(G: ig.Graph, membership: np.ndarray, out: str | Path, run_id: str) -> None:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    nodes = [{"id": v["name"], "kind": v["kind"], "community": int(membership[v.index])} for v in G.vs]
    edges = [{"src": G.vs[e.source]["name"], "dst": G.vs[e.target]["name"], "etype": e["etype"], "weight": e["weight"]} for e in G.es]
    (out / f"{run_id}.json").write_text(json.dumps({"nodes": nodes, "edges": edges}))
    G.vs["community"] = [int(m) for m in membership]
    G.write_graphml(str(out / f"{run_id}.graphml"))
