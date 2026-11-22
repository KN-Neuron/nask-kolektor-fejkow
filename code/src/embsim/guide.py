"""Teksty objaśniające interfejs: do czego służy narzędzie, jak z niego korzystać, jak powstaje graf i na jakich danych działa."""
from __future__ import annotations

import pandas as pd
import streamlit as st

HOWTO = """
**Do czego to służy.** Analityk dostaje podejrzaną reklamę albo stronę i chce wiedzieć: *czy to coś nowego, czy część akcji, którą już znamy,
i kto za nią stoi?* Narzędzie porównuje nowy materiał ze zbiorem znanych incydentów (**galerią**), mówi, do czego go przypisać, i pokazuje
**dlaczego**: wspólne domeny, te same obrazy, ten sam zestaw zasobów strony, podobny tekst.

| krok | co robisz | co dostajesz |
|---|---|---|
| **1. Galeria** | w pasku bocznym wczytujesz znane materiały (foldery z HTML/HAR/zrzutami albo plik reklam Meta) | grupy: **kampanie** (ta sama akcja oszustów) i **operatorzy** (ta sama ekipa, kilka kampanii) |
| **2. Nowy materiał** | w zakładce *Analiza* wgrywasz zrzut, HAR, HTML, reklamę Meta, tekst albo adres (adresów nie odwiedzamy) | cechy materiału: tekst i ślady infrastruktury |
| **3. Werdykt** | czytasz wynik | jedna z trzech decyzji (niżej), trzy najsilniejsze powody i rysunek powiązań |
| **4. Decyzja analityka** | dodajesz materiał do galerii albo pobierasz kartę | galeria rośnie; zakładka *Klastry* pokazuje strukturę i to, co skleja grupy |

**Trzy możliwe decyzje**

- 🔴 **Znana kampania**: materiał jest wariantem czegoś, co już mamy (np. ta sama oferta z inną grafiką i domeną).
- 🟠 **Znany operator, nowa kampania**: inna treść, ale ta sama infrastruktura (zasoby strony, parametry adresu, domeny).
- ⚪ **Nowy wzorzec**: nic podobnego nie znamy. System niczego nie dokleja na siłę; to też jest pełnoprawny wynik.
"""

GRAPH_DOT = """
digraph G {
  rankdir=LR; bgcolor="transparent"; nodesep=0.35; ranksep=0.7;
  node [fontname="Helvetica", fontsize=11];
  edge [fontname="Helvetica", fontsize=10];
  subgraph cluster_k1 { label="kampania K1"; color="#c0392b"; fontcolor="#c0392b"; style=rounded;
    a [label="reklama A", shape=box, style="rounded,filled", fillcolor="#f6dcd9"];
    b [label="strona B", shape=box, style="rounded,filled", fillcolor="#f6dcd9"]; }
  subgraph cluster_k2 { label="kampania K2"; color="#c0392b"; fontcolor="#c0392b"; style=rounded;
    c [label="reklama C", shape=box, style="rounded,filled", fillcolor="#f6dcd9"]; }
  d [label="strona D\\n(nic wspólnego)", shape=box, style="rounded,filled", fillcolor="#e5e5e5"];
  t1 [label="te same obrazy,\\npodobny tekst", shape=note, style=filled, fillcolor="#fdf2e0"];
  t2 [label="zestaw zasobów\\n/aio-static/sdk", shape=note, style=filled, fillcolor="#e4eefb"];
  t3 [label="facebook.net\\n(w każdym materiale)", shape=note, style="filled,dashed", fillcolor="#f2f2f2"];
  a -> t1 [dir=none]; b -> t1 [dir=none];
  b -> t2 [dir=none, color="#2c6fbb"]; c -> t2 [dir=none, color="#2c6fbb"];
  d -> t3 [dir=none, style=dashed, color="#999999"]; a -> t3 [dir=none, style=dashed, color="#999999"];
}
"""

