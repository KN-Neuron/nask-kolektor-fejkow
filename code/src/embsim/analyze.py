"""Logika demonstratora bez zależności od Streamlita (testowalna): wejście -> cechy -> dopasowanie z przesłankami -> sieć.

Jedna ścieżka: dowolne z wejść (zrzut, HTML, HAR, JSON/JSONL z reklamami Meta, tekst, adres URL) składa się w jeden materiał (`Case`),
który idzie do `Gallery.query/add` (wzór podobieństwa: docs/14). Adresów URL NIE odwiedzamy: bierzemy tylko domenę jako ślad.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np

from .api import Decision, Gallery, Match, case_from_folder, case_from_meta_ad, case_from_text
from .features import Case, registered

IMG_EXT = {".png", ".jpg", ".jpeg", ".webp"}
_CHANNEL_PL = {"text": "podobna treść", "text_lex": "podobne brzmienie tekstu", "kit": "ten sam zestaw zasobów strony",
               "scheme": "ten sam schemat parametrów adresu", "host": "wspólna domena", "pixel": "ten sam piksel śledzący",
               "image": "podobny wygląd"}
_EXTRA_PL = {"payer": "ten sam płatnik", "page": "ta sama strona reklamodawcy", "text_hash": "identyczny tekst"}


# --------------------------------------------------------------------------------------------------------------------
# OCR zrzutu (opcjonalny, z łagodną degradacją)


def ocr_languages() -> list[str]:
    try:
        import pytesseract

        return pytesseract.get_languages(config="")
    except Exception:
        return []


def ocr_image(path: Path) -> tuple[str, str | None]:
    """Tekst ze zrzutu. Zwraca (tekst, użyty język); (\"\", None), gdy OCR niedostępny. Bez języka polskiego jakość jest niższa."""
    langs = ocr_languages()
    if not langs:
        return "", None
    use = "+".join(l for l in ("pol", "eng") if l in langs) or langs[0]
    try:
        import pytesseract
        from PIL import Image

        return " ".join(pytesseract.image_to_string(Image.open(path).convert("RGB"), lang=use).split()), use
    except Exception:
        return "", None


# --------------------------------------------------------------------------------------------------------------------
# wejście -> materiał


def case_from_inputs(files: list[tuple[str, bytes]], text: str = "", url: str = "", ocr: bool = True, case_id: str | None = None,
                     vlm: bool = False) -> tuple[Case, dict]:
    """Składa jeden materiał z przesłanych plików (nazwa, bajty), tekstu i adresu. Zwraca (materiał, informacje o przetwarzaniu).

    `vlm=True`: dodatkowo opis kreacji zrzutu modelem wizyjnym (embsim/vlm.py, Ollama); bez modelu pomijany z ostrzeżeniem.
    """
    info: dict = {"pliki": [n for n, _ in files], "ocr_język": None, "ocr_znaków": 0, "ostrzeżenia": []}
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "wejscie"
        root.mkdir()
        images = []
        for name, data in files:
            low = name.lower()
            if low.endswith((".jsonl", ".json")) and not low.endswith(".info.json"):
                try:
                    recs = [json.loads(l) for l in data.decode("utf-8").splitlines() if l.strip()] if low.endswith(".jsonl") else json.loads(data)
                    recs = recs if isinstance(recs, list) else [recs]
                    if recs and "id" in recs[0] and ("page_id" in recs[0] or "ad_creative_bodies" in recs[0]):
                        c = case_from_meta_ad(recs[0])
                        info["źródło"] = f"reklama Meta (1 z {len(recs)} rekordów w pliku)"
                        return c, info
                except (ValueError, KeyError):
                    pass
            (root / Path(name).name).write_bytes(data)
            if Path(name).suffix.lower() in IMG_EXT:
                images.append(root / Path(name).name)
        case = case_from_folder(root) if any(p.is_file() for p in root.iterdir()) else Case(id="")
        texts = [case.text] if case.text else []
        if images and ocr:
            for im in images:
                t, lang = ocr_image(im)
                if lang is None:
                    info["ostrzeżenia"].append("OCR niedostępny (brak tesseract): zrzut nie daje tekstu.")
                    break
                info["ocr_język"] = lang
                info["ocr_znaków"] += len(t)
                if t:
                    texts.append(t)
            if info["ocr_język"] and "pol" not in info["ocr_język"]:
                info["ostrzeżenia"].append("OCR bez języka polskiego: jakość rozpoznania tekstu jest niższa.")
        elif images and not ocr:
            info["ostrzeżenia"].append("Zrzut dodany, ale OCR wyłączony: bez tekstu i bez śladów dopasowanie będzie słabe.")
        if images and vlm:
            from . import vlm as _vlm

            descs = [(_vlm.describe(im)) for im in images]
            got = [d for d in descs if d]
            info["vlm_opisów"] = len(got)
            if got:
                texts.extend(t for t in (_vlm.to_text(d) for d in got) if t)
                info["vlm"] = got
            else:
                info["ostrzeżenia"].append("Opis kreacji (VLM) niedostępny: uruchom Ollama i `ollama pull " + _vlm.MODEL + "`.")
        if text.strip():
            texts.append(text.strip())
        case.text = "\n".join(texts)
    if url.strip():
        u = url.strip() if "://" in url else "http://" + url.strip()
        host = (urlsplit(u).hostname or "").lower()
        if host:
            case.sets.setdefault("host", set()).add(registered(host))
            case.meta["url"] = url.strip()
            info["url"] = f"użyto tylko domeny {registered(host)} (adresu nie odwiedzamy)"
    case.id = case_id or "nowy_" + hashlib.sha1((case.text + json.dumps({k: sorted(v) for k, v in case.sets.items()})).encode()).hexdigest()[:8]
    return case, info


# --------------------------------------------------------------------------------------------------------------------
# wynik: przesłanki, pewność, karta


def confidence_label(evidence: float) -> str:
    return "wysoka" if evidence >= 0.8 else "średnia" if evidence >= 0.5 else "niska (mało danych do porównania)"


def top_reasons(m: Match, k: int = 3) -> list[str]:
    """Trzy najsilniejsze powody połączenia: kanały wyniku (z wartością) i dokładne zgodności poza wynikiem."""
    out = [f"{_CHANNEL_PL.get(c, c)} ({v:.2f})" + (": " + ", ".join(m.shared[c][:2]) if c in m.shared else "")
           for c, v in sorted(m.channels.items(), key=lambda kv: -kv[1]) if v > 0]
    out += [f"{_EXTRA_PL.get(c, c)}: {', '.join(v[:2])}" for c, v in m.extra_shared.items()]
    return out[:k]


def verdict_style(d: Decision) -> tuple[str, str]:
    return {"znana_kampania": ("success", "Znana kampania"), "znany_operator_nowa_kampania": ("warning", "Znany operator, nowa kampania"),
            "nowy_wzorzec": ("info", "Nowy wzorzec, nie doklejam do żadnej grupy")}.get(d.verdict, ("info", d.verdict))


def card_markdown(case: Case, d: Decision) -> str:
    """Karta dla analityka (Markdown): wniosek, powody, najbliższe materiały."""
    lines = [f"# Karta materiału {case.id}", "", f"**Wniosek:** {verdict_style(d)[1]}", "", d.explain(), "", "## Najbliższe materiały", "",
             "| materiał | kampania | operator | wynik kampanii | wynik operatora | trzy najsilniejsze powody |", "|---|---|---|---|---|---|"]
    for m in d.matches:
        lines.append(f"| {m.id} | {m.group or '-'} | {m.operator or '-'} | {m.campaign_score:.2f} | {m.operator_score:.2f} | "
                     f"{'; '.join(top_reasons(m)) or '-'} |")
    lines += ["", f"Progi: kampania {d.thresholds.get('campaign')}, operator {d.thresholds.get('operator')}. "
              "Progi dobrane na syntetyce; na prawdziwych kampaniach niesprawdzone (zob. docs/WYNIKI.md)."]
    return "\n".join(lines)


def network_figure(case: Case, d: Decision):
    """Sieć: nowy materiał, jego najbliższe dopasowania, ich kampanie i operatorzy (plotly)."""
    import networkx as nx
    import plotly.graph_objects as go

    G = nx.Graph()
    G.add_node("NOWY", kind="nowy", label=case.id)
    for m in d.matches:
        G.add_node(m.id, kind="materiał", label=m.id)
        G.add_edge("NOWY", m.id, w=max(m.campaign_score, 0.05))
        if m.group:
            G.add_node("K:" + m.group, kind="kampania", label=m.group)
            G.add_edge(m.id, "K:" + m.group, w=1.0)
            if m.operator:
                G.add_node("O:" + m.operator, kind="operator", label=m.operator)
                G.add_edge("K:" + m.group, "O:" + m.operator, w=1.0)
    pos = nx.spring_layout(G, seed=3, weight="w", k=0.9)
    color = {"nowy": "#d62728", "materiał": "#1f77b4", "kampania": "#2ca02c", "operator": "#ff7f0e"}
    ex, ey = [], []
    for a, b in G.edges:
        ex += [pos[a][0], pos[b][0], None]
        ey += [pos[a][1], pos[b][1], None]
    fig = go.Figure([go.Scatter(x=ex, y=ey, mode="lines", line=dict(width=1, color="#999"), hoverinfo="none")])
    for kind, c in color.items():
        ns = [n for n, a in G.nodes(data=True) if a["kind"] == kind]
        if ns:
            fig.add_trace(go.Scatter(x=[pos[n][0] for n in ns], y=[pos[n][1] for n in ns], mode="markers+text", name=kind,
                                     text=[G.nodes[n]["label"] for n in ns], textposition="top center",
                                     marker=dict(size=18 if kind != "materiał" else 12, color=c)))
    fig.update_layout(showlegend=True, xaxis=dict(visible=False), yaxis=dict(visible=False), height=420, margin=dict(l=10, r=10, t=10, b=10))
    return fig


def gallery_summary(g: Gallery) -> dict:
    return {"materiałów": len(g), "kampanii": len({it["group"] for it in g.items}), "operatorów": len({it["operator"] for it in g.items})}


# --------------------------------------------------------------------------------------------------------------------
# budowa galerii


def build_from_folders(g: Gallery, root: Path, ocr: bool = False, progress=None) -> int:
    """Galeria z folderów przypadków (HTML, HAR, zrzuty). OCR tylko dla przypadków bez tekstu (sam zrzut), żeby było szybko."""
    from .material import load_case as material

    dirs = sorted((d for d in root.iterdir() if d.is_dir()), key=lambda d: (len(d.name), d.name))
    for i, d in enumerate(dirs):
        c = case_from_folder(d)
        c.id = d.name
        if ocr and not c.text.strip():
            c.text = "\n".join(t for t in (ocr_image(p)[0] for p in material(d).images[:3]) if t)
        if c.text.strip() or c.sets:
            g.add(c)
        if progress:
            progress((i + 1) / len(dirs), d.name)
    return len(dirs)


def build_from_meta(g: Gallery, path: Path, limit: int = 2000) -> int:
    n = 0
    for line in path.open(encoding="utf-8"):
        c = case_from_meta_ad(json.loads(line))
        if c.text.strip() or c.sets:
            g.add(c)
            n += 1
        if n >= limit:
            break
    return n


def hash_embed(texts, dim: int = 96):
    """Deterministyczny zamiennik embeddingu bez modelu (testy, tryb offline): worek słów z haszowaniem."""
    V = np.zeros((len(texts), dim))
    for i, t in enumerate(texts):
        for w in t.lower().split():
            V[i, int(hashlib.md5(w.encode()).hexdigest(), 16) % dim] += 1
    return V / np.maximum(np.linalg.norm(V, axis=1, keepdims=True), 1e-9)


# --------------------------------------------------------------------------------------------------------------------
# klastry w galerii (bez bazy): operator -> kampanie -> materiały, plus ślady, które je sklejają

TRACE_LABEL = {"host": "domena", "kit": "zestaw zasobów", "scheme": "schemat adresu", "pixel": "piksel", "payer": "płatnik",
               "page": "strona reklamodawcy", "text_hash": "identyczny tekst"}
HUB_FRACTION = 0.2          # ślad obecny w więcej niż 20% galerii (min. 10 materiałów) niczego nie dowodzi (tracker, CDN)


def cluster_index(g: Gallery) -> dict[str, dict[str, list[int]]]:
    """operator -> kampania -> indeksy materiałów w galerii."""
    out: dict[str, dict[str, list[int]]] = {}
    for i, it in enumerate(g.items):
        out.setdefault(it["operator"] or "?", {}).setdefault(it["group"] or "?", []).append(i)
    return out


def shared_traces(g: Gallery, idx: list[int]) -> list[dict]:
    """Ślady wspólne dla ≥2 materiałów wskazanego klastra, bez hubów; rzadkie (najmocniejsze) najpierw."""
    from collections import Counter, defaultdict

    cap = max(10, int(HUB_FRACTION * len(g.items)))
    df = Counter((ch, x) for it in g.items for ch, s in it["case"].sets.items() if ch in TRACE_LABEL for x in s)
    inside: dict[tuple, list[str]] = defaultdict(list)
    for i in idx:
        for ch, s in g.items[i]["case"].sets.items():
            if ch in TRACE_LABEL:
                for x in s:
                    inside[(ch, x)].append(g.items[i]["case"].id)
    rows = [{"ślad": TRACE_LABEL[ch], "wartość": x, "materiały": ms, "w galerii": df[(ch, x)]}
            for (ch, x), ms in inside.items() if len(ms) >= 2 and df[(ch, x)] <= cap]
    rows.sort(key=lambda r: (r["w galerii"], -len(r["materiały"])))
    return rows


def _esc(s: object, n: int = 38) -> str:
    return str(s).replace('"', "'").replace("\\", "/").replace("\n", " ")[:n]


def cluster_dot(g: Gallery, campaigns: dict[str, list[int]], title: str, traces: list[dict], max_materials: int = 24, max_traces: int = 12) -> str:
    """Rysunek: operator (ramka) -> kampanie (ramki) -> materiały, a obok owalne ślady łączące materiały. Układ bez fizyki."""
    lines = ["graph G {", 'rankdir=LR; bgcolor="transparent"; node [fontname="Helvetica", fontsize=10];',
             f'subgraph cluster_op {{ label="{_esc(title, 60)}"; style="rounded"; color="#ff7f0e"; fontname="Helvetica";']
    shown: set[str] = set()
    for k, (camp, idx) in enumerate(sorted(campaigns.items())):
        lines.append(f'subgraph cluster_k{k} {{ label="kampania {_esc(camp)}"; style="rounded"; color="#2ca02c"; fontname="Helvetica";')
        for i in idx[: max(1, max_materials // max(len(campaigns), 1))]:
            c = g.items[i]["case"]
            shown.add(c.id)
            snippet = _esc(c.text.strip().splitlines()[0] if c.text.strip() else "(bez tekstu)", 30)
            lines.append(f'"m:{_esc(c.id)}" [label="{_esc(c.id)}\\n{snippet}", shape=box, style="rounded,filled", fillcolor="#eef3fb"];')
        lines.append("}")
    lines.append("}")
    for j, t in enumerate(traces[:max_traces]):
        ms = [m for m in t["materiały"] if m in shown]
        if len(ms) < 2:
            continue
        lines.append(f'"t{j}" [label="{t["ślad"]}:\\n{_esc(t["wartość"])}\\n({len(t["materiały"])} mat.)", shape=ellipse, style=filled, '
                     f'fillcolor="#fff7d6", color="#b8860b"];')
        lines += [f'"t{j}" -- "m:{_esc(m)}" [color="#b8860b"];' for m in ms]
    lines.append("}")
    return "\n".join(lines)


def cluster_markdown(title: str, materials: list[dict], traces: list[dict]) -> str:
    out = [f"# Klaster: {title}", "", f"Materiałów: {len(materials)}", "", "## Co skleja ten klaster", ""]
    out += [f"- {t['ślad']}: `{t['wartość']}` ({len(t['materiały'])} materiałów, w galerii {t['w galerii']})" for t in traces] or [
        "- brak wspólnych śladów poza hubami; grupowanie wynika z podobieństwa treści"]
    out += ["", "## Materiały", "", "| materiał | kampania | operator | początek tekstu |", "|---|---|---|---|"]
    out += [f"| {m['materiał']} | {m['kampania']} | {m['operator']} | {m['tekst']} |" for m in materials]
    return "\n".join(out)
