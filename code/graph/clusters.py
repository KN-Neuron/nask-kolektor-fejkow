"""Klastry z grafu w czytelnej formie (task 6): dane dla zakładki demo i karty w Markdown.

    .venv/bin/python graph/clusters.py creators --label scam            # lista twórców
    .venv/bin/python graph/clusters.py creator "Sharon Coleman"           # karta twórcy (Markdown)
    .venv/bin/python graph/clusters.py group S1                           # karta sieci / kampanii (NASK, syntetyka)

Zasada czytelności: zamiast grafu wszystkiego pokazujemy jeden klaster naraz i tylko to, co go SKLEJA:
- twórca (Meta): strony + ślady, które łączą co najmniej dwie strony (płatnik, domena, identyczny tekst);
- sieć / kampania (NASK, syntetyka): materiały + wspólne ślady nie-huby (zestaw strony, schemat adresu, piksel, domena, osoba...).
Huby (google.com, CDN) są pomijane, bo niczego nie dowodzą. Każda kreska na rysunku ma podpis „dlaczego”.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from load import driver

MAX_DRAW = 14  # najwięcej śladów na rysunku; reszta tylko w tabeli

KIND_PL = {"Payer": "płatnik", "Domain": "domena", "Text": "identyczny tekst", "PageKit": "zestaw strony", "UrlScheme": "schemat adresu",
           "Tracker": "piksel / tag", "Advertiser": "strona reklamodawcy", "Person": "osoba", "Product": "produkt", "Brand": "marka",
           "Contact": "kontakt", "ImageHash": "ten sam obraz"}
REL_PL = {"LANDS_ON": "ląduje na", "CALLS": "wywołuje", "USES_KIT": "zestaw strony", "USES_URL_SCHEME": "schemat adresu",
          "USES_TRACKER": "piksel / tag", "ADVERTISED_BY": "strona reklamodawcy", "MENTIONS": "osoba", "PROMOTES": "produkt",
          "IMPERSONATES": "podrabia markę", "HAS_CONTACT": "kontakt", "HAS_IMAGE": "ten sam obraz", "REDIRECTS_THROUGH": "przekierowanie"}
LABEL_PL = {"scam": "scam", "podejrzany": "podejrzany", "brak sygnału": "brak sygnału"}


# --------------------------------------------------------------------------------------------------------------------
# twórcy (Meta)

def creators(session, label: str | None = None, min_ads: int = 2, q: str | None = None, limit: int = 300) -> list[dict]:
    return [dict(r) for r in session.run("""
        MATCH (c:Creator)
        WHERE ($label IS NULL OR c.label = $label) AND c.n_ads >= $min_ads
          AND ($q IS NULL OR toLower(c.name) CONTAINS toLower($q)
               OR EXISTS { (c)<-[:PART_OF]-(x) WHERE toLower(x.name) CONTAINS toLower($q) })
        RETURN c.id AS id, c.name AS twórca, c.label AS etykieta, c.n_ads AS reklam, c.n_flagged AS zdjętych,
               round(100.0 * coalesce(c.scam_share, 0)) AS proc_zdjętych, c.n_pages AS stron, c.n_payers AS płatników,
               EXISTS { (c)<-[:CREATED_BY]-(:Material) } AS nask
        ORDER BY nask DESC, c.n_pages DESC, c.n_ads DESC LIMIT $limit""", label=label, min_ads=min_ads, q=q or None, limit=limit)]


def find_creator(session, x: str) -> str | None:
    r = session.run("""
        MATCH (c:Creator) WHERE c.id = $x OR c.name = $x OR EXISTS { (c)<-[:PART_OF]-(:Advertiser {name: $x}) }
        RETURN c.id AS id ORDER BY c.n_ads DESC LIMIT 1""", x=x).single()
    return r["id"] if r else None


def creator_card(session, cid: str) -> dict:
    head = session.run("""
        MATCH (c:Creator {id: $id})<-[:CREATED_BY]-(a:Ad)
        RETURN c.id AS id, c.name AS name, c.label AS label, c.n_ads AS n_ads, c.n_flagged AS n_flagged, c.n_pages AS n_pages,
               c.n_payers AS n_payers, c.scam_share AS share, min(a.delivery_start) AS od,
               max(coalesce(a.delivery_stop, a.delivery_start)) AS do, count(DISTINCT a.text_hash) AS texts,
               [p IN collect(DISTINCT a.found_by) WHERE p STARTS WITH 'kw:' | substring(p, 3)][..8] AS topics""", id=cid).single()
    if head is None:
        return {}
    card = dict(head)
    card["pages"] = [dict(r) for r in session.run("""
        MATCH (c:Creator {id: $id})<-[:PART_OF]-(v:Advertiser)<-[:BY]-(a:Ad)
        RETURN v.name AS strona, v.page_id AS page_id, count(a) AS reklam, sum(CASE WHEN a.meta_flag IS NULL THEN 0 ELSE 1 END) AS zdjętych,
               coalesce(v.mixed_script, false) AS mieszane_alfabety
        ORDER BY reklam DESC""", id=cid)]
    # co skleja strony w jednego twórcę: ślad wspólny dla >= 2 stron
    glue = [dict(r) for r in session.run("""
        MATCH (c:Creator {id: $id})<-[:PART_OF]-(x) WHERE x:Payer OR x:Domain
        MATCH (x)<-[:PAID_BY|LINKS_TO]-(a:Ad)-[:CREATED_BY]->(c), (a)-[:BY]->(v:Advertiser)
        WITH x, labels(x)[0] AS kind, collect(DISTINCT v.name) AS pages, count(DISTINCT a) AS ads
        WHERE size(pages) > 1
        RETURN kind, x.name AS name, pages, ads ORDER BY size(pages) DESC, ads DESC""", id=cid)]
    glue += [dict(r) for r in session.run("""
        MATCH (c:Creator {id: $id})<-[:CREATED_BY]-(a:Ad)-[:BY]->(v:Advertiser) WHERE a.text_hash IS NOT NULL
        WITH a.text_hash AS h, collect(DISTINCT v.name) AS pages, count(a) AS ads, head(collect(a.body)) AS body
        WHERE size(pages) > 1
        RETURN 'Text' AS kind, '„' + left(body, 50) + '…”' AS name, pages, ads ORDER BY size(pages) DESC, ads DESC LIMIT 20""", id=cid)]
    card["glue"] = sorted(glue, key=lambda g: (-len(g["pages"]), -g["ads"]))
    card["ads"] = [dict(r) for r in session.run("""
        MATCH (c:Creator {id: $id})<-[:CREATED_BY]-(a:Ad)
        RETURN a.delivery_start AS start, CASE WHEN a.meta_flag IS NULL THEN '' ELSE 'zdjęta przez Metę' END AS meta,
               a.label AS etykieta, a.label_source AS skąd, coalesce(nullif(a.title, ''), left(a.body, 90), '(treść usunięta)') AS treść,
               a.library_url AS link
        ORDER BY a.meta_flag IS NULL, a.delivery_start DESC LIMIT 30""", id=cid)]
    card["materials"] = [dict(r) for r in session.run("""
        MATCH (c:Creator {id: $id})<-[:CREATED_BY]-(m:Material)
        RETURN m.id AS id, m.name AS nazwa, coalesce(m.dataset, '') AS zbiór, m.verdict AS decyzja""", id=cid)]
    return card


def creator_dot(card: dict) -> str:
    """Rysunek: strony (prostokąty) i ślady, które je sklejają (owale), układ bez fizyki, więc się nie rusza."""
    if not card:
        return ""
    glue = card["glue"][:MAX_DRAW]
    pages = sorted({p for g in glue for p in g["pages"]}) or [p["strona"] for p in card["pages"][:MAX_DRAW]]
    color = {"Payer": "#7c3aed", "Domain": "#2563eb", "Text": "#6b7280"}
    esc = lambda s: str(s).replace('"', "'")
    fill = {"scam": "#fecaca", "podejrzany": "#fde68a"}.get(card["label"], "#e5e7eb")
    head = f'"tw" [label="{esc(card["name"])}\\n{card["n_ads"]} reklam · {card["label"]}", shape=doubleoctagon, style=filled, fillcolor="{fill}"];'
    lines = ['graph G {', 'rankdir=LR; bgcolor="transparent"; node [fontname="Helvetica", fontsize=11];', head]
    for p in pages[:30]:
        lines.append(f'"p:{esc(p)}" [label="{esc(p)}", shape=box, style="rounded,filled", fillcolor="#f3f4f6"];')
        lines.append(f'"tw" -- "p:{esc(p)}" [color="#d1d5db"];')
    for i, g in enumerate(glue):
        lines.append(f'"g{i}" [label="{KIND_PL[g["kind"]]}:\\n{esc(g["name"])[:40]}\\n({g["ads"]} reklam)", shape=ellipse, '
                     f'color="{color[g["kind"]]}", fontcolor="{color[g["kind"]]}"];')
        for p in g["pages"]:
            if p in pages[:30]:
                lines.append(f'"p:{esc(p)}" -- "g{i}" [color="{color[g["kind"]]}"];')
    for m in card["materials"]:
        lines.append(f'"m:{esc(m["id"])}" [label="przypadek {esc(m["id"])}\\n({m["zbiór"]})", shape=note, style=filled, fillcolor="#dbeafe"];')
        lines.append(f'"m:{esc(m["id"])}" -- "tw" [style=dashed, label="ta sama strona"];')
    lines.append("}")
    return "\n".join(lines)


# --------------------------------------------------------------------------------------------------------------------
# sieci i kampanie (materiały NASK, syntetyka, nowe z `add`)

def groups(session, dataset: str = "nask") -> list[dict]:
    return [dict(r) for r in session.run("""
        MATCH (c:Campaign)<-[:IN_CAMPAIGN]-(m:Material {dataset: $ds})
        OPTIONAL MATCH (c)-[:IN_NETWORK]->(n:Network)
        WITH coalesce(n.id, c.id) AS id, CASE WHEN n IS NULL THEN 'kampania' ELSE 'sieć' END AS typ,
             collect(DISTINCT c.id) AS kampanie, collect(DISTINCT m.id) AS materiały
        RETURN id, typ, kampanie, materiały, size(materiały) AS liczba
        ORDER BY liczba DESC, id""", ds=dataset)]


def group_card(session, gid: str) -> dict:
    members = [r["id"] for r in session.run("""
        OPTIONAL MATCH (:Network {id: $g})<-[:IN_NETWORK]-(:Campaign)<-[:IN_CAMPAIGN]-(m1:Material)
        OPTIONAL MATCH (:Campaign {id: $g})<-[:IN_CAMPAIGN]-(m2:Material)
        WITH collect(DISTINCT m1.id) + collect(DISTINCT m2.id) AS ids UNWIND ids AS id RETURN DISTINCT id""", g=gid)]
    if not members:
        return {}
    mats = [dict(r) for r in session.run("""
        UNWIND $ids AS i MATCH (m:Material {id: i}) OPTIONAL MATCH (m)-[:IN_CAMPAIGN]->(c:Campaign)
        OPTIONAL MATCH (m)-[:CREATED_BY]->(tw:Creator)
        RETURN m.id AS id, m.name AS nazwa, left(coalesce(m.title, ''), 70) AS tytuł, c.id AS kampania, tw.name AS twórca_meta,
               m.truth_operator AS prawda_operator, m.truth_campaign AS prawda_kampania
        ORDER BY kampania, id""", ids=members)]
    shared = [dict(r) for r in session.run("""
        UNWIND $ids AS i MATCH (m:Material {id: i})-[r]->(x)
        WHERE type(r) IN $rels AND NOT coalesce(x.hub, false)
        WITH x, type(r) AS rel, labels(x)[0] AS kind, collect(DISTINCT m.id) AS ms WHERE size(ms) > 1
        RETURN kind, rel, coalesce(x.name, x.prefix, x.fingerprint, x.id) AS name, ms ORDER BY size(ms) DESC, rel""",
        ids=members, rels=list(REL_PL))]
    pairs = [dict(r) for r in session.run("""
        UNWIND $ids AS i MATCH (a:Material {id: i})-[s:SIMILAR]->(b:Material) WHERE b.id IN $ids
        RETURN a.id AS a, b.id AS b, s.score AS wynik, s.relation AS relacja, s.reasons AS przesłanki ORDER BY wynik DESC""", ids=members)]
    return {"id": gid, "members": members, "materials": mats, "shared": shared, "pairs": pairs}


def group_dot(card: dict) -> str:
    if not card:
        return ""
    esc = lambda s: str(s).replace('"', "'")
    camp_color = {}
    palette = ["#fee2e2", "#dbeafe", "#dcfce7", "#fef3c7", "#ede9fe", "#fce7f3"]
    lines = ['graph G {', 'rankdir=LR; bgcolor="transparent"; nodesep=0.15; ranksep=1.2; node [fontname="Helvetica", fontsize=11];']
    for m in card["materials"]:
        col = camp_color.setdefault(m["kampania"], palette[len(camp_color) % len(palette)])
        lines.append(f'"m:{esc(m["id"])}" [label="przypadek {esc(m["id"])}\\nkampania {esc(m["kampania"])}", shape=note, '
                     f'style=filled, fillcolor="{col}"];')
    # ślady tego samego rodzaju łączące TE SAME materiały = jeden owal (np. 6 wspólnych obrazów 48~61 to jeden węzeł „6 × ten sam obraz”)
    bundles: dict[tuple, list[str]] = {}
    for x in card["shared"]:
        bundles.setdefault((x["rel"], tuple(sorted(x["ms"]))), []).append(str(x["name"]))
    order = sorted(bundles.items(), key=lambda kv: (-len(kv[0][1]), -len(kv[1])))[:8]  # reszta w tabeli pod rysunkiem
    for i, ((rel, ms), names) in enumerate(order):
        vals = "\\n".join(esc(n)[:34] for n in names[:3]) + (f"\\n(+{len(names) - 3})" if len(names) > 3 else "")
        head = f"{len(names)} × {REL_PL[rel]}" if len(names) > 1 else REL_PL[rel]
        if rel == "HAS_IMAGE":
            vals = ""
        lines.append(f'"s{i}" [label="{head}' + (f':\\n{vals}' if vals else "") + '", shape=ellipse, color="#2563eb", fontcolor="#1e3a8a"];')
        for m in ms:
            lines.append(f'"m:{esc(m)}" -- "s{i}" [color="#93c5fd"];')
    lines.append("}")
    return "\n".join(lines)


# --------------------------------------------------------------------------------------------------------------------
# nowe materiały (add / scraper)

def added(session, limit: int = 100) -> list[dict]:
    return [dict(r) for r in session.run("""
        MATCH (n) WHERE n.verdict IS NOT NULL AND (n:Ad OR n:Material)
        OPTIONAL MATCH (n)-[:CREATED_BY]->(c:Creator)
        RETURN labels(n)[0] AS typ, n.id AS id, n.added_at AS dodano, n.verdict AS decyzja, c.name AS twórca,
               n.creator_source AS dlaczego_ten_twórca, n.verdict_text AS wyjaśnienie
        ORDER BY n.added_at DESC LIMIT $limit""", limit=limit)]


VERDICT_PL = {"znana_kampania": "znana kampania", "znany_operator_nowa_kampania": "znany operator, nowa kampania", "nowy_wzorzec": "nowy wzorzec"}


def _common(host: str) -> bool:
    """Pospolita usługa (instagram.com, google.com...): wspólna niczego nie dowodzi. Ta sama lista co w silniku, gdy jest dostępny."""
    try:
        from embsim.features import is_common
    except ImportError:
        return host.split(":")[0].removeprefix("www.") in {"instagram.com", "facebook.com", "google.com", "youtube.com", "linktr.ee"}
    return is_common(host)


def added_card(session, nid: str) -> dict:
    """Nowy materiał (add / scraper): decyzja, najbliższe materiały z silnika (krawędzie SIMILAR_TO) i ślady, które z nimi dzieli."""
    head = session.run("""
        MATCH (n {id: $id}) WHERE n:Ad OR n:Material
        OPTIONAL MATCH (n)-[:CREATED_BY]->(c:Creator)
        RETURN n.id AS id, labels(n)[0] AS typ, n.verdict AS verdict, n.verdict_text AS text, n.added_at AS added,
               left(coalesce(n.title, n.body, n.name, ''), 80) AS snippet, c.id AS creator_id, c.name AS creator, c.label AS label
        LIMIT 1""", id=nid).single()
    if head is None:
        return {}
    matches = [dict(r) for r in session.run("""
        MATCH ({id: $id})-[s:SIMILAR_TO]->(o)
        OPTIONAL MATCH (o)-[:CREATED_BY]->(c:Creator)
        RETURN o.id AS id, labels(o)[0] AS typ, left(coalesce(o.title, o.body, o.name, ''), 60) AS snippet, s.score AS score,
               s.operator_score AS operator_score, coalesce(s.reasons, []) AS reasons, c.id AS creator_id, c.name AS creator,
               c.label AS label
        ORDER BY s.score DESC, s.operator_score DESC""", id=nid)]
    traces = [dict(r) for r in session.run("""
        MATCH (n {id: $id})-[r:BY|PAID_BY|LINKS_TO|ADVERTISED_BY|LANDS_ON]->(x)
        OPTIONAL MATCH (n)-[:SIMILAR_TO]->(o)-[r2]->(x) WHERE type(r2) = type(r)
        RETURN labels(x)[0] AS kind, type(r) AS rel, coalesce(x.name, x.id) AS name, collect(DISTINCT o.id) AS shared""", id=nid)]
    for t in traces:
        t["common"] = t["kind"] == "Domain" and _common(t["name"])
    return {**dict(head), "matches": matches, "traces": traces}


def added_dot(card: dict) -> str:
    """Rysunek nowego materiału: on w środku, najbliższe materiały pogrupowane po twórcy, ślady wspólne z nimi. Strzałka do materiału,
    który rozstrzygnął decyzję, ma kolor werdyktu (czerwona: kampania, pomarańczowa: operator); reszta szara przerywana."""
    if not card:
        return ""
    esc = lambda s: str(s).replace('"', "'").replace("\n", " ")
    v = card["verdict"]
    fill = {"znana_kampania": "#fecaca", "znany_operator_nowa_kampania": "#fed7aa"}.get(v, "#e5e7eb")
    lines = ['digraph G {', 'rankdir=LR; bgcolor="transparent"; node [fontname="Helvetica", fontsize=10]; edge [fontname="Helvetica", fontsize=9];',
             f'"n" [label="nowy materiał {esc(card["id"])}\\n{esc(card["snippet"])[:40]}\\n{VERDICT_PL.get(v, v)}", shape=note, style=filled, '
             f'fillcolor="{fill}", penwidth=2];']
    ms = card["matches"]
    key = None
    if ms and v == "znana_kampania":
        key, kcol = max(ms, key=lambda m: m["score"] or 0)["id"], "#dc2626"
    elif ms and v == "znany_operator_nowa_kampania":
        key, kcol = max(ms, key=lambda m: m["operator_score"] or 0)["id"], "#ea580c"
    by_creator: dict[str, list[dict]] = {}
    for m in ms:
        by_creator.setdefault(m["creator"] or "(bez twórcy)", []).append(m)
    for i, (cname, group) in enumerate(by_creator.items()):
        lines.append(f'subgraph cluster_{i} {{ label="twórca: {esc(cname)[:40]}"; style="rounded"; color="#9ca3af"; fontsize=10;')
        for m in group:
            lines.append(f'"m:{esc(m["id"])}" [label="{esc(m["id"])}\\n{esc(m["snippet"])[:34]}", shape=box, style="rounded,filled", '
                         f'fillcolor="#f3f4f6"];')
        lines.append("}")
    for m in ms:
        why = esc((m["reasons"] or [""])[0])[:42]
        lab = f'kampania {m["score"] or 0:.2f} · operator {m["operator_score"] or 0:.2f}' + (f"\\n{why}" if why else "")
        if m["id"] == key:
            lines.append(f'"n" -> "m:{esc(m["id"])}" [label="{lab}", color="{kcol}", fontcolor="{kcol}", penwidth=2.5];')
        else:
            lines.append(f'"n" -> "m:{esc(m["id"])}" [label="{lab}", color="#9ca3af", fontcolor="#6b7280", style=dashed];')
    color = {"Payer": "#7c3aed", "Domain": "#2563eb", "Advertiser": "#059669"}
    for j, t in enumerate(card["traces"]):
        c = "#9ca3af" if t["common"] else color.get(t["kind"], "#6b7280")
        extra = "\\n(pospolita usługa: nie dowodzi)" if t["common"] else ""
        lines.append(f'"t{j}" [label="{KIND_PL.get(t["kind"], t["kind"])}:\\n{esc(t["name"])[:36]}{extra}", shape=ellipse, color="{c}", '
                     f'fontcolor="{c}"{", style=dotted" if t["common"] else ""}];')
        lines.append(f'"n" -> "t{j}" [dir=none, color="{c}"];')
        for o in t["shared"]:
            lines.append(f'"t{j}" -> "m:{esc(o)}" [dir=none, color="{c}"{", style=dotted" if t["common"] else ""}];')
    lines.append("}")
    return "\n".join(lines)


# --------------------------------------------------------------------------------------------------------------------
# Markdown (CLI, eksport)

def creator_markdown(card: dict) -> str:
    if not card:
        return "nie znaleziono twórcy"
    out = [f"# Twórca: {card['name']} [{card['id']}]", "",
           f"- etykieta: **{card['label']}** ({card['n_flagged']} z {card['n_ads']} reklam zdjętych przez Metę)",
           f"- strony: {card['n_pages']}, płatnicy: {card['n_payers']}, różne teksty: {card['texts']}, okres: {card['od']} – {card['do']}",
           f"- tematy (zapytania): {', '.join(card['topics']) or '—'}", "", "## Dlaczego to jeden twórca", ""]
    out += [f"- {KIND_PL[g['kind']]} **{g['name']}** łączy strony: {', '.join(g['pages'][:6])}"
            + (f" (+{len(g['pages']) - 6})" if len(g["pages"]) > 6 else "") + f" ({g['ads']} reklam)" for g in card["glue"][:15]]
    if not card["glue"]:
        out.append("- jedna strona, więc nic nie trzeba sklejać")
    if card["materials"]:
        out += ["", "## Przypadki NASK / nowe materiały", ""] + [f"- {m['id']}: {m['nazwa']}" for m in card["materials"]]
    return "\n".join(out)


def group_markdown(card: dict) -> str:
    if not card:
        return "nie znaleziono sieci ani kampanii"
    out = [f"# {card['id']}: {len(card['members'])} materiałów", "", "## Wspólne ślady (bez hubów)", ""]
    out += [f"- {REL_PL[s['rel']]} **{s['name']}**: {', '.join(s['ms'])}" for s in card["shared"][:20]]
    out += ["", "## Pary z wynikiem", ""]
    out += [f"- {p['a']} ↔ {p['b']}: {p['wynik']} ({p['relacja']}): {'; '.join((p['przesłanki'] or [])[:3])}" for p in card["pairs"][:20]]
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["creators", "creator", "group"])
    ap.add_argument("x", nargs="?")
    ap.add_argument("--label")
    a = ap.parse_args()
    drv = driver()
    with drv.session() as s:
        if a.what == "creators":
            for r in creators(s, a.label, limit=30):
                print(f"{r['twórca'][:40]:<40} {r['etykieta']:<13} reklam {r['reklam']:>5}  stron {r['stron']:>3}  {r['id']}")
        elif a.what == "creator":
            cid = find_creator(s, a.x)
            print(creator_markdown(creator_card(s, cid) if cid else {}))
        else:
            print(group_markdown(group_card(s, a.x)))
    drv.close()


if __name__ == "__main__":
    main()
