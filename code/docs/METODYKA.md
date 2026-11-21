# Kolekcjoner Fejków: metodyka demonstratora

Wyzwanie „Follow the Fake” (HackNation × NASK). Narzędzie łączy pojedyncze materiały z podejrzanych reklam w kampanie
i dla każdego powiązania podaje przesłanki. Nie jest detektorem pojedynczego fejka.

## 1. Wejście

| Rodzaj | Co z niego bierzemy |
|---|---|
| folder przypadku (jak w zbiorze organizatora) | wszystko poniżej, łącznie |
| zapis strony HTML (z folderem `_files`) | tytuł, widoczny tekst, adres zapisu (`saved from url`), linki, piksele w kodzie, klasy HTML, obrazy |
| log ruchu HAR | wszystkie adresy (parametry, ścieżki, usługi zewnętrzne), przekierowania 3xx |
| zrzut ekranu / kreacja | OCR (Tesseract), pHash, nazwa reklamodawcy („… Sponsorowane”) |
| nagranie (mp4) | klatki co 3 s (ffmpeg): OCR i pHash |
| `info.json` (np. z Meta Ad Library) | identyfikator reklamy, tytuł, opis |
| adres URL | analiza bierna: domena, schemat parametrów, identyfikatory reklam i pikseli, wzorzec ścieżki; opcjonalnie DNS/RDAP/crt.sh |
| tekst / nazwa produktu | słowa kluczowe, osoby, tematyka, dopasowanie nazw produktów |

Brak dowolnego elementu nie przerywa analizy: materiał dostaje listę braków, a porównanie korzysta z dostępnych kanałów.
**Stron oszustów nie odwiedzamy.** Korzystamy z plików nagranych przez organizatora i z biernych, publicznych źródeł.

## 2. Cechy (kanały)

- **tekst**: TF-IDF słów i bigramów na tytułach (waga ×3) i treści, polskie znaki ujednolicone (OCR bez pakietu `pol` je gubi);
  w uzasadnieniu pokazujemy najmocniej wspólne słowa;
- **osoby**: mała baza osób publicznych (`config/osoby.txt`); pełne imię i nazwisko z polską odmianą, aliasy tylko dla nazwisk
  jednoznacznych (np. „Lewandowski” wymaga imienia, „Lewandowska” nie łapie „Lewandowski”);
- **produkt**: krótki tytuł strony nie będący nagłówkiem newsa; dopasowanie także gdy nazwa pada w treści drugiego materiału;
- **reklamodawca**: nazwa strony przy „Sponsorowane” odczytana ze zrzutu reklamy;
- **śledzenie**: identyfikatory reklam Meta (`ad_id`, link do Ad Library), piksele Meta (`fbq('init')`, `pxl=`, `facebook.com/tr?id=`),
  Google Ads / GTM, oznacznik konta w adresie (`acc=`);
- **adres**: schemat parametrów jako odcisk systemu kierowania ruchu (np. losowe `utm_id` 20 znaków, `utm_medium/campaign/content`
  10 znaków, `utm_visit` UUID), wzorce ścieżek z podmienionymi identyfikatorami, charakterystyczne katalogi zestawów stron,
  nietypowe usługi zewnętrzne (pomijamy CDN-y i usługi masowe), cele przekierowań;
- **domena**: domena docelowa (adres zapisu strony, nazwa pliku HAR);
- **obraz**: pHash (DCT 32×32 → 64 bity) zrzutów, kreacji, klatek i obrazów użytych na stronach;
- **szablon strony**: zbiór klas HTML (Jaccard) oraz wykrywanie cloakingu (ta sama domena serwuje różne strony);
- **tematyka**: słownik (fałszywy news, inwestycje, zdrowie, hazard, sklep); bardzo słaby sygnał;
- **infrastruktura** (opcjonalnie, wymaga sieci): DNS, ASN (Team Cymru), RDAP, dziennik certyfikatów crt.sh; reguły: wspólny
  adres IP (słaby, jeśli CDN), ten sam zestaw serwerów nazw, podsieć /24, rejestracja w krótkim odstępie, ten sam certyfikat.

## 3. Podobieństwo

Każdy kanał zwraca dowody `(kod, kanał, waga, opis)`. Wynik pary:

