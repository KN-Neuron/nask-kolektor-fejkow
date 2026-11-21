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
from embsim.api import DEFAULT_CONFIG, Gallery

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
        st.session_state.gallery = Gallery.load(GALLERY_FILE, embed_fn=fn) if GALLERY_FILE.exists() else Gallery(embed_fn=fn)
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
    t_camp = st.slider("Próg: znana kampania", 0.30, 0.99, float(g.cfg.thresholds.get("campaign") or 0.95), 0.01,
                       help="Domyślny próg 0,95 pochodzi z kalibracji na syntetyce. Na reklamach Meta w teście po czasie optimum wyszło "
                            "ok. 0,5. Niższy próg łączy chętniej (więcej trafień, więcej błędnych połączeń).")
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
st.subheader("1. Wejście")
with st.form("wejscie"):
    files = st.file_uploader("Pliki: zrzut ekranu, HTML, HAR, reklama Meta (JSON/JSONL), info.json", accept_multiple_files=True,
                             type=["png", "jpg", "jpeg", "webp", "html", "htm", "har", "json", "jsonl"])
    text = st.text_area("Tekst reklamy albo nazwa produktu", height=90)
    url = st.text_input("Adres URL (użyjemy tylko domeny)")
    ocr = st.checkbox("Odczytaj tekst ze zrzutu (OCR)", value=True)
    go = st.form_submit_button("Analizuj", type="primary")

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
        best = d.matches[0]
        c1, c2, c3 = st.columns(3)
        c1.metric("wynik kampanii", f"{d.campaign_score:.2f}", help=f"próg {d.thresholds.get('campaign')}")
        c2.metric("wynik operatora", f"{d.operator_score:.2f}", help=f"próg {d.thresholds.get('operator')}")
        c3.metric("pewność dowodu", A.confidence_label(best.evidence))
        st.markdown("**Trzy najsilniejsze powody (najbliższy materiał):**")
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
        st.plotly_chart(A.network_figure(case, d), use_container_width=True)
    c1, c2 = st.columns(2)
    c1.download_button("Pobierz kartę dla analityka (Markdown)", A.card_markdown(case, d), file_name=f"karta_{case.id}.md")
    if c2.button("Dodaj materiał do galerii"):
        g.add(case)
        st.session_state.flash = f"Dodano {case.id}. Galeria ma teraz {len(g)} materiałów."
        st.rerun()
