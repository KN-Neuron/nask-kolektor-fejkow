"""Kolekcjoner Fejków: demonstrator. Uruchomienie: `fejki demo app` albo `streamlit run src/fejki/app/demo_app.py`.

Wejście: folder przypadku ze zbioru, pliki (HTML, HAR, zrzut, nagranie, info.json), adres URL albo tekst / nazwa produktu.
Wynik: cechy materiału, dopasowanie do znanych kampanii z uzasadnieniem, kampanie i sieci operatorów, graf powiązań.
Strony oszustów nie są odwiedzane: korzystamy z plików nagranych przez organizatora i z biernych źródeł (DNS, RDAP, crt.sh).
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from fejki.config import ROOT
from fejki.demo import store
from fejki.demo.cards import all_markdown, build_cards, card_markdown, domains_csv
from fejki.demo.material import Material, material_from_inputs
from fejki.demo.similar import CHANNELS, CONTENT_RELATIONS, W, all_pairs, campaigns, confidence_label, match

DEFAULT_DATA = Path(os.environ.get("FEJKI_DATA") or ROOT.parent / "data" / "dane" / "do_udostępnienia")

st.set_page_config(page_title="Kolekcjoner Fejków", page_icon="🕵️", layout="wide")


# --- stan ----------------------------------------------------------------------------------------------------------

@st.cache_resource
def _load_index():
    return store.load()


def index() -> store.Index | None:
    if "index" not in st.session_state:
        st.session_state.index = _load_index()
    return st.session_state.index


def infra_or_none(idx):
    if st.session_state.get("use_infra") and idx and idx.infra:
        return store.infra_records(idx)
    return None


def _pair_model():
    return json.loads(_pm_path.read_text(encoding="utf-8")) if st.session_state.get("use_model") and _pm_path.exists() else None


@st.cache_data(show_spinner="Liczę podobieństwa…")
def _pairs(materials_json: str, infra_json: str, semantic: bool = False, visual: bool = False, model_json: str = ""):
    mats = [Material.model_validate(m) for m in json.loads(materials_json)]
    infra = None
    if infra_json != "{}":
        from fejki.infra.collect import InfraRecord

        infra = {d: InfraRecord.model_validate(r) for d, r in json.loads(infra_json).items()}
    vec = None
    if visual:
        from fejki.demo.vision import material_vectors

        vec = material_vectors(mats)
    return [p.model_dump() for p in all_pairs(mats, infra, semantic, vec, json.loads(model_json) if model_json else None)]


def get_pairs(idx):
    from fejki.demo.similar import Pair

    infra = idx.infra if st.session_state.get("use_infra") else {}
    raw = _pairs(json.dumps([m.model_dump() for m in idx.materials]), json.dumps(infra, sort_keys=True),
                 bool(st.session_state.get("use_sem")), bool(st.session_state.get("use_vis")),
                 json.dumps(_pair_model()) if _pair_model() else "")
    return [Pair.model_validate(p) for p in raw]


# --- pasek boczny --------------------------------------------------------------------------------------------------

st.sidebar.title("🕵️ Kolekcjoner Fejków")
st.sidebar.caption("Łączenie podejrzanych reklam w kampanie, z uzasadnieniem każdego powiązania.")
idx = index()
if idx:
    st.sidebar.success(f"Zbiór: {len(idx.materials)} materiałów (zbudowany {idx.built_at[:16].replace('T', ' ')} UTC)")
else:
    st.sidebar.warning("Brak indeksu. Zbuduj go poniżej.")

thr = st.sidebar.slider("Próg powiązania", 0.4, 0.95, 0.7, 0.05,
                        help="Krawędź powstaje, gdy łączny wynik dowodów przekracza próg. Wyższy próg = mniej, ale pewniejszych powiązań.")
maybe = st.sidebar.slider("Próg „do weryfikacji”", 0.2, 0.7, 0.4, 0.05)
st.session_state.use_infra = st.sidebar.toggle("Kanał infrastruktury (DNS, RDAP, crt.sh)", value=bool(idx and idx.infra),
                                               help="Dane bierne z publicznych źródeł; wymaga sieci. Strony oszustów nie są odwiedzane.")

st.session_state.use_sem = st.sidebar.toggle(
    "Kanał semantyczny (bge-m3)", value=False,
    help="Podobieństwo znaczenia tekstu (model BAAI/bge-m3, MIT, ~2,2 GB, musi być pobrany). Wolniejsze liczenie przy pierwszym użyciu.")

from fejki.demo import vision as _vision  # noqa: E402

_vis_ok = _vision.model_available()
st.session_state.use_vis = st.sidebar.toggle(
    "Kanał obrazu (PE-Core)", value=False, disabled=not _vis_ok,
    help="Embeddingi zrzutów i kreacji (Meta Perception Encoder B/16, Apache-2.0, 1,8 GB). Wyłączony, gdy model nie jest pobrany.")
_pm_path = ROOT / "artifacts" / "demo" / "pair_model.json"
st.session_state.use_model = st.sidebar.toggle(
    "Wyuczony model par", value=False, disabled=not _pm_path.exists(),
    help="Wynik pary z regresji logistycznej uczonej na zbiorze urlscan (zamiast ręcznych wag). Przesłanki bez zmian.")

with st.sidebar.expander("Zbiór danych i indeks"):
    data_dir = st.text_input("Folder z przypadkami", str(DEFAULT_DATA))
    _us = ROOT.parent / "data" / "urlscan"
    extra_dir = st.text_input("Dodatkowy zbiór referencyjny (np. skany urlscan)", str(_us) if _us.exists() else "",
                              help="Skany dołożone do wiedzy referencyjnej: narzędzie rozpozna więcej znanych zestawów stron.")
    do_ocr = st.checkbox("OCR zrzutów i klatek wideo", value=True)
    if st.button("Zbuduj / przebuduj indeks", use_container_width=True):
        bar = st.progress(0.0, "start")
        new = store.build(Path(data_dir), ocr=do_ocr, progress=lambda k, n, d: bar.progress((k + 1) / n, f"przypadek {d}"),
                          extra=[Path(extra_dir)] if extra_dir.strip() else None)
        if idx and idx.infra:
            new.infra = idx.infra
        store.save(new)
        st.session_state.index = new
        st.cache_data.clear()
        st.rerun()
    if idx and st.button("Zbierz dane infrastruktury (bierne)", use_container_width=True):
        with st.spinner("DNS, RDAP, crt.sh…"):
            errs = store.collect_infra(idx)
        store.save(idx)
        st.cache_data.clear()
        st.info(f"Domen z danymi: {len(idx.infra)}" + (f"; problemy: {'; '.join(errs[:5])}" if errs else ""))

if not idx or not idx.materials:
    st.title("Kolekcjoner Fejków")
    st.info("Zbuduj indeks w panelu bocznym („Zbiór danych i indeks”), wskazując folder z przypadkami.")
    st.stop()

pairs = get_pairs(idx)
camps = campaigns(idx.materials, pairs, thr, "kampania")
nets = campaigns(idx.materials, pairs, thr, "sieć")
camp_of = {m: c.id for c in camps for m in c.members}
net_of = {m: n.id for n in nets for m in n.members}
by_id = idx.by_id()


def show_material(m: Material, compact: bool = False):
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**Treść**")
        st.write("Tytuły:", "; ".join(t[:90] for t in m.titles) or "—")
        st.write("Tematyka:", ", ".join(f"{k} ({v})" for k, v in list(m.topics.items())[:3]) or "—")
        st.write("Osoby:", ", ".join(f"{k} ×{v}" for k, v in m.person_counts.items()) or "—")
        st.write("Produkt:", ", ".join(m.products) or "—")
        st.write("Reklamodawca (z kreacji):", ", ".join(m.advertisers) or "—")
        st.write("Słowa kluczowe:", ", ".join(m.keywords[:12]) or "—")
    with c2:
        st.markdown("**Adresy i śledzenie**")
        st.write("Domeny docelowe:", ", ".join(m.landing_domains) or "—")
        st.write("Usługi zewnętrzne (nietypowe):", ", ".join(m.third_party_hosts[:8]) or "—")
        st.write("Identyfikatory reklam Meta:", ", ".join(m.ad_ids) or "—")
        st.write("Piksele Meta:", ", ".join(m.pixel_ids) or "—")
        st.write("Inne identyfikatory:", ", ".join(m.tracker_ids + [f"acc={a}" for a in m.ad_accounts]) or "—")
        st.write("Schemat parametrów:", "; ".join(s[:90] for s in m.url_schemes[:2]) or "—")
        st.write("Przekierowania (z HAR):", "; ".join(m.redirects[:4]) or "—")
    with c3:
        st.markdown("**Obraz, struktura, braki**")
        roles = pd.Series([i.role for i in m.images]).value_counts().to_dict() if m.images else {}
        st.write("Obrazy (pHash):", ", ".join(f"{k}: {v}" for k, v in roles.items()) or "—")
        st.write("Stron w materiale:", m.pages)
        if m.cloaking:
            st.warning("Możliwy cloaking: " + m.cloaking[0])
        if m.missing:
            st.write("Braki:", "; ".join(m.missing))
        for n in m.notes[:4]:
            st.caption(n)
    if not compact and m.ocr_text:
        with st.expander("Tekst odczytany ze zrzutów (OCR)"):
            st.write(m.ocr_text[:3000])


def graph_html(node_ids: list[str], edges: list, highlight: str | None = None, height: int = 560) -> str:
    from pyvis.network import Network

    palette = ["#e15759", "#4e79a7", "#f28e2b", "#76b7b2", "#59a14f", "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac"]
    net_color = {n.id: palette[k % len(palette)] for k, n in enumerate(nets)}
    g = Network(height=f"{height}px", width="100%", bgcolor="#ffffff", font_color="#222222", directed=False)
    g.set_options(json.dumps({
        "physics": {"enabled": False},
        "edges": {"smooth": False, "font": {"size": 11, "align": "middle"}},
        "nodes": {"font": {"size": 13}},
        "interaction": {"hover": True, "tooltipDelay": 120, "navigationButtons": True},
    }))
    import networkx as nx

    G = nx.Graph()
    G.add_nodes_from(node_ids)
    G.add_weighted_edges_from([(p.a, p.b, p.score) for p in edges if p.a in G and p.b in G])
    # układ po składowych: każda grupa na własnym okręgu, pojedyncze materiały w siatce pod spodem
    import math

    pos, x0 = {}, 0.0
    comps = sorted((sorted(c) for c in nx.connected_components(G)), key=lambda c: (-len(c), c))
    groups, singles = [c for c in comps if len(c) > 1], [c[0] for c in comps if len(c) == 1]
    for comp in groups:
        r = 110 + 45 * len(comp)
        for k, nid in enumerate(comp):
            a = 2 * math.pi * k / len(comp) - math.pi / 2
            pos[nid] = (x0 + r + r * math.cos(a), r * math.sin(a))
        x0 += 2 * r + 160
    cols = max(3, math.ceil(math.sqrt(len(singles) * 2)))
    width = max(x0 - 160, 600)
    for k, nid in enumerate(singles):
        pos[nid] = (k % cols * width / max(1, cols - 1) if cols > 1 else 0, 420 + 170 * (k // cols))
    for nid in node_ids:
        m = by_id.get(nid)
        desc = (m.products or m.titles or m.landing_domains or [f"reklama Meta {x}" for x in m.ad_ids] or m.files or [""])[0] if m else ""
        label = nid if m is None else f"{nid}: {desc[:26]}"
        title = "" if m is None else f"{m.label}\n{'; '.join(m.landing_domains)}\n{camp_of.get(nid, '')} / {net_of.get(nid, '')}"
        color = "#111111" if nid == highlight else net_color.get(net_of.get(nid), "#999999")
        x, y = pos[nid]
        g.add_node(nid, label=label, title=title, color=color, shape="dot", size=28 if nid == highlight else 18,
                   x=float(x), y=float(y), physics=False)
    for p in edges:
        content = p.relation in CONTENT_RELATIONS
        g.add_edge(p.a, p.b, width=1 + 4 * p.score, title=f"{p.score:.2f} · {p.relation}\n" + "\n".join("• " + e.reason for e in p.evidence[:6]),
                   color="#d62728" if content else "#1f77b4", dashes=not content, label=f"{p.score:.2f}")
    html = g.generate_html()
    # dopasuj widok do wszystkich węzłów po narysowaniu (bez fizyki vis-network nie robi tego sam w ramce iframe)
    # (graf w nieaktywnej zakładce ma przy ładowaniu zerową szerokość, więc dopasowujemy też przy każdej zmianie rozmiaru)
    fit = ("<script>function _fit(){try{network.redraw();network.fit({animation:false});}catch(e){}}"
           "setTimeout(_fit,250);window.addEventListener('resize',function(){setTimeout(_fit,60);});"
           "new ResizeObserver(function(){setTimeout(_fit,60);}).observe(document.body);</script></body>")
    return html.replace("</body>", fit)


def evidence_table(p) -> pd.DataFrame:
    return pd.DataFrame([{"kanał": e.channel, "waga": e.weight, "uzasadnienie": e.reason} for e in p.evidence])


# --- zakładki ------------------------------------------------------------------------------------------------------

tab_new, tab_batch, tab_camp, tab_graph, tab_tmpl, tab_mat, tab_method = st.tabs(
    ["🔎 Analiza nowego materiału", "📥 Nowy zbiór (folder / zip)", "📦 Kampanie i sieci", "🕸️ Graf powiązań", "🧬 Schemat perswazji",
     "📄 Materiały", "📐 Metodyka i testy"])

with tab_new:
    st.header("Analiza nowego materiału")
    st.caption("Podaj dowolną kombinację: pliki (zapis strony HTML, log HAR, zrzut ekranu, nagranie, info.json), adres URL, tekst "
               "lub nazwę produktu. Brakujące elementy nie przerywają analizy.")
    mode = st.radio("Źródło", ["Własne wejście", "Przypadek ze zbioru (jako nowy, z pominięciem go w zbiorze)"], horizontal=True)
    new = None
    if mode.startswith("Własne"):
        c1, c2 = st.columns([1, 1])
        with c1:
            url = st.text_area("Adres URL reklamy lub strony (jeden lub kilka)", height=90,
                               placeholder="https://… (analiza bierna: kształt adresu, identyfikatory, dane domeny)")
            text = st.text_area("Tekst reklamy, nazwa produktu lub inna wskazówka", height=90)
        with c2:
            ups = st.file_uploader("Pliki materiału", accept_multiple_files=True,
                                   type=["html", "htm", "mhtml", "har", "png", "jpg", "jpeg", "webp", "gif", "mp4", "mov", "webm", "json", "txt"])
            do_ocr_new = st.checkbox("OCR obrazów", value=True, key="ocr_new")
        if st.button("Analizuj", type="primary"):
            tmp = Path(tempfile.mkdtemp(prefix="fejki_up_"))
            try:
                files = []
                for u in ups or []:
                    p = tmp / Path(u.name).name
                    p.write_bytes(u.getbuffer())
                    files.append(p)
                txt = text
                for p in [f for f in files if f.suffix == ".txt"]:
                    txt += "\n" + p.read_text(encoding="utf-8", errors="replace")
                files = [f for f in files if f.suffix != ".txt"]
                if not (files or url.strip() or txt.strip()):
                    st.error("Podaj przynajmniej jeden plik, adres URL albo tekst.")
                else:
                    with st.spinner("Wyciągam cechy…"):
                        new = material_from_inputs("nowy materiał", files=files, url=url, text=txt, ocr=do_ocr_new)
                        new.files = [f.name for f in files]
                    st.session_state.new = new
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
    else:
        pick = st.selectbox("Przypadek", [m.id for m in idx.materials], format_func=lambda x: f"{x}: {(by_id[x].titles or by_id[x].files or ['—'])[0][:80]}")
        if st.button("Analizuj jako nowy", type="primary"):
            st.session_state.new = by_id[pick].model_copy(update={"id": f"{pick}*", "label": f"przypadek {pick} (jako nowy)"})
    new = st.session_state.get("new")
    if new:
        base = [m for m in idx.materials if m.id != new.id.rstrip("*")]
        bp = [p for p in pairs if p.a != new.id.rstrip("*") and p.b != new.id.rstrip("*")]
        bc, bn = campaigns(base, bp, thr, "kampania"), campaigns(base, bp, thr, "sieć")
        infra = None
        if st.session_state.use_infra and new.landing_domains:
            with st.spinner("Bierne dane infrastruktury dla nowych domen…"):
                store.collect_infra(idx, [new])
                store.save(idx)
            infra = store.infra_records(idx)
        r = match(new, base, bc, bn, thr=thr, maybe=maybe, infra=infra, semantic=bool(st.session_state.get("use_sem")),
                  model=_pair_model())
        st.subheader("Wynik")
        from fejki.demo.explain import verdict
        from fejki.sources.meta_knowledge import MetaKnowledge

        n_us = sum(1 for m_ in idx.materials if m_.source == "urlscan")
        v = verdict(r, new, len(base), n_us)
        {"success": st.success, "warning": st.warning, "info": st.info}[v["level"]](
            f"**{v['decision']}** · najlepszy wynik {r.best_score:.2f} ({confidence_label(r.best_score)})")
        st.markdown(f"**Co to znaczy:** {v['meaning']}")
        c_a, c_b = st.columns(2)
        c_a.markdown("**Dane, które narzędzie miało:**\n" + "\n".join(f"- ✅ {x}" for x in v["have"]) if v["have"] else "**Dane:** brak")
        c_b.markdown("**Czego zabrakło:**\n" + "\n".join(f"- ⬜ {x}" for x in v["lack"]) if v["lack"] else "**Niczego nie zabrakło**")
        for tip in v["advice"]:
            st.info(tip)
        st.caption(f"Porównano z: {v['ref']}.")

        @st.cache_resource
        def _meta():
            return MetaKnowledge(ROOT.parent / "data" / "meta" / "ads.jsonl")

        mk = _meta()
        if mk.n:
            rows_m = mk.lookup(new.landing_domains, new.advertisers, new.ad_ids)
            with st.expander(f"Co wiemy z Meta Ad Library ({mk.n:,} zebranych reklam)".replace(",", " "), expanded=bool(rows_m)):
                if rows_m:
                    st.dataframe(pd.DataFrame(rows_m), use_container_width=True, hide_index=True)
                else:
                    st.write("Domena, reklamodawca ani identyfikator tego materiału nie występują w zebranych reklamach "
                             "(reklamy-oszustwa żyją krótko, a część jest usunięta przez Metę).")
        if r.pairs:
            st.markdown("**Najbliższe materiały** (nawet jeśli wynik jest niski: pokazują, czego brakuje do powiązania)")
            st.dataframe(pd.DataFrame([{"materiał": p.b, "wynik": p.score, "relacja": p.relation,
                                        "przesłanki": " | ".join(e.reason for e in p.evidence[:3]) or "brak wspólnych śladów"}
                                       for p in r.pairs[:5]]), use_container_width=True, hide_index=True)
        show_material(new)
        if r.ranking:
            st.markdown("**Najbliższe kampanie** (wynik = najsilniejsze powiązanie z którymkolwiek materiałem kampanii)")
            names = {c.id: c.name for c in bc}
            st.dataframe(pd.DataFrame([{"kampania": x["campaign"], "nazwa": names.get(x["campaign"], ""), "sieć": x["network"],
                                        "wynik": x["score"], "przez materiał": x["via"], "relacja": x["relation"],
                                        "główne przesłanki": " | ".join(x["evidence"][:3])} for x in r.ranking[:8]]),
                         use_container_width=True, hide_index=True)
            for p in [p for p in r.pairs if p.score >= maybe][:5]:
                with st.expander(f"{p.b}: wynik {p.score:.2f} · {p.relation}"):
                    st.dataframe(evidence_table(p), use_container_width=True, hide_index=True)
            near = [p for p in r.pairs if p.score >= maybe][:12]
            if near:
                nodes = [new.id] + [p.b for p in near]
                st.components.v1.html(graph_html(nodes, near, highlight=new.id, height=420), height=440)
        if not new.id.endswith("*") and st.button("Dodaj ten materiał do zbioru"):
            idx.materials.append(new.model_copy(update={"id": f"n{len(idx.materials) + 1}", "label": "dodany ręcznie"}))
            store.save(idx)
            st.cache_data.clear()
            del st.session_state["new"]
            st.rerun()

with tab_batch:
    from fejki.demo.batch import analyze as batch_analyze
    from fejki.demo.batch import materials_from

    st.header("Nowy zbiór: dopasowanie wielu materiałów naraz")
    st.caption("Wskaż folder z przypadkami (podfolder = materiał), płaski folder z plikami albo wgraj archiwum .zip. Każdy materiał "
               "zostanie dopasowany do zbioru; nieprzypisane, ale podobne do siebie, są grupowane w propozycje NOWYCH kampanii. "
               "Wynik do pobrania jako CSV.")
    src_mode = st.radio("Źródło", ["Ścieżka do folderu lub zip na serwerze", "Wgraj archiwum .zip"], horizontal=True, key="bsrc")
    bpath = None
    if src_mode.startswith("Ścieżka"):
        txt = st.text_input("Ścieżka", "", placeholder="/ścieżka/do/nowego_zbioru lub /ścieżka/do/zbior.zip", key="bpath")
        bpath = Path(txt) if txt.strip() else None
    else:
        up = st.file_uploader("Archiwum zip", type=["zip"], key="bzip")
        if up is not None:
            tmpz = Path(tempfile.mkdtemp(prefix="fejki_bz_")) / "zbior.zip"
            tmpz.write_bytes(up.getbuffer())
            bpath = tmpz
    ocr_b = st.checkbox("OCR zrzutów i klatek", value=True, key="bocr")
    if st.button("Analizuj zbiór", type="primary", key="bgo"):
        if bpath is None or not bpath.exists():
            st.error("Podaj istniejącą ścieżkę albo wgraj plik zip.")
        else:
            bar = st.progress(0.0, "start")
            new_mats = materials_from(bpath, ocr=ocr_b, progress=lambda k, n, d: bar.progress((k + 1) / n, f"materiał {d}"))
            infra_b = store.infra_records(idx) if (st.session_state.use_infra and idx.infra) else None
            df_b, proposals = batch_analyze(idx, new_mats, thr, maybe, infra_b, st.session_state.get("use_sem", False),
                                            st.session_state.get("use_vis", False), _pair_model())
            st.session_state.batch = (df_b, proposals, len(new_mats))
    if st.session_state.get("batch"):
        df_b, proposals, n_new = st.session_state.batch
        st.success(f"Przeanalizowano {n_new} materiałów.")
        st.dataframe(df_b, use_container_width=True, hide_index=True)
        for p_ in proposals:
            st.info(f"Propozycja nowej kampanii {p_['id']}: materiały {', '.join(p_['materiały'])} ({p_['nazwa']})")
        st.download_button("Pobierz wynik (CSV)", df_b.to_csv(index=False).encode("utf-8"), "dopasowania.csv")

with tab_camp:
    st.header("Kampanie i sieci operatorów")
    st.caption("**Kampania** = ten sam przekaz (duplikaty i warianty: tekst, tytuł, produkt, obrazy). **Sieć** = kampanie połączone "
               "wspólną infrastrukturą lub śledzeniem (piksel, schemat adresów, zestaw strony, domena), czyli prawdopodobnie ten sam operator.")
    rows = []
    for n in nets:
        for c in [c for c in camps if set(c.members) <= set(n.members)]:
            rows.append({"sieć": n.id, "kampania": c.id, "nazwa": c.name, "materiały": ", ".join(c.members), "liczba": len(c.members),
                         "domeny": ", ".join(sorted({d for m in c.members for d in by_id[m].landing_domains})),
                         "spójność": c.strength})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    for n in [n for n in nets if len(n.members) > 1]:
        with st.expander(f"Sieć {n.id}: {n.name} · {len(n.members)} materiałów · sygnały: "
                         + ", ".join(f"{k} ({v})" for k, v in list(n.signals.items())[:5])):
            inner = [p for p in pairs if p.a in n.members and p.b in n.members and p.score >= thr]
            st.dataframe(pd.DataFrame([{"para": f"{p.a} ↔ {p.b}", "wynik": p.score, "relacja": p.relation,
                                        "przesłanki": " | ".join(e.reason for e in p.evidence[:4])} for p in inner]),
                         use_container_width=True, hide_index=True)
    st.download_button("Eksport kampanii (CSV)", pd.DataFrame(rows).to_csv(index=False).encode("utf-8"), "kampanie.csv")

    st.divider()
    st.subheader("Karta kampanii dla analityka")
    st.caption("Okno obserwacji, domeny kampanii, lista domen do weryfikacji z uzasadnieniem i priorytetem, przesłanki powiązań. "
               "Okno to czas zebrania materiałów (logi HAR, daty w nazwach zrzutów), nie czas emisji reklam.")
    cards = build_cards(idx.materials, pairs, camps, nets, thr, store.infra_records(idx) if idx.infra else None)
    card_by_id = {c.id: c for c in cards}
    sel_card = st.selectbox("Kampania", [c.id for c in cards],
                            format_func=lambda k: f"{k}: {card_by_id[k].name} [{', '.join(card_by_id[k].members)}]")
    card = card_by_id[sel_card]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Materiały", len(card.members))
    c2.metric("Okno obserwacji", (f"{card.window_days} dni" if (card.window_days or 0) >= 1
                                  else f"{round((card.window_days or 0) * 24, 1)} h") if card.window_start else "brak dat")
    c3.metric("Domeny do weryfikacji", len(card.domains_to_verify))
    c4.metric("Sieć operatora", card.network or "—")
    if card.domains_to_verify:
        st.dataframe(pd.DataFrame([{"domena": d.domain, "priorytet": d.priority, "dlaczego": "; ".join(d.roles + d.notes),
                                    "materiały": ", ".join(d.materials), "rejestracja": d.registered or "—"}
                                   for d in card.domains_to_verify]), use_container_width=True, hide_index=True)
    with st.expander("Pełna karta", expanded=False):
        st.markdown(card_markdown(card))
    d1, d2, d3 = st.columns(3)
    d1.download_button("Ta karta (Markdown)", card_markdown(card).encode("utf-8"), f"karta_{card.id}.md")
    d2.download_button("Wszystkie karty (Markdown)", all_markdown(cards).encode("utf-8"), "karty_kampanii.md")
    d3.download_button("Domeny do weryfikacji (CSV)", domains_csv(cards).encode("utf-8"), "domeny_do_weryfikacji.csv")
    if not idx.infra:
        st.caption("Daty rejestracji domen pojawią się po „Zbierz dane infrastruktury (bierne)” w panelu bocznym.")

with tab_graph:
    from fejki.demo.export import build_graph as exp_graph
    from fejki.demo.export import csvs as exp_csvs
    from fejki.demo.export import cypher as exp_cypher
    from fejki.demo.export import graphml as exp_graphml

    st.header("Graf powiązań")
    st.caption("Węzeł = materiał (kolor = sieć). Czerwona linia ciągła = ten sam przekaz; niebieska przerywana = wspólna infrastruktura. "
               "Najedź na krawędź, żeby zobaczyć przesłanki.")
    shown = [p for p in pairs if p.score >= min(thr, maybe)]
    st.components.v1.html(graph_html([m.id for m in idx.materials], shown), height=600)
    g_exp = exp_graph(idx.materials, pairs, camps, nets, min(thr, maybe))
    e1, e2, e3 = st.columns(3)
    e1.download_button("Graf (GraphML)", exp_graphml(g_exp).encode("utf-8"), "graf.graphml")
    e2.download_button("Graf dla Neo4j (Cypher)", exp_cypher(g_exp).encode("utf-8"), "graf.cypher")
    e3.download_button("Węzły i krawędzie (CSV)", exp_csvs(g_exp)["edges.csv"].encode("utf-8"), "krawedzie.csv")
    st.dataframe(pd.DataFrame([{"a": p.a, "b": p.b, "wynik": p.score, "pewność": confidence_label(p.score), "relacja": p.relation,
                                "przesłanki": " | ".join(e.reason for e in p.evidence[:5])} for p in shown]),
                 use_container_width=True, hide_index=True)

with tab_mat:
    st.header("Materiały w zbiorze")
    st.dataframe(pd.DataFrame([{"id": m.id, "kampania": camp_of.get(m.id), "sieć": net_of.get(m.id),
                                "tytuł": (m.titles or ["—"])[0][:70], "domeny": ", ".join(m.landing_domains),
                                "osoby": ", ".join(m.persons[:3]), "produkt": ", ".join(m.products), "braki": "; ".join(m.missing)}
                               for m in idx.materials]), use_container_width=True, hide_index=True)
    sel = st.selectbox("Szczegóły materiału", [m.id for m in idx.materials])
    show_material(by_id[sel])
    st.caption("Pliki: " + ", ".join(by_id[sel].files[:20]) + (" …" if len(by_id[sel].files) > 20 else ""))

with tab_tmpl:
    import plotly.express as px

    from fejki.demo.persuasion import MOVES, moves
    from fejki.demo.template import TemplateSpace, model_available, project_2d, separation

    st.header("Schemat perswazji ponad tematami")
    st.caption("Hipoteza projektu: oszuści zmieniają temat (osoba, produkt), ale powtarzają ten sam schemat perswazji. "
               "Sprawdzamy, czy po usunięciu tematu z wektorów tekstu (LEACE) materiały tej samej sieci operatora są bliżej "
               "siebie niż materiały różnych sieci. Sieci pochodzą z infrastruktury i śledzenia; ten widok używa wyłącznie tekstu, "
               "więc ocena nie jest cyrkularna. Wynik jest analizą, nie wpływa na grupowanie.")
    st.subheader("DNA perswazji (ruchy na 1000 słów)")
    dna_df = pd.DataFrame({m.id: moves(" ".join(m.titles) + " " + m.text) for m in idx.materials}).T
    dna_df.columns = [MOVES[c][0] for c in dna_df.columns]
    dna_df.index = [f"{i} ({net_of.get(i, '—')})" for i in dna_df.index]
    st.plotly_chart(px.imshow(dna_df, color_continuous_scale="Reds", aspect="auto", labels={"color": "na 1000 słów"}),
                    use_container_width=True)
    bge_ok = model_available()
    enc = st.radio("Enkoder tekstu", ["lsa", "bge-m3"], horizontal=True, index=0,
                   format_func=lambda e: "TF-IDF + SVD (offline)" if e == "lsa" else "bge-m3 (semantyczny)" + ("" if bge_ok else ": model niepobrany"))
    if enc == "bge-m3" and not bge_ok:
        st.warning("Model BAAI/bge-m3 (~2,3 GB) nie jest pobrany. Pobranie wymaga decyzji zespołu; do tego czasu używamy LSA.")
        enc = "lsa"

    @st.cache_resource(show_spinner="Liczę wektory fragmentów i LEACE…")
    def _space(materials_key: str, encoder: str):
        return TemplateSpace([Material.model_validate(m) for m in json.loads(materials_key)], encoder=encoder)

    space = _space(json.dumps([m.model_dump() for m in idx.materials]), enc)
    if not getattr(space, "leace_available", True):
        st.warning("Brak bibliotek części badawczej (torch, concept-erasure): wariant „LEACE” jest równy surowemu. "
                   "Zainstaluj: pip install -e \".[research]\".")
    groups = {mid: n.id for n in nets for mid in n.members if len(n.members) > 1}
    main_topic = {m.id: next(iter(m.topics), "inne") for m in idx.materials}
    st.subheader("Czy po usunięciu tematu sieci się rozdzielają?")
    st.dataframe(pd.DataFrame(separation(space, groups, main_topic)), use_container_width=True, hide_index=True)
    st.caption(f"Fragmentów: {len(space.chunk_ids)}, klas tematu: {len(space.topic_classes)}, usunięty rząd: {space.rank}. "
               "Kontrola losowa usuwa losową podprzestrzeń tego samego rzędu. Duplikaty pominięte. Przy 10 przypadkach to "
               "ilustracja, nie dowód: do dowodu potrzebny większy zbiór (urlscan z kluczem) i podział po sieciach.")
    cols = st.columns(2)
    for col, variant in zip(cols, ["surowe", "LEACE (bez tematu)"]):
        pts = project_2d(space, variant)
        df2 = pd.DataFrame([{"x": x, "y": y, "materiał": k, "sieć": net_of.get(k, "—") if k in groups else "osobno",
                             "temat": main_topic.get(k, "inne")} for k, (x, y) in pts.items()])
        fig = px.scatter(df2, x="x", y="y", color="sieć", symbol="temat", text="materiał", title=variant, height=420)
        fig.update_traces(textposition="top center", marker={"size": 13})
        fig.update_layout(xaxis_title="", yaxis_title="", legend={"orientation": "h", "y": -0.2})
        col.plotly_chart(fig, use_container_width=True)

with tab_method:
    st.header("Metodyka")
    st.markdown("""