1. noisy-OR wag w obrębie kanału (osoby z limitem 0,5),
2. noisy-OR między kanałami: `1 − Π(1 − p_kanał)`.

Cechy pospolite tracą wagę (`2 / liczba materiałów z cechą`, gdy cechę ma więcej niż 2 materiały), więc ta sama znana twarz
w wielu kampaniach nie skleja ich sama. Wagi (`fejki.demo.similar.W`) ustawiliśmy ręcznie według specyficzności sygnału:
identyfikator reklamy 0,95, piksel 0,9, ta sama domena 0,9, niemal identyczny tekst 0,9, wspólny wzorzec ścieżki 0,7,
schemat parametrów 0,6, osoba 0,3, tematyka 0,1.

Relacja pary: **duplikat** (ten sam identyfikator reklamy albo tekst ≥ 0,95 z tym samym tytułem/domeną/obrazem),
**wariant tego samego przekazu** (tekst ≥ 0,6, ten sam tytuł lub produkt, albo podobny szablon i tekst ≥ 0,4),
**wspólna infrastruktura / operator** (tylko ślady techniczne), **podobieństwo treści**.

## 4. Grupowanie

- **kampania**: składowe spójne krawędzi typu duplikat/wariant z wynikiem ≥ próg (domyślnie 0,7);
- **sieć**: składowe spójne wszystkich krawędzi ≥ próg, czyli kampanie prawdopodobnie jednego operatora.

## 5. Nowy materiał

Porównanie z każdym materiałem zbioru, wynik kampanii = najsilniejsze powiązanie z jej członkiem. Decyzja:
przypisanie do kampanii (ten sam przekaz ≥ próg) · nowy przekaz w znanej sieci (tylko infrastruktura ≥ próg) ·
możliwe powiązanie do weryfikacji (≥ 0,4) · nowy wzorzec.

## 5a. Karta kampanii (`fejki demo cards`, zakładka „Kampanie i sieci”)

Dla każdej kampanii: materiały i sieć operatora, **okno obserwacji** (najwcześniejszy i najpóźniejszy znacznik czasu:
`startedDateTime` z logów HAR, daty RRRR-MM-DD z nazw zrzutów i nagrań przeliczone z czasu polskiego na UTC, `timestamp`
z `info.json`; niejednoznaczne formaty jak `08-12-2026` pomijamy), tematyka, osoby, produkty, reklamodawcy, identyfikatory
reklam i pikseli, **domeny do weryfikacji** z priorytetem i uzasadnieniem:

| Priorytet | Rola domeny |
|---|---|
| wysoki | domena docelowa reklamy w tej kampanii |
| średni | nietypowa usługa zewnętrzna ładowana przez stronę kampanii; cel przekierowania; domena innej kampanii tej samej sieci |

Z kanałem infrastruktury karta podaje datę rejestracji, rejestratora i **wiek domeny przy pierwszej obserwacji**
(≤ 7 dni = „świeża domena”). Okno to czas zebrania materiałów, nie czas emisji reklam; daty emisji da Meta Ad Library.
Eksport: Markdown (karta lub wszystkie) i CSV domen do weryfikacji.

## 5b. Schemat perswazji ponad tematami (zakładka „Schemat perswazji”; analiza, nie wpływa na grupowanie)

Hipoteza z pierwotnego planu: oszuści zmieniają temat, ale powtarzają schemat perswazji, więc po usunięciu tematu z wektorów
tekstu materiały jednego operatora powinny być bliżej siebie.

- **DNA perswazji** (`demo/persuasion.py`): 10 ruchów wykrywanych słownikami (szokujący news, tajemnica, autorytet,
  presja czasu, dowód społeczny, obietnica zysku, niska bariera, formularz, podrobiony portal, cena/rabat) na 1000 słów.
  Sieć S1 łączy profil „szokujący news + obietnica zysku + niska bariera”; landery produktowe (14, 47) to „dowód społeczny
  + presja czasu”; przypadek 36 prawie nie ma ruchów (strona-przykrywka).