GRAPH_TEXT = """
1. **Węzły to materiały** (reklama, strona) oraz **ślady**, które da się z nich wyciągnąć: domena, zestaw zasobów strony, schemat parametrów
   adresu, piksel śledzący, identyczny obraz, a w reklamach Meta także płatnik i strona twórcy.
2. **Dla każdej pary materiałów liczymy jedną liczbę S od 0 do 1** (wzór poniżej). Składają się na nią: podobieństwo tekstu (embedding oraz
   n-gramy znaków) i **wspólne ślady, ważone rzadkością**: ślad spotykany w każdym materiale (Facebook, Google, CDN) nie znaczy nic, ślad
   spotkany tylko u dwóch materiałów znaczy dużo.
3. **Kampania** to grupa, w której materiały łączy S ≥ próg kampanii (treść i ślady razem). **Operator** to grupa łączona **wyłącznie
   śladami infrastruktury** przy niższym progu: ta sama ekipa zmienia przekaz, ale rzadko zmienia swoje narzędzia.
4. **Nowy materiał** dostaje werdykt z najlepszego dopasowania w galerii; jeśli nic nie przekracza progów, tworzy nowy wzorzec.
5. **Rysunek w zakładce Klastry** pokazuje tylko ślady, które *skleja* grupę (wspólne dla co najmniej dwóch materiałów). Czerwona ramka to
   jedna kampania, niebieska to ślady łączące kampanie w operatora. Szare, przerywane ślady są zbyt pospolite, żeby cokolwiek dowodzić.

Wersja z bazą grafową (Neo4j, zakładka *Klastry*) robi to samo na większą skalę: **twórca reklam jest węzłem głównym**, a znacznik „zdjęta
przez Metę” przechodzi z twórcy na jego reklamy. Wymaga pakietu `neo4j` (`pip install -e ".[graph]"`) i działającej bazy
(`docs/13_BAZA_GRAFOWA.md`). **Klastry z galerii działają bez bazy**: wybierz „Galeria (offline)”.
"""

DATA_ROWS = [
    ("folder z przypadkami (podfoldery = materiały)", "HTML zapisany z przeglądarki, HAR, zrzuty ekranu, `info.json`", "NASK-10, własne zgłoszenia"),
    ("reklamy Meta Ad Library", "JSON / JSONL z oficjalnego API", "próbka 14 936 reklam, 97 447 w całości"),
    ("kanał ruchu sieciowego", "JSONL: id, tekst, zbiory `host`, `kit`, `scheme`, `pixel` (`docs/15_FORMAT_KANALU_RUCHU.md`)", "eksport z grafu, dane z własnego scrapera"),
    ("pojedynczy tekst lub adres", "wklejony tekst reklamy, adres (używamy tylko domeny)", "zgłoszenie od użytkownika"),
]

DATA_TEXT = """
**Czy to zadziała na innych danych?** Metoda **nie jest wytrenowana na żadnym zbiorze**: wagi kanałów są równe, a na etykietach dobieramy
tylko dwa progi decyzyjne. Nowe dane nie wymagają uczenia, ale wymagają **sprawdzenia progów**:

- progi z jednego źródła nie przenoszą się 1:1: dla stron (HTML, HAR, zrzuty) 0,725, dla reklam Meta optimum wyszło ok. 0,5. Suwak w
  pasku bocznym zmienia próg od razu. Próg można też dobrać na własnych materiałach z etykietami, tak jak w `embsim/bench.py` (kalibracja
  na zbiorze dev); gotowego polecenia dla cudzych danych nie ma;
- sprawdziliśmy to na **trzech rodzajach danych**: syntetycznych światach z prawdą (80 światów, podział po światach), reklamach Meta
  (4,5 tys. reklam, test po czasie) i dziesięciu przypadkach NASK; liczby i ograniczenia: `docs/WYNIKI.md`;
- **czego nie umie**: nie rozpoznaje twarzy ani logotypów, a prawdziwych etykiet kampanii dla Mety nie ma, więc tam mierzymy tylko zgodność
  z twórcą i z oznaczeniem zdjęcia reklamy przez Metę; OCR polskiego tekstu wymaga pakietu `tesseract-ocr-pol` (w kontenerze jest).
"""


def render_howto() -> None:
    st.markdown(HOWTO)


def render_graph_explainer() -> None:
    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown(GRAPH_TEXT)
    with c2:
        st.caption("Schemat: ramka to kampania, kartki to ślady. Wspólny ślad łączy materiały, pospolity (przerywany) nie łączy.")
        st.graphviz_chart(GRAPH_DOT, use_container_width=True)


def render_data() -> None:
    st.markdown(DATA_TEXT)
    st.dataframe(pd.DataFrame(DATA_ROWS, columns=["wejście", "format", "przykład"]), use_container_width=True, hide_index=True)
