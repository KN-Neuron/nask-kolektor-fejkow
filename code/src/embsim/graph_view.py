"""Widok „Klastry w grafie (Neo4j)”, przeniesiony z fejki.app.graph_tab do nowego interfejsu (jedna implementacja): twórcy z Mety, sieci i kampanie NASK/syntetyki, nowe materiały z `add`.

Dane z Neo4j (graph/clusters.py), połączenie z NEO4J_URI / NEO4J_PASSWORD (code/.env), jak przy ładowaniu.
Jeden klaster naraz: karta z liczbami, rysunek tylko z tym, co klaster skleja (bez hubów), tabela przesłanek.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

CODE = Path(__file__).resolve().parents[2]            # katalog code/

sys.path.insert(0, str(CODE / "graph"))


@st.cache_resource(show_spinner=False)
def _driver():
    from load import driver

    d = driver()
    d.verify_connectivity()
    return d


@st.cache_data(ttl=300, show_spinner=False)
def _q(name: str, *args):
    import clusters

    with _driver().session() as s:
        return getattr(clusters, name)(s, *args)


def _table(rows, **kw):
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, **kw)


def render() -> None:
    try:
        import clusters
        from neo4j.exceptions import AuthError, ServiceUnavailable
    except ImportError:
        st.info("Widok z grafu Neo4j wymaga pakietu `neo4j` (`pip install -e \".[graph]\"`) i działającej bazy (docs/13_BAZA_GRAFOWA.md). "
                "Klastry z galerii działają bez bazy: wybierz „Galeria (offline)”.")
        return

    st.subheader("Klastry w grafie (Neo4j)")
    st.caption("Jeden klaster naraz i tylko to, co go skleja. Pospolite ślady (google.com, CDN, trackery) są pominięte, bo niczego "
               "nie dowodzą. Dane: baza Neo4j (lokalna albo serwer zespołu, zależnie od NEO4J_URI w code/.env).")
    try:
        _driver()
    except KeyError:
        st.warning("Brak hasła do Neo4j: ustaw `NEO4J_PASSWORD` (i ewentualnie `NEO4J_URI`, `NEO4J_USER`) w `code/.env` albo w zmiennych "
                   "środowiska i uruchom demo ponownie. Hasło lokalnej bazy to to, z którym uruchomiono `docker compose up -d`.")
        return
    except (ServiceUnavailable, AuthError, OSError) as e:  # brak bazy albo złe hasło: reszta demo działa dalej
        st.warning(f"Brak połączenia z Neo4j ({type(e).__name__}). Uruchom bazę (`docker compose up -d`) albo ustaw NEO4J_URI "
                   "w code/.env na serwer zespołu; instrukcja: docs/13_BAZA_GRAFOWA.md.")
        return

    view = st.radio("Co pokazać", ["Twórcy (reklamy Meta)", "Sieci i kampanie (NASK, syntetyka)", "Nowe materiały (add / scraper)"],
                    horizontal=True)

    if view.startswith("Twórcy"):
        c1, c2, c3 = st.columns([1, 1, 2])
        label = c1.selectbox("Etykieta", ["scam", "podejrzany", "brak sygnału", "wszystkie"])
        min_ads = c2.number_input("Min. reklam", 1, 1000, 2)
        q = c3.text_input("Szukaj (twórca, strona, płatnik, domena)", placeholder="np. Sharon Coleman")
        rows = _q("creators", None if label == "wszystkie" else label, int(min_ads), q or None)
        if not rows:
            st.info("Brak twórców dla tych filtrów.")
            return
        st.caption(f"{len(rows)} twórców (najwyżej 300). Na górze: powiązani z przypadkami NASK, potem z największą liczbą stron.")
        _table([{k: v for k, v in r.items() if k != "id"} for r in rows], height=240)
        pick = st.selectbox("Karta twórcy", [r["id"] for r in rows],
                            format_func=lambda i: next(f"{r['twórca']} · {r['etykieta']} · {r['reklam']} reklam" for r in rows if r["id"] == i))
        card = _q("creator_card", pick)
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Etykieta", card["label"])
        m2.metric("Reklam", card["n_ads"])
        m3.metric("Zdjętych przez Metę", f"{card['n_flagged']} ({round(100 * (card['share'] or 0))}%)")
        m4.metric("Stron", card["n_pages"])
        m5.metric("Płatników", card["n_payers"])
        texts = card["texts"] or ("0: Meta usunęła treść tych reklam, w Ad Library został tylko komunikat o usunięciu"
                                  if card["n_flagged"] else 0)
        st.caption(f"Okres emisji: {card['od']} – {card['do']} · różnych tekstów: {texts} · "
                   f"tematy (zapytania): {', '.join(card['topics']) or '—'}")
        st.subheader("Dlaczego to jeden twórca")
        if card["glue"]:
            st.graphviz_chart(clusters.creator_dot(card), width="stretch")
            _table([{"ślad": clusters.KIND_PL[g["kind"]], "wartość": g["name"], "łączy strony": ", ".join(g["pages"][:8])
                     + (f" (+{len(g['pages']) - 8})" if len(g["pages"]) > 8 else ""), "reklam": g["ads"]} for g in card["glue"]])
        else:
            st.write("Jedna strona, więc nic nie trzeba sklejać.")
            if card["materials"]:
                st.graphviz_chart(clusters.creator_dot(card), width="stretch")
        if card["materials"]:
            st.subheader("Przypadki NASK i nowe materiały tego twórcy")
            _table(card["materials"])
        with st.expander(f"Strony ({len(card['pages'])})"):
            _table(card["pages"])
        with st.expander("Reklamy (najpierw zdjęte przez Metę, najwyżej 30)"):
            _table(card["ads"], column_config={"link": st.column_config.LinkColumn("Ad Library")})
        st.download_button("Karta (Markdown)", clusters.creator_markdown(card).encode("utf-8"), f"twórca_{card['id']}.md")
        st.code(f"MATCH p = (c:Creator {{id: '{card['id']}'}})<-[:PART_OF]-(x) RETURN p", language="cypher")

    elif view.startswith("Sieci"):
        ds = st.radio("Zbiór", ["nask", "synth", "nowe"], horizontal=True,
                      format_func={"nask": "NASK", "synth": "syntetyka (ze znaną prawdą)", "nowe": "nowe z add"}.get)
        rows = _q("groups", ds)
        if not rows:
            st.info("Brak kampanii w tym zbiorze (kampanie liczy `load.py nask` / `load.py synth`).")
            return
        _table([{**r, "kampanie": ", ".join(r["kampanie"]), "materiały": ", ".join(r["materiały"])} for r in rows], height=220)
        pick = st.selectbox("Karta sieci / kampanii", [r["id"] for r in rows],
                            format_func=lambda i: next(f"{r['typ']} {i} · {r['liczba']} materiałów" for r in rows if r["id"] == i))
        card = _q("group_card", pick)
        st.subheader("Co łączy te materiały")
        if card["shared"]:
            st.graphviz_chart(clusters.group_dot(card), width="content")
            _table([{"ślad": clusters.REL_PL[s["rel"]], "wartość": s["name"], "materiały": ", ".join(s["ms"])} for s in card["shared"]])
        else:
            st.write("Brak wspólnych śladów poza hubami; połączenie wynika z podobieństwa treści (tabela niżej).")
        st.subheader("Materiały")
        _table(card["materials"])
        if card["pairs"]:
            st.subheader("Pary i ich przesłanki")
            _table([{**p, "przesłanki": " | ".join((p["przesłanki"] or [])[:4])} for p in card["pairs"]])
        st.download_button("Karta (Markdown)", clusters.group_markdown(card).encode("utf-8"), f"klaster_{card['id']}.md")

    else:
        rows = _q("added")
        if not rows:
            st.info("Nic jeszcze nie dodano. Dodawanie: `graph/scrape.py add …` albo scraper `graph/scrape.py watch …`.")
            return
        _table([{k: v for k, v in r.items() if k != "wyjaśnienie"} for r in rows], height=260)
        pick = st.selectbox("Karta materiału", [r["id"] for r in rows],
                            format_func=lambda i: next(f"{i} · {clusters.VERDICT_PL.get(r['decyzja'], r['decyzja'])} · {r['twórca'] or '—'}"
                                                       for r in rows if r["id"] == i))
        card = _q("added_card", pick)
        if card:
            st.subheader("Z czym go połączyliśmy i dlaczego")
            if card["matches"] or card["traces"]:
                st.graphviz_chart(clusters.added_dot(card), width="stretch")
                st.caption("Czerwona strzałka: znana kampania · pomarańczowa: ten sam operator (materiał, który rozstrzygnął decyzję) · "
                           "szara przerywana: inne bliskie materiały. Ramki: twórcy (operatorzy z Mety). Owale: ślady wspólne z bliskimi "
                           "materiałami; kropkowane = pospolita usługa (np. instagram.com), która niczego nie dowodzi.")
                _table([{"materiał": m["id"], "twórca": m["creator"], "wynik kampanii": m["score"], "wynik operatora": m["operator_score"],
                         "powody": " | ".join(m["reasons"][:3]), "treść": m["snippet"]} for m in card["matches"]])
            else:
                st.write("Silnik nie zapisał bliskich materiałów ani śladów dla tego materiału.")
        with st.expander("Wyjaśnienie zapisane przy dodaniu", expanded=not card):
            st.text(next(r["wyjaśnienie"] for r in rows if r["id"] == pick) or "—")