- **LEACE** (`demo/template.py`): tekst dzielony na fragmenty ~400 znaków (bez adresów), kodowany enkoderem, etykieta
  **tematu** ze słownika dla każdego fragmentu (nigdy etykieta sieci), LEACE usuwa liniowo temat; kontrola: losowa
  podprzestrzeń tego samego rzędu; wektor materiału = średnia fragmentów. Sieci do oceny pochodzą z infrastruktury, kanał
  widzi tylko tekst, więc ocena nie jest cyrkularna.
- **Wynik wstępny (2026-11-21, enkoder offline TF-IDF+SVD, 10 przypadków, 271 fragmentów, usunięty rząd 5, bez duplikatów):**

| Wariant | ta sama sieć | ta sama sieć, inny temat | różne sieci | odstęp |
|---|---|---|---|---|
| surowe | 0,190 | 0,171 | 0,055 | 0,135 |
| LEACE (bez tematu) | 0,190 | 0,169 | 0,057 | 0,133 |
| kontrola losowa | 0,178 | 0,174 | 0,051 | 0,127 |

  Sam tekst odróżnia sieć S1 od reszty (0,17–0,19 wobec 0,055), ale **LEACE nic nie zmienia**: przy enkoderze leksykalnym
  temat nie leży w kilku kierunkach.

- **Wynik z bge-m3 (2026-11-21, te same dane i ustawienia):**

| Wariant | ta sama sieć | ta sama sieć, inny temat | różne sieci | odstęp |
|---|---|---|---|---|
| surowe | 0,897 | 0,898 | 0,683 | **0,214** |
| LEACE (bez tematu) | 0,909 | 0,924 | 0,751 | **0,158** |
| kontrola losowa | 0,897 | 0,898 | 0,682 | 0,215 |

  LEACE **zbliża wszystkie strony oszustw do siebie** (różne sieci: 0,683 → 0,751), więc odstęp między sieciami **maleje**
  (0,214 → 0,158); kontrola losowa nie zmienia nic, czyli efekt jest realny. Wniosek: po usunięciu tematu zostaje wspólny
  „język oszustwa”, a nie podpis konkretnego operatora. **Hipoteza „schemat perswazji odróżnia operatorów” na tych danych
  nie jest potwierdzona.** Nowa, testowalna hipoteza: schemat perswazji (po LEACE) odróżnia **oszustwa od legalnych treści**
  ponad tematami; do sprawdzenia na trudnych negatywach (prawdziwe portale, legalne reklamy z Meta). Uwaga: 10 przypadków,
  ilustracja, nie dowód.

## 5c. Dodatkowe mechanizmy

- **Kanał semantyczny** (opcjonalny, `semantic=True` / przełącznik w UI): wektory znaczenia tekstu z bge-m3 (średnia z fragmentów).
  Wszystkie strony oszustw mają do siebie wysokie podobieństwo (tło do 0,86), więc dowód powstaje dopiero **powyżej 0,88**
  (`SEM_FLOOR`), z wagą do 0,5. Wynik: na zbiorze organizatora grupowanie bez zmian, dowód wzmacnia pary w sieci S1 (waga 0,02–0,11).
- **Logotypy / podrabiane marki**: marka z nazwy pliku logotypu w zasobach strony (`logo-gazeta.svg` → „gazeta”); dowód o wadze 0,3
  (wiele kampanii podrabia te same portale, więc to słaby sygnał).
- **Szablon strony**: dowód tylko dla stron z ≥ 25 różnymi klasami/elementami HTML i wagą do 0,35 (mała strona zawsze „pasuje” do
  małej; wykryte testem negatywnym: sam szablon dawał 0,6 i wprowadzał obcy materiał do „do weryfikacji”).
- **Grupowanie**: średnie wiązanie z wymogiem wsparcia (średni wynik par między grupami ≥ 0,15) zamiast składowych spójnych;
  na urlscan próg 0,5: F1 0,627 → 0,678, największa grupa 89 → 46 (literatura entity resolution: łańcuchowanie / „czarna dziura”).
- **Wsad nowego zbioru** (`fejki demo match`, zakładka „Nowy zbiór”): folder z podfolderami, płaski folder lub zip (bezpieczne
  rozpakowanie), CSV z decyzją, kampanią, siecią i przesłankami oraz **propozycje nowych kampanii** z materiałów nieprzypisanych.