**1. Pozyskanie cech** (bez odwiedzania stron oszustów):
- *tekst*: widoczny tekst zapisanych stron, OCR zrzutów i klatek wideo; słowa kluczowe, tematyka (słownik), osoby publiczne
  (mała baza `config/osoby.txt`, dopasowanie z polską odmianą), produkt (krótki tytuł strony), reklamodawca (nazwa przy „Sponsorowane”);
- *adresy i śledzenie*: domeny docelowe (adres zapisu strony, nazwa HAR), schemat parametrów (np. losowe `utm_*` o stałej
  długości + `utm_visit` = ten sam system kierowania ruchu), wzorce ścieżek i katalogi zestawów stron, identyfikatory reklam Meta
  (`ad_id`), piksele Meta, identyfikatory Google Ads/GTM, nietypowe usługi zewnętrzne, przekierowania z logu HAR;
- *obraz*: pHash zrzutów, kreacji, klatek wideo i obrazów użytych na stronach;
- *struktura*: zestaw klas HTML (szablon strony), wykrywanie cloakingu (ta sama domena, różne strony);
- *infrastruktura (opcjonalnie)*: DNS, ASN, RDAP, dziennik certyfikatów (crt.sh).

**2. Podobieństwo**: każdy kanał zwraca dowody z wagą i opisem. Wagi łączymy metodą noisy-OR w kanale, a potem między kanałami.
Pospolite cechy (osoba obecna w wielu materiałach, popularna usługa) dostają niższą wagę. Każda krawędź ma listę przesłanek.

