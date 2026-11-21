"""Streamlit demo. Reads precomputed artifacts (run `fejki eval all` first). Demo mode = offline fixtures."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[3]
ART = ROOT / "artifacts"

st.set_page_config(page_title="Kolekcjoner Fejków", layout="wide")
st.markdown("<style>html, body, [class*='css'] {font-size: 18px;}</style>", unsafe_allow_html=True)
st.sidebar.title("Kolekcjoner Fejków")
demo = st.sidebar.toggle("Tryb demo (fixture'y offline)", value=True)
page = st.sidebar.radio("Widok", ["Przegląd", "Kampanie", "Karta kampanii", "Eksperymenty", "Replay", "Komentarze"])
if demo:
    st.sidebar.caption("Dane syntetyczne: fikcyjne osoby, marki i domeny .example. Cel badawczy.")


@st.cache_data
def csv(name: str, sub: str = "tables") -> pd.DataFrame | None:
    p = ART / sub / name
    return pd.read_csv(p) if p.exists() else None


def need(df, what: str):
    if df is None:
        st.warning(f"Brak {what}. Uruchom: `fejki eval all --seed 1`")
        st.stop()
    return df


if page == "Przegląd":
    st.header("Dzienna liczba nowych reklam per region i bursty")
    b = need(csv("bursts.csv", "replay"), "bursts.csv")
    reg = st.multiselect("Regiony", sorted(b.region.unique()), default=sorted(b.region.unique())[:4])
    d = b[b.region.isin(reg)]
    fig = px.line(d, x="day", y="count", color=d.region.astype(str))
    bb = d[d.burst]
    fig.add_scatter(x=bb.day, y=bb["count"], mode="markers", marker=dict(size=11, color="red", symbol="x"), name="burst")
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Burst: ogon Poissona względem 14-dniowej średniej kroczącej (p < 1e-3). Warunek konieczny, o kampanii decyduje score koordynacji.")

elif page == "Kampanie":
    st.header("Kandydaci na kampanie")
    c = need(csv("campaigns.csv"), "campaigns.csv")
    mn = st.slider("Minimalny score", 0.0, 1.0, 0.0)
    st.dataframe(c[c.score >= mn], use_container_width=True)

elif page == "Karta kampanii":
    cards = sorted((ART / "cards").glob("campaign-*.md"))
    if not cards:
        need(None, "kart kampanii")
    sel = st.selectbox("Kampania", [p.stem for p in cards])
    st.markdown((ART / "cards" / f"{sel}.md").read_text())
    pd_csv = ART / "cards" / "proposed_domains.csv"
    if pd_csv.exists():
        df = pd.read_csv(pd_csv)
        st.download_button("Eksport proposed_domains.csv", df.to_csv(index=False), "proposed_domains.csv")
    gj = next(iter((ART / "graph").glob("run-*.json")), None)
    if gj:
        g = json.loads(gj.read_text())
        from pyvis.network import Network

        net = Network(height="520px", width="100%", bgcolor="#111", font_color="white")
        keep = {n["id"] for n in g["nodes"] if n["kind"] != "creative"} | {n["id"] for n in g["nodes"][:400]}
        col = {"creative": "#4c72b0", "advertiser": "#dd8452", "domain": "#55a868", "artifact": "#c44e52"}
        for n in g["nodes"]:
            if n["id"] in keep:
                net.add_node(n["id"], label=n["id"][2:20], color=col.get(n["kind"], "#999"), title=f"community {n['community']}")
        for e in g["edges"]:
            if e["src"] in keep and e["dst"] in keep:
                net.add_edge(e["src"], e["dst"], value=e["weight"])
        st.components.v1.html(net.generate_html(), height=540)

elif page == "Eksperymenty":
    st.header("Wyniki eksperymentów")
    v = ART / "tables" / "H1_verdict.txt"
    if v.exists():
        st.info(v.read_text())
    for e in ["E1_campaign_recovery", "E2_topic_probes", "E3_paraphrase_robustness", "E4_style_control", "E5_crossmodal_agreement", "E6_operational_value", "E7_complexity_ablation", "E8_comments"]:
        df = csv(f"{e}.csv")
        if df is not None:
            st.subheader(e)
            st.dataframe(df, use_container_width=True)
            img = ART / "figures" / f"{e}.png"
            if img.exists():
                st.image(str(img))

elif page == "Replay":
    st.header("Replay strumieniowy i lead time")
    log = need(csv("replay_log.csv", "replay"), "replay_log.csv")
    day = st.select_slider("Dzień", options=list(log.tick), value=log.tick.iloc[-1])
    st.metric("Liczba aktywnych śladów kampanii do wybranego dnia", int(log[log.tick <= day].n_tracks.max()))
    st.line_chart(log.set_index("tick")[["n_window", "n_tracks"]])
    lt = csv("lead_times.csv", "replay")
    if lt is not None and len(lt):
        sim = bool(lt.simulated.iloc[0])
        st.subheader("Lead time względem Listy CERT" + (" [SYMULACJA]" if sim else ""))
        st.write(f"Mediana: {lt.lead_days.median():.1f} dni; odsetek domen wykrytych wcześniej: {(lt.lead_days > 0).mean():.0%}")
        st.plotly_chart(px.histogram(lt, x="lead_days", nbins=20), use_container_width=True)

else:
    st.header("Warstwa komentarzy (dane syntetyczne)")
    df = csv("E8_comments.csv")
    if df is None:
        st.warning("Uruchom: `fejki comments`")
    else:
        st.dataframe(df)
        st.caption("Tylko hash autora, placeholdery kontaktów, brak łączenia kont po tożsamości.")