- **Scheduler** (`fejki demo watch`): okresowe zapytania do Meta Ad Library po słowach kluczowych, nowe reklamy jako materiały,
  dopasowanie do kampanii, historia w `data/meta/watch_report.csv`; wymaga aktualnego tokenu (czytelny komunikat po wygaśnięciu).
- **Eksport grafu** (`fejki demo export`): GraphML, Cypher dla Neo4j, CSV (węzły: Material, Domain, Pixel, Person, Campaign, Network).

## 5d. Kanał obrazu, dowód przeciwny, blokowanie, ablacja (wyniki zmierzone 2026-11-21)

- **Kanał obrazu** (`demo/vision.py`, Meta Perception Encoder PE-Core B/16, Apache-2.0, 1,79 GB, opcjonalny): wektor materiału = średnia
  embeddingów jego zrzutów i kreacji; dowód „podobny wygląd” dopiero od podobieństwa **0,92** (`VIS_FLOOR`).
  Pomiary: (a) **zrzuty reklam ze zbioru organizatora** (karty z telefonu): podobieństwo odzwierciedla format, nie kampanię
  (48↔61, ta sama kampania: 0,41; 10↔14, różni operatorzy: 0,84), więc niska podłoga łączyłaby fałszywie; (b) **117 zrzutów stron z urlscan**:
  ROC AUC 0,753, AP 0,822 (baza 0,473), przy podobieństwie ≥ 0,8 precyzja 0,998 (548 par), ≥ 0,92 prawie to samo. Wniosek: wygląd strony
  wskazuje ten sam zestaw (kit), ale ogólny wygląd karty reklamy nie rozróżnia kampanii; kanał działa jako wykrywacz niemal-duplikatów.
- **Dowód przeciwny** (`similar.conflict`): różne piksele Meta albo różne schematy TDS przy braku wspólnej domeny, piksela, id reklamy
  i trackera obniżają wynik ×0,6 i są pokazywane jako przesłanka „przeciw”. Powód: ablacja na syntetyce wykazała, że wspólny zestaw stron
  i generyczny schemat `utm_*` sklejają różnych operatorów (sieć F1 0,473). Po poprawce: sieć F1 **0,849** (kampania 0,909 → 0,984);
  zbiór organizatora bez zmian; urlscan F1 0,614 → 0,608.
- **Blokowanie kandydatów** (powyżej 300 materiałów, `BLOCK_ABOVE`): liczymy pary ze wspólnym kluczem (domena, piksel, id reklamy, schemat,
  katalog, wzorzec ścieżki, usługa, tytuł, reklamodawca, logo, kontakt) lub z 12 najbliższych sąsiadów w tekście. Na 122 skanach urlscan:
  7381 → 1168 par (czas 0,9 s → 0,2 s), **kosztem czułości** (F1 0,614 → 0,49, gdy wymuszone na małym zbiorze); dlatego włączane dopiero
  przy dużych zbiorach. Na zbiorze organizatora wynik identyczny.
- **Model par** (`demo/learn.py`) opcjonalnie zastępuje ręczne wagi (przełącznik w UI i parametr `model`): ROC AUC 0,791 wobec 0,775.
- **Syntetyka i ablacja** (`fejki demo synth`, `fejki demo ablate`): 42 przypadki (6 operatorów, w tym dwóch ze wspólnym zestawem stron;
  ta sama narracja u różnych operatorów; 6 negatywów z tymi samymi osobami), domeny `.example`/`.test`. Ablacja: bez tekstu kampania F1
  spada 0,98 → 0,60 (najważniejszy kanał przy braku wspólnych identyfikatorów); sam tekst daje kampanię F1 0,91; sam „adres” tylko 0,60.
  Ograniczenie: syntetyka sprawdza odzyskanie podłożonej struktury, nie realizm kampanii.

## 6. Testy (`fejki demo eval`)

Nie mamy etykiet kampanii od organizatora, więc „oczekiwane” = wynik na pełnym zbiorze. Test mierzy stabilność i odporność,
nie trafność względem podziału organizatora.

- **pomiń-jeden** (10 przypadków): każdy przypadek dopasowany jako nowy do reszty zbioru. Wynik: spójność kampanii 100%, sieci 100%;
  pojedyncze przypadki nie zostały doklejone do żadnej grupy.
