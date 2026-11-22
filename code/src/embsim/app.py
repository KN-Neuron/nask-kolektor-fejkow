"""Kolekcjoner Fejków: demonstrator, jedna ścieżka. Uruchomienie: `make demo` albo `streamlit run src/embsim/app.py`.

Wejście (zrzut, HTML, HAR, reklama Meta w JSON/JSONL, tekst, adres URL; adresów nie odwiedzamy) -> cechy -> dopasowanie do galerii z
przesłankami (wzór: docs/14, bez uczenia) -> sieć kampanii i operatorów -> karta dla analityka. Działa offline po pobraniu modelu
(w obrazie Dockera jest już w środku); `EMBSIM_EMBED=hash` włącza zamiennik bez modelu.
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st

from embsim import analyze as A
from embsim import graph_view
from embsim import jury as J
from embsim.api import DEFAULT_CONFIG, Gallery, demo_thresholds

ROOT = Path(__file__).resolve().parents[3]
GALLERY_FILE = Path(os.environ.get("EMBSIM_GALLERY", ROOT / "code" / "artifacts" / "gallery_demo.jsonl"))
DEFAULT_FOLDERS = os.environ.get("EMBSIM_DATA", str(ROOT / "data" / "dane" / "do_udostępnienia"))
DEFAULT_META = os.environ.get("EMBSIM_META", str(ROOT / "data" / "meta" / "sample_s1.jsonl"))

st.set_page_config(page_title="Kolekcjoner Fejków", page_icon="🕵️", layout="wide")


def embed_fn():
    return A.hash_embed if os.environ.get("EMBSIM_EMBED") == "hash" else None


def gallery() -> Gallery:
    if "gallery" not in st.session_state:
        fn = embed_fn()
        thr = demo_thresholds()
        st.session_state.gallery = (Gallery.load(GALLERY_FILE, embed_fn=fn, thresholds=thr) if GALLERY_FILE.exists()
                                    else Gallery(embed_fn=fn, thresholds=thr))
    return st.session_state.gallery


# --- pasek boczny: galeria --------------------------------------------------------------------------------------------

g = gallery()
with st.sidebar:
    st.header("Galeria znanych materiałów")
    if "flash" in st.session_state:                      # komunikat po akcji (strona odświeżana, żeby liczniki były aktualne)
        st.success(st.session_state.pop("flash"))
    s = A.gallery_summary(g)
    c1, c2, c3 = st.columns(3)
    c1.metric("materiały", s["materiałów"]); c2.metric("kampanie", s["kampanii"]); c3.metric("operatorzy", s["operatorów"])
    st.caption(f"Konfiguracja: `{DEFAULT_CONFIG}`.")
    t_camp = st.slider("Próg: znana kampania", 0.30, 0.99, float(g.cfg.thresholds.get("campaign") or 0.95), 0.005, format="%.3f",
                       help="Domyślny próg 0,725 jest skalibrowany na stronach (HTML, HAR, zrzuty) z NASK i syntetyki, zostaw-jeden "
                            "(config/embsim/demo_calibration.json). Na reklamach Meta optimum wyszło ok. 0,5. Niższy próg łączy "
                            "chętniej (więcej trafień, więcej błędnych połączeń).")
    g.cfg.thresholds["campaign"] = t_camp
    with st.expander("Zbuduj galerię", expanded=(len(g) == 0)):
        folders = st.text_input("Folder z przypadkami (podfoldery = materiały)", DEFAULT_FOLDERS)
        use_ocr = st.checkbox("OCR dla przypadków bez tekstu (sam zrzut)", value=False)
        if st.button("Dodaj przypadki z folderów"):
            p = Path(folders)
            if p.is_dir():
                bar = st.progress(0.0)
                n = A.build_from_folders(g, p, ocr=use_ocr, progress=lambda f, t: bar.progress(f, text=t))
                st.session_state.flash = f"Wczytano {n} folderów."
                st.rerun()
            else:
                st.error("Folder nie istnieje.")
        meta_path = st.text_input("Reklamy Meta (JSONL)", DEFAULT_META)
        limit = st.slider("ile reklam", 200, 5000, 1500, 100)
        if st.button("Dodaj reklamy z pliku"):
            p = Path(meta_path)
            if p.is_file():
                with st.spinner("Liczę wektory i dodaję…"):
                    n = A.build_from_meta(g, p, limit)
                st.session_state.flash = f"Dodano {n} reklam."
                st.rerun()
            else:
                st.error("Plik nie istnieje.")
        c1, c2 = st.columns(2)
        if c1.button("Zapisz galerię"):
            GALLERY_FILE.parent.mkdir(parents=True, exist_ok=True)
            g.save(GALLERY_FILE)
            st.success(f"Zapisano: {GALLERY_FILE.name}")
        if c2.button("Wyczyść"):
            del st.session_state["gallery"]
            st.rerun()

# --- krok 1: wejście ---------------------------------------------------------------------------------------------------

st.title("Kolekcjoner Fejków")
st.caption("Jedna metoda: podobieństwo to jedno wyrażenie z wagami ustalonymi z góry, bez uczenia (docs/14_WZOR_PODOBIENSTWA.md). "
           "Strony oszustów nie są odwiedzane.")
tab_a, tab_k, tab_w = st.tabs(["🔎 Analiza nowego materiału", "🧩 Klastry", "📐 Wzór i wyniki"])

with tab_a:
    st.subheader("1. Wejście")
    with st.form("wejscie"):
        files = st.file_uploader("Pliki: zrzut ekranu, HTML, HAR, reklama Meta (JSON/JSONL), info.json", accept_multiple_files=True,
                                 type=["png", "jpg", "jpeg", "webp", "html", "htm", "har", "json", "jsonl"])
        text = st.text_area("Tekst reklamy albo nazwa produktu", height=90)
        url = st.text_input("Adres URL (użyjemy tylko domeny)")
        ocr = st.checkbox("Odczytaj tekst ze zrzutu (OCR)", value=True)
        go = st.form_submit_button("Analizuj", type="primary")

    with st.expander("Wiele materiałów naraz (zbiór testowy: ZIP albo folder, podfolder = jeden materiał)"):
        st.caption("Każdy materiał dostaje decyzję względem galerii i dopiero potem do niej trafia, więc kilka nowych materiałów jednej "
                   "kampanii łączy się też między sobą (dostają wspólną nową kampanię K…). Pliki jak w folderach NASK: HTML, HAR, zrzuty, "
                   "zasoby strony `*_files`.")
        bz = st.file_uploader("Archiwum ZIP", type=["zip"], key="batch_zip")
        bdir = st.text_input("albo folder na dysku", "", key="batch_dir")
        c1, c2 = st.columns(2)
        bocr = c1.checkbox("OCR dla materiałów bez tekstu (sam zrzut)", value=True, key="batch_ocr")
        bkeep = c2.checkbox("Zostaw ocenione materiały w galerii", value=False, key="batch_keep")
        if st.button("Oceń wszystkie", key="batch_go"):
            import tempfile

            with tempfile.TemporaryDirectory() as td:
                try:
                    root = A.extract_zip(bz.getvalue(), Path(td)) if bz else Path(bdir) if bdir.strip() else None
                except (ValueError, OSError) as e:
                    root = None
                    st.error(f"Nie da się rozpakować archiwum: {e}")
                if root is None or not root.is_dir():
                    st.warning("Wgraj ZIP albo podaj istniejący folder.")
                else:
                    bar = st.progress(0.0)
                    rows, _ = A.assess_folder(g, root, keep=bkeep, ocr=bocr, progress=lambda f, t: bar.progress(f, text=t))
                    st.session_state.batch = rows
        if st.session_state.get("batch"):
            bdf = pd.DataFrame(st.session_state.batch)
            st.dataframe(bdf, use_container_width=True, hide_index=True)
            st.caption(" · ".join(f"{k}: {v}" for k, v in bdf["werdykt"].value_counts().items()))
            st.download_button("Pobierz wyniki (CSV)", bdf.to_csv(index=False).encode("utf-8"), "wyniki.csv", key="batch_csv")

    if go:
        if not (files or text.strip() or url.strip()):
            st.warning("Podaj plik, tekst albo adres.")
        else:
            with st.spinner("Wyciągam cechy i porównuję z galerią…"):
                case, info = A.case_from_inputs([(f.name, f.getvalue()) for f in (files or [])], text, url, ocr)
                st.session_state.result = (case, info, g.query(case, 5))

    res = st.session_state.get("result")
    if res:
        case, info, d = res
        # --- krok 2: cechy ------------------------------------------------------------------------------------------------
        st.subheader("2. Cechy materiału")
        for w in info.get("ostrzeżenia", []):
            st.warning(w)
        for k in ("źródło", "url"):
            if k in info:
                st.caption(info[k])
        cols = st.columns(5)
        cols[0].metric("znaków tekstu", len(case.text))
        for col, ch in zip(cols[1:], ("host", "kit", "scheme", "pixel")):
            col.metric({"host": "domeny", "kit": "zestawy zasobów", "scheme": "schematy adresu", "pixel": "piksele"}[ch], len(case.sets.get(ch, ())))
        if info.get("ocr_język"):
            st.caption(f"OCR: język {info['ocr_język']}, odczytano {info['ocr_znaków']} znaków.")
        with st.expander("Tekst i ślady"):
            st.write(case.text[:1200] or "(brak tekstu)")
            st.json({k: sorted(v)[:8] for k, v in case.sets.items()})

        # --- krok 3: dopasowanie z przesłankami ----------------------------------------------------------------------------
        st.subheader("3. Dopasowanie z przesłankami")
        if len(g) == 0:
            st.info("Galeria jest pusta: zbuduj ją w pasku bocznym albo dodaj ten materiał jako pierwszy.")
        kind, label = A.verdict_style(d)
        getattr(st, kind)(f"**{label}**")
        st.write(d.explain())
        if d.matches:
            best = d.key_match()
            c1, c2, c3 = st.columns(3)
            c1.metric("wynik kampanii", f"{d.campaign_score:.2f}", help=f"próg {d.thresholds.get('campaign')}")
            c2.metric("wynik operatora", f"{d.operator_score:.2f}", help=f"próg {d.thresholds.get('operator')}")
            c3.metric("pewność dowodu", A.confidence_label(best.evidence))
            st.markdown(f"**Trzy najsilniejsze powody (materiał {best.id}):**")
            for r in A.top_reasons(best):
                st.markdown(f"- {r}")
            st.dataframe(pd.DataFrame([{"materiał": m.id, "kampania": m.group, "operator": m.operator, "wynik kampanii": m.campaign_score,
                                        "wynik operatora": m.operator_score, "powody": "; ".join(A.top_reasons(m))} for m in d.matches]),
                         use_container_width=True, hide_index=True)
            for m in d.matches[:3]:
                with st.expander(f"Szczegóły: {m.id}"):
                    if m.channels:
                        st.bar_chart(pd.Series(m.channels, name="wynik kanału"))
                    st.json({"wspólne ślady": m.shared, "dokładne zgodności poza wynikiem": m.extra_shared})

        # --- krok 4: sieć i karta ------------------------------------------------------------------------------------------
        st.subheader("4. Sieć kampanii i operatorów")
        if d.matches:
            st.caption("Czerwona strzałka: znana kampania · pomarańczowa: ten sam operator · szara przerywana: za słabe, żeby łączyć. "
                       "Na strzałce wynik i najmocniejszy powód.")
            st.graphviz_chart(A.network_dot(case, d), use_container_width=False)
        c1, c2 = st.columns(2)
        c1.download_button("Pobierz kartę dla analityka (Markdown)", A.card_markdown(case, d), file_name=f"karta_{case.id}.md")
        if c2.button("Dodaj materiał do galerii"):
            g.add(case)
            st.session_state.flash = f"Dodano {case.id}. Galeria ma teraz {len(g)} materiałów."
            st.rerun()


# --- zakładka: klastry ---------------------------------------------------------------------------------------------------

with tab_k:
    mode = st.radio("Źródło klastrów", ["Galeria (offline)", "Graf Neo4j (twórcy z Mety, sieci NASK)"], horizontal=True, key="cluster_mode")
    if mode.startswith("Graf"):
        graph_view.render()
    else:
        st.subheader("Klastry w galerii")
        idx = A.cluster_index(g)
        if not idx:
            st.info("Galeria jest pusta: zbuduj ją w pasku bocznym albo dodaj materiały w zakładce Analiza.")
        else:
            st.caption("Operator → kampanie → materiały. Rysunek pokazuje tylko ślady, które klaster skleja (wspólne dla co najmniej dwóch "
                       "materiałów); trackery i inne pospolite ślady są pominięte, bo niczego nie dowodzą. Działa bez bazy.")
            size = lambda o: sum(len(v) for v in idx[o].values())
            ops = sorted(idx, key=lambda o: -size(o))
            st.dataframe(pd.DataFrame([{"operator": o, "kampanie": len(idx[o]), "materiały": size(o)} for o in ops]),
                         use_container_width=True, hide_index=True, height=200)
            op = st.selectbox("Karta operatora", ops, format_func=lambda o: f"{o} · {len(idx[o])} kampanii · {size(o)} materiałów")
            camps = idx[op]
            all_idx = [i for v in camps.values() for i in v]
            traces = A.shared_traces(g, all_idx)
            st.markdown("**Co z tego wynika**")
            for line in A.cluster_summary(g, camps, traces) or ["Brak wspólnych rzadkich śladów: grupowanie wynika z podobieństwa treści."]:
                st.markdown(f"- {line}")
            st.caption("Czerwona ramka: ślady jednej kampanii (w środku jej ramki) · niebieska: ślady łączące kampanie w operatora. "
                       "Jedna ramka = jeden zbiór materiałów i wszystko, co go skleja.")
            st.graphviz_chart(A.cluster_dot(g, camps, f"operator {op}", traces), use_container_width=False)
            st.markdown("**Co skleja ten klaster**")
            if traces:
                st.dataframe(pd.DataFrame([{**t, "materiały": ", ".join(t["materiały"][:8]) + (f" (+{len(t['materiały']) - 8})" if len(t["materiały"]) > 8 else "")}
                                           for t in traces[:30]]), use_container_width=True, hide_index=True)
            else:
                st.write("Brak wspólnych śladów poza pospolitymi; grupowanie wynika z podobieństwa treści.")
            mats = [{"materiał": g.items[i]["case"].id, "kampania": g.items[i]["group"], "operator": g.items[i]["operator"],
                     "tekst": (g.items[i]["case"].text.strip().splitlines() or [""])[0][:80]} for i in all_idx]
            with st.expander(f"Materiały ({len(mats)})"):
                st.dataframe(pd.DataFrame(mats), use_container_width=True, hide_index=True)
            st.download_button("Pobierz kartę klastra (Markdown)", A.cluster_markdown(f"operator {op}", mats, traces), file_name=f"klaster_{op}.md")


# --- zakładka: wzór i wyniki ----------------------------------------------------------------------------------------------

CHANNELS = [
    ("text", "embedding tekstu (MiniLM, wielojęzyczny)", "kosinus, odjęta typowa wartość w galerii"),
    ("text_lex", "TF-IDF n-gramów znaków (3–5), bez modelu", "kosinus, odjęta typowa wartość w galerii"),
    ("kit", "katalogi zasobów strony (z HAR)", "wspólne ślady ważone rzadkością"),
    ("scheme", "zestaw nazw parametrów adresu (z HAR)", "wspólne ślady ważone rzadkością"),
    ("host", "domeny rejestrowalne z ruchu, bez Google/Meta/CDN", "wspólne ślady ważone rzadkością"),
    ("pixel", "identyfikatory pikseli i tagów (z HTML)", "wspólne ślady ważone rzadkością"),
    ("img", "identyczne obrazy strony (SHA-256 z HAR i `*_files`), bez modelu", "wspólne ślady ważone rzadkością"),
]

with tab_w:
    st.subheader("Jak liczymy podobieństwo")
    st.markdown(
        "Podobieństwo dwóch materiałów to **jedno wyrażenie z wagami ustalonymi z góry**. Nie ma tu wytrenowanego modelu: każdy kanał daje liczbę "
        "od 0 do 1, wszystkie ważą tyle samo, a jedyne liczby dobrane na danych z etykietami to **dwa progi decyzyjne**.")
    st.code(
        "S̄(a,b) = Σ w_c · s_c(a,b) / Σ w_c          średnia po kanałach, w których coś da się porównać (w_c = 1)\n"
        "S(a,b)  = max(0, 1 − (1 − S̄) / λ)         λ = min(1, e / e_ref): im mniej danych, tym wyższy S̄ jest potrzebny\n"
        "s_ślad  = 1 − exp(− Σ idf(x)),  idf(x) = ln((N+1) / (df(x)+0,5))   x = wspólny ślad: rzadki waży dużo, pospolity prawie nic\n"
        "decyzja: S ≥ t_kampanii → znana kampania;  inaczej S_operatora ≥ t_operatora → ten sam operator;  inaczej → nowy wzorzec",
        language="text")
    st.dataframe(pd.DataFrame(CHANNELS, columns=["kanał", "co porównuje", "jak"]), use_container_width=True, hide_index=True)
    thr = g.cfg.thresholds
    st.caption(f"Progi: kampania {thr.get('campaign')} (skalibrowany na stronach z NASK i syntetyki, `config/embsim/demo_calibration.json`), "
               f"operator {thr.get('operator')}. Pełny opis: `docs/14_WZOR_PODOBIENSTWA.md`.")

    res_w = st.session_state.get("result")
    if res_w and res_w[2].matches:
        _, _, dw = res_w
        mw = dw.key_match()
        st.markdown(f"**Na żywo: ostatnia analiza, najbliższy materiał {mw.id}**")
        if mw.channels:
            vals = list(mw.channels.values())
            st.dataframe(pd.DataFrame([{"kanał": k, "wynik kanału s_c": v} for k, v in mw.channels.items()]),
                         use_container_width=True, hide_index=True)
            st.write(f"S̄ = średnia z {len(vals)} kanałów = **{sum(vals) / len(vals):.3f}**; po korekcie o dostępność dowodu "
                     f"**S = {mw.campaign_score:.3f}** (próg {thr.get('campaign')}); wynik operatora **{mw.operator_score:.3f}** "
                     f"(próg {thr.get('operator')}). Pominięte kanały nie miały wspólnego śladu albo danych w obu materiałach.")
    else:
        st.caption("Przeanalizuj materiał w pierwszej zakładce, a tu pojawi się rozbicie jego wyniku na kanały.")

    st.subheader("Walidacja na zbiorze, którego system nie widział")
    st.markdown(
        "Mierzone: skuteczność wskazywania podobnych materiałów i wariantów, poprawność przypisania do istniejących grup, "
        "**niełączenie obcych**, odporność na duplikaty i braki danych, interpretowalność i pełny przebieg od wczytania do wyniku. "
        "A: każdy przypadek NASK ukryty po kolei. B: ten sam materiał w innych formatach (sam HTML, sam HAR, sam zrzut, duplikat). "
        "C: syntetyka z ukrytymi wariantami, nową kampanią znanego operatora i negatywami.")
    stored = J.load_stored()
    can_run = Path(DEFAULT_FOLDERS).is_dir()
    if can_run and st.button("Uruchom test na danych z tego komputera", key="jury_run"):
        with st.spinner("Buduję galerie i pytam o każdy ukryty materiał (około pół minuty)…"):
            rr = J.run_all(g.cfg.thresholds.get("campaign"), Path(DEFAULT_FOLDERS))
        stored = J.to_record(rr)
        st.session_state.jury_live = stored
    stored = st.session_state.get("jury_live") or stored
    if not stored:
        st.info("Brak zapisanych wyników testu. Uruchom `PYTHONPATH=src python scripts/test_jak_jury_embsim.py` w katalogu code/.")
    else:
        st.caption(f"Wyniki z {stored['data']}, próg kampanii {stored['próg']}. A: {stored['wyniki']['A']}; B: {stored['wyniki']['B']}; "
                   f"C: {stored['wyniki']['C']}.")
        st.dataframe(pd.DataFrame(stored["podsumowanie"]), use_container_width=True, hide_index=True)
        for k, title in (("A", "A. NASK, ukryty przypadek"), ("B", "B. Format, braki, duplikat"), ("C", "C. Syntetyka jako ukryty zbiór")):
            if stored.get(k):
                with st.expander(f"{title}: {stored['wyniki'][k]}"):
                    st.dataframe(pd.DataFrame(stored[k]), use_container_width=True, hide_index=True)
