"""Eksport grafu powiązań: GraphML (Gephi, yEd, networkx) oraz Neo4j (Cypher i CSV do importu).

Węzły: Material (cechy), Domain, Pixel, Person, Campaign, Network. Krawędzie: SIMILAR (z wynikiem, relacją i przesłankami),
HOSTS (materiał → domena), USES_PIXEL, MENTIONS, IN_CAMPAIGN, IN_NETWORK.
"""
from __future__ import annotations

import csv
import io
import json
import re

import networkx as nx

from .material import Material
from .similar import Campaign, Pair


def build_graph(materials: list[Material], pairs: list[Pair], camps: list[Campaign], nets: list[Campaign],
                thr: float = 0.4) -> nx.Graph:
    g = nx.Graph()
    for m in materials:
        g.add_node(f"m:{m.id}", kind="Material", label=m.id, title=(m.titles or [""])[0][:120], topics=", ".join(list(m.topics)[:2]))
        for d in m.landing_domains:
            g.add_node(f"d:{d}", kind="Domain", label=d)
            g.add_edge(f"m:{m.id}", f"d:{d}", type="HOSTS")
        for px in m.pixel_ids:
            g.add_node(f"p:{px}", kind="Pixel", label=px)
            g.add_edge(f"m:{m.id}", f"p:{px}", type="USES_PIXEL")
        for person in m.persons[:4]:
            g.add_node(f"o:{person}", kind="Person", label=person)
            g.add_edge(f"m:{m.id}", f"o:{person}", type="MENTIONS")
    for c in camps:
        g.add_node(f"c:{c.id}", kind="Campaign", label=f"{c.id} {c.name}"[:80])
        for mid in c.members:
            g.add_edge(f"m:{mid}", f"c:{c.id}", type="IN_CAMPAIGN")
    for n in nets:
        if len(n.members) > 1:
            g.add_node(f"n:{n.id}", kind="Network", label=n.id)
            for mid in n.members:
                g.add_edge(f"m:{mid}", f"n:{n.id}", type="IN_NETWORK")
    for p in pairs:
        if p.score >= thr:
            g.add_edge(f"m:{p.a}", f"m:{p.b}", type="SIMILAR", score=p.score, relation=p.relation,
                       reasons=" | ".join(e.reason for e in p.evidence[:6]))
    return g


def graphml(g: nx.Graph) -> str:
    buf = io.BytesIO()
    nx.write_graphml(g, buf)
    return buf.getvalue().decode("utf-8")


def _q(v) -> str:
    """Literał Cypher: napisy w cudzysłowie, a mapy z kluczami bez cudzysłowu (JSON w Cypherze jest nieprawidłowy)."""
    if isinstance(v, dict):
        items = [(re.sub(r"\W", "_", str(k)), _q(x)) for k, x in v.items()]
        return "{" + ", ".join(f"{k}: {x}" for k, x in items) + "}"
    return json.dumps(v, ensure_ascii=False)


def cypher(g: nx.Graph) -> str:
    """Skrypt Cypher (wklejany w Neo4j Browser lub `cypher-shell < plik`)."""
    L = ["// Kolekcjoner Fejków: graf powiązań", "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Node) REQUIRE n.key IS UNIQUE;"]
    for k, a in g.nodes(data=True):
        props = {kk: vv for kk, vv in a.items() if kk != "kind"}
        L.append(f"MERGE (n:Node {{key: {_q(k)}}}) SET n:{a['kind']}, n += {_q(props)};")
    for u, v, a in g.edges(data=True):
        props = {kk: vv for kk, vv in a.items() if kk != "type"}
        typ = re.sub(r"\W", "_", a["type"])
        L.append(f"MATCH (a:Node {{key: {_q(u)}}}), (b:Node {{key: {_q(v)}}}) MERGE (a)-[r:{typ}]->(b) SET r += {_q(props)};")
    return "\n".join(L) + "\n"


def csvs(g: nx.Graph) -> dict[str, str]:
    nodes, edges = io.StringIO(), io.StringIO()
    wn = csv.writer(nodes)
    wn.writerow(["key", "kind", "label", "title"])
    for k, a in g.nodes(data=True):
        wn.writerow([k, a["kind"], a.get("label", ""), a.get("title", "")])
    we = csv.writer(edges)
    we.writerow(["source", "target", "type", "score", "relation", "reasons"])
    for u, v, a in g.edges(data=True):
        we.writerow([u, v, a["type"], a.get("score", ""), a.get("relation", ""), a.get("reasons", "")])
    return {"nodes.csv": nodes.getvalue(), "edges.csv": edges.getvalue()}
