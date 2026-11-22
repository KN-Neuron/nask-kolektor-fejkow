"""Logika demonstratora bez zależności od Streamlita (testowalna): wejście -> cechy -> dopasowanie z przesłankami -> sieć.

Jedna ścieżka: dowolne z wejść (zrzut, HTML, HAR, JSON/JSONL z reklamami Meta, tekst, adres URL) składa się w jeden materiał (`Case`),
który idzie do `Gallery.query/add` (wzór podobieństwa: docs/14). Adres URL: domyślnie tylko domena jako ślad; z `fetch=True` pobieramy stronę (embsim/fetch.py) do HTML i HAR i dalej jak pliki.
"""
from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np

from .api import Decision, Gallery, has_evidence, Match, case_from_folder, case_from_meta_ad, case_from_text
from .features import Case, registered, scheme_fp

IMG_EXT = {".png", ".jpg", ".jpeg", ".webp"}
_CHANNEL_PL = {"text": "podobna treść", "text_lex": "podobne brzmienie tekstu", "kit": "ten sam zestaw zasobów strony",
               "scheme": "ten sam schemat parametrów adresu", "host": "wspólna domena", "pixel": "ten sam piksel śledzący",
               "image": "podobny wygląd", "img": "te same obrazy na stronie", "face": "ta sama osoba na obrazach"}
_EXTRA_PL = {"face": "wizerunek", "dhash": "bardzo podobny obraz (po zmianie rozmiaru, np. logo)", "payer": "ten sam płatnik", "page": "ta sama strona reklamodawcy", "text_hash": "identyczny tekst"}


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
                     vlm: bool = False, fetch: bool = False) -> tuple[Case, dict]:
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
        if fetch and url.strip():
            from .fetch import FetchError, fetch_to_folder

            try:
                fi = fetch_to_folder(url, root / "_pobrane")
                info["pobranie"] = fi
                info["url"] = (f"pobrano stronę {fi['adres_końcowy']} (status {fi['status']}, przekierowań {len(fi['przekierowania'])}, "
                               f"zasobów {fi['zasobów']}, obrazów {fi['obrazów']})")
            except FetchError as e:
                info["ostrzeżenia"].append(f"Nie udało się pobrać strony: {e}. Używam tylko domeny.")
        case = case_from_folder(root) if any(p.is_file() for p in root.rglob("*")) else Case(id="")
        texts = [case.text] if case.text else []
        if images and not case.text and not any(v for k, v in case.sets.items() if k not in ("img", "page", "payer", "text_hash")):
            case.meta["screenshot_only"] = True               # sam zrzut: identyczny obraz to ten sam artefakt (reguła dokładna), także po OCR
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
            if sch := scheme_fp(u):                       # schemat parametrów adresu (np. utm_visit, cuuid) bez odwiedzania strony
                case.sets.setdefault("scheme", set()).add(sch)
            case.meta["url"] = url.strip()
            info.setdefault("url", f"użyto tylko domeny {registered(host)} (adresu nie odwiedzamy)")
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
    extra = [f"{_EXTRA_PL.get(c, c)}: {', '.join(v[:2])}" for c, v in m.extra_shared.items()]
    face = [e for e in extra if e.startswith(_EXTRA_PL["face"])]
    return (out + extra)[:k] if not face or face[0] in (out + extra)[:k] else (out + extra)[: k - 1] + face[:1]   # wizerunek zawsze widoczny


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


def gallery_summary(g: Gallery) -> dict:
    return {"materiałów": len(g), "kampanii": len({it["group"] for it in g.items}), "operatorów": len({it["operator"] for it in g.items})}


# --------------------------------------------------------------------------------------------------------------------
# budowa galerii


def build_from_folders(g: Gallery, root: Path, ocr: bool = False, progress=None, regroup: bool = True) -> int:
    """Galeria z folderów przypadków (HTML, HAR, zrzuty). OCR tylko dla przypadków bez tekstu (sam zrzut), żeby było szybko."""
    from .material import load_case as material

    dirs = sorted((d for d in root.iterdir() if d.is_dir()), key=lambda d: (len(d.name), d.name))
    for i, d in enumerate(dirs):
        c = case_from_folder(d)
        c.id = d.name
        if ocr and not c.text.strip():
            c.text = "\n".join(t for t in (ocr_image(p)[0] for p in material(d).images[:3]) if t)
        if has_evidence(c):
            g.add(c)
        if progress:
            progress((i + 1) / len(dirs), d.name)
    if regroup:
        g.regroup()                                   # kampanie od nowa na pełnej galerii (bez zależności od kolejności)
    return len(dirs)


def build_from_meta(g: Gallery, path: Path, limit: int = 2000) -> int:
    n = 0
    for line in path.open(encoding="utf-8"):
        c = case_from_meta_ad(json.loads(line))
        if has_evidence(c):
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