- **niepełne wejście**: sam HTML albo sam HAR trafia do właściwej sieci we wszystkich sprawdzonych przypadkach (1, 2, 3, 48, 61).
  **Same zrzuty ekranu nie wystarczają** (0 z 4): zrzut reklamy ma mało tekstu, a w zbiorze nie ma drugiego podobnego zrzutu.
- testy jednostkowe na sztucznych plikach: `pytest tests/test_demo.py`.

## 7. Ograniczenia

- wagi i progi ustalone ręcznie, na małym zbiorze (10 przypadków);
- OCR bez polskiego pakietu gubi diakrytyki (obraz Dockera instaluje `tesseract-ocr-pol`);
- osoby rozpoznajemy po nazwiskach w tekście i OCR; bez rozpoznawania twarzy;
- transkrypcja mowy z nagrań nie jest włączona (klatki tak);
- kanał infrastruktury wymaga dostępu do sieci; bez niego działa reszta;
- schemat parametrów jest silnym sygnałem zestawu oszustów, ale te same zestawy mogą być sprzedawane wielu operatorom.

## 8. Biblioteki, usługi i licencje

| Składnik | Licencja | Do czego |
|---|---|---|
| Streamlit | Apache-2.0 | interfejs |
| pandas, NumPy, SciPy, scikit-learn | BSD-3 | dane, pHash (DCT), TF-IDF |
| pydantic, typer, rapidfuzz, PyYAML, plotly | MIT | modele danych, CLI, dopasowania rozmyte |
| networkx, httpx, tldextract, python-dotenv, lxml | BSD-3 | grafy, HTTP do RDAP/crt.sh, domeny |
| pyvis (z vis-network) | BSD-3 (vis-network: Apache-2.0/MIT) | graf powiązań |
| Beautiful Soup | MIT | parsowanie HTML |
| Pillow | MIT-CMU (HPND) | obrazy |
| pytesseract, Tesseract OCR | Apache-2.0 | OCR |
| FFmpeg | LGPL-2.1+ (zależnie od kompilacji GPL) | klatki z nagrań |
| dnspython | ISC | DNS |
| scikit-learn | BSD-3 | TF-IDF, regresja logistyczna (model par) |
| sentence-transformers, PyTorch | Apache-2.0, BSD-3 | enkoder semantyczny (opcjonalny) |
| BAAI/bge-m3 (model) | MIT | embeddingi tekstu wielojęzyczne, ~2,2 GB, lokalnie |
| concept-erasure (LEACE) | MIT | analiza „schemat perswazji” (część badawcza) |
| NetworkX | BSD-3 | graf, eksport GraphML |

Dodatkowe dane (budowa zbiorów, nie demonstracja): **urlscan.io**, wyszukiwarka istniejących publicznych skanów
(bez klucza: metadane i zrzuty; z darmowym kluczem `URLSCAN_API_KEY`: pełny wynik i DOM); nie zlecamy nowych skanów; dane
zostają lokalnie; źródło każdego przypadku zapisane w `labels.csv`. Opis: `docs/07_ZBIORY_DANYCH.md`.

Usługi zewnętrzne (tylko kanał infrastruktury, opcjonalnie): publiczne serwery DNS, Team Cymru IP-to-ASN (DNS), rdap.org,
crt.sh. Nie wymagają kluczy. **Meta Ad Library API** (opcjonalnie, do sprawdzania `ad_id`): wymaga potwierdzenia tożsamości
(facebook.com/ID), akceptacji warunków na facebook.com/ads/library/api, aplikacji deweloperskiej i tokenu w `.env`
(`META_ACCESS_TOKEN`); dla reklam komercyjnych w UE API zwraca ograniczony zestaw pól.

## 9. Dane

Zbiór organizatora (`DANE.zip`) służy wyłącznie realizacji wyzwania i nie może być publicznie rozpowszechniany. Nie jest częścią
repozytorium ani obrazu Dockera: podaje się go przy uruchomieniu (`FEJKI_DATA` lub wolumen `/data`). Indeks
(`artifacts/demo/index.json`) zawiera cechy wyciągnięte z tych danych, więc też nie trafia do repozytorium.