**3. Grupowanie**: *kampania* = składowe spójne krawędzi „duplikat / wariant tego samego przekazu”; *sieć* = składowe spójne
wszystkich krawędzi powyżej progu (wspólny operator).

**4. Nowy materiał**: porównanie ze zbiorem; przypisanie do kampanii (ten sam przekaz), wskazanie znanej sieci (nowy przekaz, ta sama
infrastruktura), „do weryfikacji” albo nowy wzorzec.
""")
    st.markdown("**Wagi dowodów**")
    st.dataframe(pd.DataFrame([{"dowód": k, "kanał": CHANNELS.get(k, k), "waga": v} for k, v in W.items()]), hide_index=True)
    st.markdown("**Testy zachowania** (bez etykiet organizatora: „oczekiwane” = wynik na pełnym zbiorze)")
    if st.button("Uruchom test pomiń-jeden"):
        from fejki.demo.evaluate import leave_one_out

        with st.spinner("Liczę…"):
            df = leave_one_out(idx.materials, thr)
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.write(f"Spójność kampanii: {df['kampania OK'].mean():.0%} · spójność sieci: {df['sieć OK'].mean():.0%}")
    st.markdown("""
**Ograniczenia**: brak etykiet kampanii od organizatora (testy mierzą stabilność, nie trafność względem ich podziału); OCR bez
polskiego pakietu językowego gubi znaki diakrytyczne (w Dockerze instalujemy `tesseract-ocr-pol`); kanał infrastruktury wymaga sieci;
nie rozpoznajemy twarzy (osoby rozpoznajemy po nazwiskach w tekście); wagi ustawione ręcznie na podstawie znaczenia sygnału.
""")