TRACE_LABEL = {"img": "ten sam obraz", "host": "domena", "kit": "zestaw zasobów", "scheme": "schemat adresu", "pixel": "piksel",
               "payer": "płatnik",
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
    names = {k: v for i in idx for k, v in g.items[i]["case"].meta.get("img_names", {}).items()}   # obraz: nazwa pliku zamiast skrótu
    rows = [{"ślad": TRACE_LABEL[ch], "wartość": names.get(x, x) if ch == "img" else x, "materiały": ms, "w galerii": df[(ch, x)]}
            for (ch, x), ms in inside.items() if len(ms) >= 2 and df[(ch, x)] <= cap]
    imgs: dict[tuple, list[dict]] = {}                # obrazy wspólne dla tych samych materiałów: jeden wiersz (para 1–2 ma ich 11)
    for r in [r for r in rows if r["ślad"] == TRACE_LABEL["img"]]:
        imgs.setdefault((tuple(r["materiały"]), r["w galerii"]), []).append(r)
    rows = [r for r in rows if r["ślad"] != TRACE_LABEL["img"]] + [
        {**rs[0], "ślad": TRACE_LABEL["img"] if len(rs) == 1 else f"te same obrazy ({len(rs)})",
         "wartość": ", ".join(r["wartość"] for r in rs[:3]) + (" …" if len(rs) > 3 else "")} for rs in imgs.values()]
    rows.sort(key=lambda r: (r["w galerii"], -len(r["materiały"])))
    return rows


def _esc(s: object, n: int = 38) -> str:
    return str(s).replace('"', "'").replace("\\", "/").replace("\n", " ")[:n]


def _html(s: object, n: int = 60) -> str:
    t = str(s)
    t = t if len(t) <= n else t[: n - 1] + "…"
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def trace_boxes(g: Gallery, campaigns: dict[str, list[int]], traces: list[dict], max_boxes: int = 8) -> list[dict]:
    """Ślady zgrupowane po zbiorze materiałów, które łączą: jedna ramka = jeden zbiór i wszystko, co go skleja.

    Zwraca {"materiały", "ślady", "kampania" (gdy wszystkie w jednej kampanii, inaczej None), "kampanie"}; najpierw ramki łączące różne
    kampanie (to one tłumaczą, czemu kampanie są jednym operatorem), potem dowody kampanii; w obu grupach rzadsze ślady wyżej."""
    camp_of = {g.items[i]["case"].id: camp for camp, idx in campaigns.items() for i in idx}
    by: dict[tuple, list[dict]] = {}
    for t in traces:
        ms = tuple(sorted((m for m in t["materiały"] if m in camp_of), key=lambda m: (len(m), m)))
        if len(ms) >= 2:
            by.setdefault(ms, []).append(t)
    boxes = []
    for ms, ts in by.items():
        cs = sorted({camp_of[m] for m in ms})
        boxes.append({"materiały": list(ms), "ślady": ts, "kampania": cs[0] if len(cs) == 1 else None, "kampanie": cs,
                      "siła": min(t["w galerii"] for t in ts)})
    boxes.sort(key=lambda b: (b["kampania"] is not None, b["siła"], -len(b["ślady"])))
    return boxes[:max_boxes]


def _box_label(b: dict, max_lines: int = 3) -> str:
    head = ("dowód kampanii " + b["kampania"]) if b["kampania"] else "łączy kampanie " + ", ".join(b["kampanie"])
    rows = [f'<tr><td align="left"><b>{_html(head)}</b></td></tr>']
    for t in b["ślady"][:max_lines]:
        rows.append(f'<tr><td align="left">{_html(t["ślad"], 22)}: {_html(t["wartość"], 30)}</td></tr>')
    if len(b["ślady"]) > max_lines:
        rows.append(f'<tr><td align="left"><i>+{len(b["ślady"]) - max_lines} innych śladów</i></td></tr>')
    return '<<table border="0" cellborder="0" cellspacing="1">' + "".join(rows) + "</table>>"


def cluster_dot(g: Gallery, campaigns: dict[str, list[int]], title: str, traces: list[dict], max_materials: int = 24, max_traces: int = 8) -> str:
    """Rysunek klastra: operator (ramka) -> kampanie (zielone ramki) -> materiały. Ślady zgrupowane po zbiorze materiałów, które łączą
    (`trace_boxes`): dowód jednej kampanii (czerwona ramka) siedzi w środku jej ramki, ślad łączący kampanie (niebieska) na zewnątrz,
    więc krawędzi jest tyle, ile materiałów w ramkach, a nie po jednej na każdy ślad."""
    boxes = trace_boxes(g, campaigns, traces, max_traces)
    inner = {}
    for n, b in enumerate(boxes):
        if b["kampania"]:
            inner.setdefault(b["kampania"], []).append(n)
    lines = ["graph G {", 'rankdir=LR; bgcolor="white"; nodesep=0.25; ranksep=0.5; splines=true;',
             'node [fontname="Helvetica", fontsize=10]; edge [penwidth=1.3];',
             f'subgraph cluster_op {{ label="{_esc(title, 60)}"; style="rounded"; color="#ff7f0e"; fontname="Helvetica";']
    shown: set[str] = set()
    for k, (camp, idx) in enumerate(sorted(campaigns.items())):
        lines.append(f'subgraph cluster_k{k} {{ label="kampania {_esc(camp)}"; style="rounded"; color="#2ca02c"; fontname="Helvetica";')
        for i in idx[: max(1, max_materials // max(len(campaigns), 1))]:
            c = g.items[i]["case"]
            shown.add(c.id)
            snippet = _esc(c.text.strip().splitlines()[0] if c.text.strip() else "(bez tekstu)", 24)
            lines.append(f'"m:{_esc(c.id)}" [label="{_esc(c.id)}\\n{snippet}", shape=box, style="rounded,filled", fillcolor="#eef3fb"];')
        for n in inner.get(camp, []):
            lines.append(f'"b{n}" [label={_box_label(boxes[n])}, shape=box, style="rounded,filled", fillcolor="#fdecea", color="#c0392b"];')
        lines.append("}")
    lines.append("}")
    for n, b in enumerate(boxes):
        if not b["kampania"]:
            lines.append(f'"b{n}" [label={_box_label(b)}, shape=box, style="rounded,filled", fillcolor="#e8f1fb", color="#2b6cb0"];')
        col = "#c0392b" if b["kampania"] else "#2b6cb0"
        lines += [f'"b{n}" -- "m:{_esc(m)}" [color="{col}"];' for m in b["materiały"] if m in shown]
    lines.append("}")
    return "\n".join(lines)


def cluster_summary(g: Gallery, campaigns: dict[str, list[int]], traces: list[dict]) -> list[str]:
    """„Co z tego wynika” w zdaniach: która grupa to jedna kampania i dlaczego, co łączy kampanie w jednego operatora."""
    out = []
    for b in trace_boxes(g, campaigns, traces, max_boxes=12):
        ms = ", ".join(b["materiały"])
        why = "; ".join(f"{t['ślad']}: {t['wartość']}" for t in b["ślady"][:3]) + ("; …" if len(b["ślady"]) > 3 else "")
        if b["kampania"]:
            out.append(f"**{ms}** to jedna kampania ({b['kampania']}): {why}")
        else:
            out.append(f"**{ms}** (kampanie {', '.join(b['kampanie'])}) łączy {why}, dlatego to jeden operator")
    singles = [c for c, idx in campaigns.items() if len(idx) == 1]
    if len(campaigns) > 1 and not any(not b["kampania"] for b in trace_boxes(g, campaigns, traces, 12)):
        out.append("Kampanie tego operatora nie mają wspólnych rzadkich śladów: połączenie wynika z podobieństwa (wynik operatora).")
    if singles and len(campaigns) == 1:
        out.append("Jeden materiał: nic nie trzeba sklejać.")
    return out


def network_dot(case: Case, d: Decision, k: int = 5) -> str:
    """Rysunek dopasowania: nowy materiał po lewej, najbliższe materiały w ramkach kampanii i operatorów, na krawędzi wynik i powód.
    Krawędź czerwona = znana kampania (wynik ≥ próg), pomarańczowa = ten sam operator, szara przerywana = za słabe, żeby łączyć."""
    tc, to = d.thresholds.get("campaign") or 1.0, d.thresholds.get("operator") or 1.0
    ms = list(d.matches[:k])
    key = d.key_match()
    if key is not None and key not in ms:
        ms.append(key)
    lines = ["digraph G {", 'rankdir=LR; bgcolor="white"; nodesep=0.3; ranksep=1.2;',
             'node [fontname="Helvetica", fontsize=10]; edge [fontname="Helvetica", fontsize=9];',
             f'"NOWY" [label="nowy materiał\\n{_esc(case.id, 24)}", shape=box, style="rounded,filled", fillcolor="#fdecea", color="#c0392b", penwidth=2];']
    ops: dict[str, dict[str, list]] = {}
    for m in ms:
        ops.setdefault(m.operator or "?", {}).setdefault(m.group or "?", []).append(m)
    for a, (op, camps) in enumerate(sorted(ops.items())):
        lines.append(f'subgraph cluster_o{a} {{ label="operator {_esc(op)}"; style="rounded"; color="#ff7f0e"; fontname="Helvetica";')
        for b, (camp, mm) in enumerate(sorted(camps.items())):
            lines.append(f'subgraph cluster_o{a}k{b} {{ label="kampania {_esc(camp)}"; style="rounded"; color="#2ca02c"; fontname="Helvetica";')
            lines += [f'"m:{_esc(m.id)}" [label="{_esc(m.id)}", shape=box, style="rounded,filled", fillcolor="#eef3fb"];' for m in mm]
            lines.append("}")
        lines.append("}")
    for m in ms:
        reason = top_reasons(m, 1)
        lab = f"kampania {m.campaign_score:.2f} · operator {m.operator_score:.2f}" + (f"\\n{_esc(reason[0], 48)}" if reason else "")
        if m.campaign_score >= tc and m is d.matches[0] or (d.exact_of == m.id):
            style = 'color="#c0392b", penwidth=2.5'
        elif m.operator_score >= to:
            style = 'color="#e67e22", penwidth=2'
        else:
            style = 'color="#aaaaaa", style=dashed'
        lines.append(f'"NOWY" -> "m:{_esc(m.id)}" [label="{lab}", {style}];')
    lines.append("}")
    return "\n".join(lines)


def cluster_markdown(title: str, materials: list[dict], traces: list[dict]) -> str:
    out = [f"# Klaster: {title}", "", f"Materiałów: {len(materials)}", "", "## Co skleja ten klaster", ""]
    out += [f"- {t['ślad']}: `{t['wartość']}` ({len(t['materiały'])} materiałów, w galerii {t['w galerii']})" for t in traces] or [
        "- brak wspólnych śladów poza hubami; grupowanie wynika z podobieństwa treści"]
    out += ["", "## Materiały", "", "| materiał | kampania | operator | początek tekstu |", "|---|---|---|---|"]
    out += [f"| {m['materiał']} | {m['kampania']} | {m['operator']} | {m['tekst']} |" for m in materials]
    return "\n".join(out)


# --------------------------------------------------------------------------------------------------------------------
# wiele materiałów naraz (zbiór testowy: ZIP albo folder, podfolder = materiał)


def extract_zip(data: bytes, dest: Path) -> Path:
    """Rozpakowuje ZIP do `dest` (bez ścieżek wychodzących poza `dest`). Zwraca katalog z materiałami: jeśli całe archiwum siedzi
    w jednym folderze (typowe „Kompresuj folder”), schodzi do niego."""
    import io

    dest = dest.resolve()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for info in z.infolist():
            name = info.filename
            if name.startswith("__MACOSX/") or Path(name).name.startswith("._"):
                continue
            target = (dest / name).resolve()
            if not target.is_relative_to(dest):
                raise ValueError(f"niebezpieczna ścieżka w archiwum: {name}")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read(info))
    root = dest
    while True:
        kids = [k for k in root.iterdir() if not k.name.startswith(".")]
        if len(kids) == 1 and kids[0].is_dir() and any(c.is_dir() for c in kids[0].iterdir()):
            root = kids[0]
        else:
            return root


def case_dirs(root: Path) -> list[Path]:
    """Podfoldery = materiały; folder bez podfolderów (albo z samymi zasobami `*_files`) to jeden materiał."""
    dirs = [d for d in root.iterdir() if d.is_dir() and not d.name.startswith((".", "__")) and not d.name.endswith("_files")]
    return sorted(dirs, key=lambda d: (len(d.name), d.name)) if dirs else [root]


def assess_folder(g: Gallery, root: Path, keep: bool = False, ocr: bool = False, progress=None) -> tuple[list[dict], Gallery]:
    """Ocena zbioru materiałów: każdy po kolei dostaje decyzję względem galerii i trafia do niej, więc kilka nowych materiałów jednej
    kampanii łączy się także między sobą. `keep=False`: praca na kopii, galeria w interfejsie zostaje bez zmian."""
    from .material import load_case as material

    gg = g if keep else copy.deepcopy(g)
    rows, dirs = [], case_dirs(root)
    for i, d in enumerate(dirs):
        c = case_from_folder(d)
        c.id = d.name if d.name not in gg._ids else f"{d.name} (nowy)"
        if ocr and not c.text.strip():
            c.text = "\n".join(t for t in (ocr_image(p)[0] for p in material(d).images[:3]) if t)
        if not (c.text.strip() or c.sets):
            rows.append({"materiał": d.name, "werdykt": "brak danych (pusty folder albo nieobsługiwane pliki)"})
            continue
        dec = gg.add(c)
        m = dec.key_match()
        rows.append({"materiał": c.id, "werdykt": verdict_style(dec)[1], "kampania": dec.group, "operator": dec.operator,
                     "najbliższy": m.id if m else "", "wynik kampanii": round(dec.campaign_score, 3),
                     "wynik operatora": round(dec.operator_score, 3), "powody": "; ".join(top_reasons(m)) if m else ""})
        if progress:
            progress((i + 1) / len(dirs), d.name)
    return rows, gg
