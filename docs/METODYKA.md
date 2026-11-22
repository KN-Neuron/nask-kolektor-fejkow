# Metodyka

Jedna metoda, od materiału do decyzji. Wzór podobieństwa ze wszystkimi składnikami: [14_WZOR_PODOBIENSTWA.md](14_WZOR_PODOBIENSTWA.md).

## 1. Przepływ

```
wejście (zrzut | HTML | HAR | reklama Meta JSON/JSONL | tekst | URL)
   │   adresów URL nie odwiedzamy: używamy tylko domeny jako śladu
   ▼
cechy materiału (embsim/features.py, embsim/analyze.py)
   │   tekst: HTML, info.json, OCR zrzutu, wpis użytkownika
   │   ślady: host, kit (zasoby), scheme (parametry adresu), pixel
   ▼
wynik podobieństwa do każdego materiału z galerii (embsim/score.py; wzór w docs/14, bez uczenia)
   ▼
decyzja (embsim/api.py: Gallery.add / query)
   │   S_kampanii ≥ t_k → znana kampania
   │   inaczej S_operatora ≥ t_o → znany operator, nowa kampania
   │   inaczej → nowy wzorzec (nie doklejamy)
   ▼
przesłanki (trzy najsilniejsze powody, wspólne ślady, pewność dowodu) + sieć + karta dla analityka (embsim/app.py)
   │   zakładka „Klastry”: operator -> kampanie -> materiały z galerii (offline) albo twórcy i sieci z grafu Neo4j (embsim/graph_view.py)
   ▼
(opcjonalnie) graf Neo4j: twórca jako węzeł główny, etykieta scam propagowana z twórcy (graph/creators.py), scraper (graph/scrape.py)
```

## 2. Decyzje projektowe

- **Bez uczenia.** Wagi kanałów równe 1; jedyne liczby dobierane na etykietach to dwa progi decyzyjne. Opcjonalna głowa kontrastowa
  (`embsim/metric.py`) nie wchodzi do wyniku; można o niej wspomnieć jako o możliwym rozszerzeniu.
- **Brak śladu to brak dowodu, nie dowód różnicy.** Domeny lądowania i piksele są rotowane między wariantami, więc kanał śladów liczy się
  tylko przy wspólnym śladzie; waga śladu rośnie z jego rzadkością (idf), więc trackery obecne wszędzie nie znaczą nic.
- **Niekompletne dane.** Wynik uwzględnia, ile kanałów da się w ogóle porównać (λ w docs/14): im mniej dowodu, tym wyższy wynik jest potrzebny.
- **Twórca jako węzeł główny (graf).** Reklamy łączy strona, płatnik, domena lub identyczny tekst; etykieta „scam” wynika ze zdjęcia reklam
  przez Metę i przechodzi z twórcy na jego reklamy. To sygnał egzekwowania, nie dowód.
- **Nowy wzorzec jest pełnoprawną decyzją.** Zdolność niełączenia tego, czego łączyć nie wolno, jest mierzona osobno (odsetek obcych materiałów zostawionych jako nowy wzorzec).

## 3. Ewaluacja

Protokół wzorowany na N-LNSO ([motor-imagery-AI](https://github.com/KN-Neuron/motor-imagery-AI)):
- **Podmiot** jest jednostką niezależności: świat syntetyczny (`embsim/cv.py`) albo twórca (`embsim/stream_eval.py`).
- Podział po podmiotach przed jakimkolwiek przetwarzaniem; test użyty raz; dobór progów i konfiguracji zagnieżdżony w zbiorze treningowym.
- Przedziały ufności bootstrapem po podmiotach; porównania parami testem Wilcoxona z korektą Holma.
- **Ewaluacja strumieniowa na Mecie:** reklamy po czasie (50% galeria, 20% walidacja, 30% test), pytanie „czy nowa reklama trafia do swojego
  twórcy albo zostaje rozpoznana jako nowa”.
Wyniki i ograniczenia: [WYNIKI.md](WYNIKI.md).

## 4. Zgodność z wymaganiami zadania

| wymaganie | stan | gdzie |
|---|---|---|
| przyjmować zrzut, HAR, HTML, tekst, URL, dane z udostępnionego zbioru | tak (nagrania wideo: tylko metadane z `info.json`) | `analyze.py`, `app.py` |
| tekst, domeny, przekierowania, linki, struktura stron, metadane infrastruktury | częściowo: tekst, domeny, zasoby, parametry, piksele; przekierowania w wersji 2 | `features.py`, `15_FORMAT_KANALU_RUCHU.md` |
| wizerunki osób, logotypy, cechy wizualne | **brak** (nazwiska w tekście; kanał obrazu słaby) | — |
| duplikaty i warianty | tak | `score.py` (kanały tekstowe) |
| metoda podobieństwa i grupowania | tak, jedno wyrażenie | `14_WZOR_PODOBIENSTWA.md` |
| analiza nowego materiału względem zbioru, wskazanie nowej kampanii | tak | `api.py` |
| klastry, graf, lista podobnych incydentów | tak (sieć w interfejsie, graf Neo4j) | `app.py`, `13_BAZA_GRAFOWA.md` |
| cechy i przesłanki powiązania | tak | `Decision.explain`, `top_reasons` |
| niekompletne dane | tak, zmierzone | `cv.py` (scenariusze bez HAR, bez HTML) |
| prosty interfejs, dokumentacja, instalacja, repozytorium | tak | `make demo`, `Dockerfile` |
| (dodatkowo) scheduler / scraper | tak, z pliku JSONL (token Mety niewpięty) | `graph/scrape.py` |
