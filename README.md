# Kolekcjoner Fejków (Follow the Fake): HackNation × NASK

Narzędzie, które z pojedynczych podejrzanych reklam i stron wydobywa wspólne ślady, łączy je w **kampanie** i **operatorów** i pokazuje,
**dlaczego** materiały zostały połączone. Wyzwanie zgłosił Ośrodek Badań nad Bezpieczeństwem Sztucznej Inteligencji NASK PIB.

> **Repozytorium jest prywatne i musi takie zostać, dopóki zawiera opisy danych organizatora.** Danych organizatora nie wolno publicznie
> rozpowszechniać. Surowe dane nie są w repo (są w `.gitignore`).

## Spis treści

1. [Co narzędzie robi, a czego nie](#1-co-narzędzie-robi-a-czego-nie)
2. [Szybki start](#2-szybki-start)
3. [Jak używać interfejsu](#3-jak-używać-interfejsu)
4. [Metoda](#4-metoda)
5. [Metryki](#5-metryki)
6. [Walidacja jak jury i dobór progu](#6-walidacja-jak-jury-i-dobór-progu)
7. [Dodatki: domeny, wizerunki, planista, graf](#7-dodatki-domeny-wizerunki-planista-graf)
8. [Klucze API](#8-klucze-api-niepotrzebne-do-oceny)
9. [Ograniczenia](#9-ograniczenia)
10. [Struktura repozytorium i dokumentacja](#10-struktura-repozytorium-i-dokumentacja)
11. [Licencje i dane zewnętrzne](#11-licencje-i-dane-zewnętrzne)

## 1. Co narzędzie robi, a czego nie

**Robi:** dla nowego materiału (zrzut, HTML, HAR, reklama z Mety, tekst, adres) odpowiada, **do czego należy** i dlaczego:

| decyzja | znaczenie | kiedy |
|---|---|---|
| **znana kampania** | ten sam przekaz i te same ślady co materiał z galerii | wynik kampanii ≥ próg (strony 0,70, Meta 0,5) albo reguła dokładna (te same obrazy) |
| **znany operator, nowa kampania** | inna kampania na tej samej infrastrukturze (zestaw strony, schemat adresu, domeny, rejestracja) | wynik operatora ≥ 0,25 |
| **nowy wzorzec** | nic w galerii nie jest wystarczająco bliskie; materiału nie doklejamy | w pozostałych przypadkach |

Każda decyzja ma **trzy najsilniejsze powody** (wspólne ślady, kanały z wynikiem), wskazany materiał, który ją rozstrzygnął, i rysunek.

**Nie robi:** nie jest wykrywaczem fejków. Nie ocenia, czy pojedynczy materiał jest oszustwem. Ocena „oszustwo” pochodzi z galerii: jeśli
nowy materiał przypina się do kampanii, którą znamy jako oszustwo (przypadki NASK, twórcy z reklamami zdjętymi przez Metę), to jest
mocny sygnał, że należy do **tej samej kampanii fejków**. „Nowy wzorzec” znaczy tylko „nie znamy podobnego”, a nie „uczciwe”. Etykiety
„scam” i „podejrzany” przy twórcach z Mety pochodzą z usunięć Mety, nie z naszej oceny.

## 2. Szybki start

```bash
make install        # venv + zależności (ok. 2 min, ok. 1,3 GB z torchem)
make test           # testy (bez danych), 74 testy
make demo           # interfejs: http://localhost:8501
make docker-run     # to samo w kontenerze (model tekstu jest w obrazie, działa offline)
cd code && docker compose up --build    # aplikacja + Neo4j: zakładka grafu działa bez ręcznych kroków
```

| polecenie | co robi |
|---|---|
| `make smoke` | dwa podobne teksty przez CLI; drugi powinien dostać znaną kampanię |
| `make watch …` | planista: automatyczny skan skrzynki, listy adresów albo Meta Ad Library (sekcja 7) |
| `make eval` | pełna ewaluacja: N-LNSO na 80 światach syntetycznych i strumień po czasie na Mecie |
| `PYTHONPATH=src .venv/bin/python scripts/test_jak_jury_embsim.py` (z `code/`) | test jak jury, raport w `code/artifacts/jury/raport_embsim.md` |
| `PYTHONPATH=src .venv/bin/python scripts/metryki.py` | wszystkie metryki z sekcji 5, raport w `code/artifacts/metryki/metryki.md` |
| `PYTHONPATH=src .venv/bin/python scripts/prog_kampanii.py zbierz` i `… dobierz` | dobór progu kampanii po podmiotach (sekcja 6) |
| `python -m embsim.cli add <folder \| plik.jsonl \| --text "...">` | CLI bez interfejsu |

**Aplikacja z grafem jednym poleceniem:** `docker compose up --build` (z `code/`) stawia Neo4j, potem jednorazowo zasila graf
(indeks przypadków z `DATA`, domyślnie `../data/dane/do_udostępnienia`, schemat, NASK, syntetyka; ok. 1 min), na koniec aplikację na
http://localhost:8501 (przeglądarka bazy http://localhost:7474). Hasło bazy: `NEO4J_PASSWORD` z `code/.env` albo domyślne `fejki-demo`.
Porty zmienia się przez `APP_PORT`, `NEO4J_HTTP_PORT` i `NEO4J_BOLT_PORT`. Sprawdzone 22.11: graf ma 52 materiały (10 NASK + 42
syntetyki) i 27 kampanii, a aplikacja łączy się z bazą.

**Docker, sprawdzone 22.11 na commicie 47211f6:** obraz zbudowany z `code/Dockerfile`, kontener uruchomiony **bez sieci**
(`--network none`) z `-v data/dane/do_udostępnienia:/data:ro`. Galeria z `/data` ma 10 materiałów, 8 kampanii i 6 operatorów. Ocena
wsadowa folderu `data/testy_apki/A_przypadki_czesciowe`: **5/5 „Znana kampania” z właściwym materiałem** (47 i 48 z samego HAR, 1 i 3
z samego zrzutu reklamy, 61 z samej strony produktu). Interfejs startuje, `/_stcore/health` zwraca `ok`. Pierwsza budowa pobiera ok.
1,5 GB (torch CPU, zależności, model tekstu ok. 470 MB). Jeśli model tekstu i modele twarzy są już lokalnie w `code/models/` (pamięć
HF w `code/models/hf`), budowa bierze je stamtąd zamiast z sieci.

## 3. Jak używać interfejsu

**Pasek boczny: galeria znanych materiałów.** Budujesz ją z folderu przypadków (podfolder = jeden materiał: HTML, HAR, zrzuty) i z pliku
reklam Meta (JSONL). Zrzut bez tekstu przechodzi przez OCR (dobry wynik wymaga `tesseract-ocr-pol`; kontener go zawiera). Po wczytaniu
folderów grupy są liczone drugi raz na pełnej galerii, więc wynik nie zależy od kolejności przypadków (docs/WYNIKI.md §5a). Suwak
„Próg: znana kampania” zmienia próg od razu (domyślnie 0,70 dla stron).

**Zakładka „🔎 Analiza nowego materiału”:**
1. *Wejście:* pliki (zrzut, HTML, HAR, reklama Meta JSON/JSONL, `info.json`), tekst reklamy albo adres URL.
2. *Cechy materiału:* ile tekstu, domen, zestawów zasobów, schematów adresu, pikseli i śladów infrastruktury udało się wydobyć.
3. *Dopasowanie z przesłankami:* decyzja, wynik kampanii i operatora, pewność dowodu, trzy najsilniejsze powody, szczegóły każdego
   kandydata i przesłanki spoza wyniku (ta sama osoba, bardzo podobny obraz, ten sam płatnik).
4. *Sieć kampanii i operatorów:* rysunek (czerwona strzałka: znana kampania, pomarańczowa: ten sam operator, szara przerywana: za słabe).
- *Wiele materiałów naraz:* ZIP albo folder (podfolder = materiał); tabela decyzji i grupy.
- *Planista:* ten sam automatyczny skan co `make watch`, uruchamiany z interfejsu.

**Adres URL:** domyślnie pobieramy stronę (HTML, łańcuch przekierowań, adresy zasobów, obrazy; bez JavaScriptu, bez adresów prywatnych,
z limitem czasu). Gdy strona nie działa albo ukrywa treść przed botami, zostaje domena i schemat parametrów adresu. Odznacz „Pobierz
stronę spod adresu”, jeśli nie chcesz odwiedzać adresu.

**Zakładka „🧩 Klastry”:**
- *Galeria (offline):* operator → kampanie → materiały, karta operatora „co z tego wynika” i rysunek tylko z tego, co klaster skleja
  (czerwone ramki: ślady jednej kampanii, niebieskie: ślady łączące kampanie w operatora). Pospolite ślady są pominięte.
- *Graf Neo4j:* trzy widoki. **Twórcy (reklamy Meta):** karta twórcy z rysunkiem „dlaczego to jeden twórca” (strony sklejone płatnikiem,
  domeną, identycznym tekstem). **Sieci i kampanie (NASK, syntetyka):** wspólne ślady materiałów i pary z przesłankami. **Nowe materiały
  (add / scraper):** dla każdego dodanego materiału rysunek najbliższych materiałów pogrupowanych po twórcy, z wynikami i powodami na
  strzałkach i wspólnymi śladami (pospolite usługi, np. instagram.com, oznaczone jako niedowodzące).

**Zakładka „📐 Jak liczymy i wyniki”:** wzór, rozbicie wyniku ostatnio analizowanego materiału na kanały i zapisane wyniki testu jak jury.

## 4. Metoda

Każdy materiał zamieniamy na **kanały cech**. Podobieństwo to **jedno wyrażenie z wagami ustalonymi z góry, bez uczenia**
([docs/14_WZOR_PODOBIENSTWA.md](docs/14_WZOR_PODOBIENSTWA.md)). Jedyne liczby dobrane na danych z etykietami to **dwa progi**.

| kanał | co porównuje | skąd |
|---|---|---|
| `text` | embedding tekstu (MiniLM, wielojęzyczny), z korektą względem typowego podobieństwa w korpusie | tekst strony, OCR, treść reklamy |
| `text_lex` | TF-IDF n-gramów znaków (3–5) | j.w. |
| `kit` | prefiksy katalogów zasobów strony | HAR |
| `scheme` | zestaw nazw parametrów adresu | HAR, URL |
| `host` | domeny rejestrowalne, bez pospolitych usług (Google, Meta, CDN, czcionki) | HAR, HTML, URL |
| `pixel` | identyfikatory pikseli i tagów | HTML |
| `img` | odcisk SHA-256 obrazów strony (≥ 2 KB) | HAR, `*_files` |
| `infra` | serwer nazw, IP, rejestrator i godzina rejestracji, para NS Cloudflare | DNS i RDAP (sekcja 7) |

**Wzór (poziom kampanii):** `S̄` = średnia po kanałach policzonych (wagi 1); dowód `e` = udział kanałów, które dało się porównać;
`λ = min(1, e / e_ref)`; **`S = max(0, 1 − (1 − S̄) / λ)`** (mniej danych → potrzebny wyższy `S̄`). Kanały tekstowe: kosinus
wyśrodkowany medianą korpusu. Kanały śladów: `1 − exp(−Σ idf)` po wspólnych śladach, `idf = ln((N+1)/(df+0,5))`, więc ślad pospolity
prawie nic nie waży, a rzadki waży dużo.

**Poziom operatora:** tylko kanały śladów, miara „zawierania” (`I / min(W_a, W_b) · (1 − exp(−I))`), bez korekty o dowód.

**Reguła dokładna:** jeśli wszystkie obrazy zapytania są w jednym materiale galerii, a co najmniej jeden obraz należy do jednej
kampanii, to jest znana kampania niezależnie od progu (te same pliki obrazów to identyczna kreacja).

**Przesłanki poza wynikiem** (pokazywane, nie liczone): ta sama twarz, ta sama znana osoba, bardzo podobny obraz po zmianie rozmiaru
(dHash), ten sam płatnik, ta sama strona reklamodawcy, identyczny tekst.

**Profile progów:** `strony` (HTML, HAR, zrzuty) kampania 0,70, `meta` (reklamy) 0,5; operator 0,25. Profil zapisuje się w decyzji,
więc interfejs, CLI i scraper używają tych samych progów. Szczegóły: [docs/METODYKA.md](docs/METODYKA.md).

## 5. Metryki

Wszystkie liczby z tej sekcji odtwarza `scripts/metryki.py` (ok. 10 s, infra z pamięci podręcznej). Dane: **NASK-10** (nasz odczyt:
kampanie {1,2} i {48,61}, operator {1,2,3,48,61}, reszta osobno; nie są to etykiety organizatora) i **syntetyka v1** (42 materiały,
12 kampanii po 3, 6 operatorów, 6 negatywów; prawda z generatora, który piszemy sami). Próg kampanii 0,70, operatora 0,25.

**Jak czytać:**
- *trafność@k* i *MRR*: czy wśród k najbliższych (wg wyniku) jest materiał z tej samej kampanii; MRR = średnia z 1/pozycja pierwszego trafienia;
- *AUROC* i *AP*: jak dobrze sam wynik podobieństwa oddziela pary „ta sama kampania” od „różne” (1 = idealnie, 0,5 = losowo);
  AP jest wrażliwe na to, że par pozytywnych jest mało;
- *precyzja, czułość, F1*: z połączeń, które zrobiliśmy, ile jest dobrych; z tych, które powinny być, ile zrobiliśmy; ich średnia harmoniczna;
- *ARI, AMI, V-measure, B-cubed F1*: zgodność całego podziału na grupy z prawdą (1 = identyczny podział).

### 5.1. Wyszukiwanie najbliższego materiału (galeria = reszta zbioru)

| zbiór | poziom | zapytań z parą | trafność@1 | trafność@3 | trafność@5 | MRR |
|---|---|---|---|---|---|---|
| NASK | kampania | 4 | 1,000 | 1,000 | 1,000 | 1,000 |
| NASK | operator | 5 | 1,000 | 1,000 | 1,000 | 1,000 |
| syntetyka | kampania | 36 | 0,972 | 0,972 | 1,000 | 0,979 |
| syntetyka | operator | 36 | 1,000 | 1,000 | 1,000 | 1,000 |

### 5.2. Podobieństwo par

| zbiór | para | par (pozytywnych) | AUROC | AP | średni wynik: te same / różne | najlepsze F1 (próg) | F1 przy progu z konfiguracji (P / R) |
|---|---|---|---|---|---|---|---|
| NASK | ta sama kampania | 45 (2) | 1,000 | 1,000 | 0,851 / 0,117 | 1,000 (0,785) | 1,000 (1,000 / 1,000) |
| NASK | ten sam operator | 45 (10) | 0,833 | 0,767 | 0,434 / 0,006 | 0,824 (0,277) | 0,824 (1,000 / 0,700) |
| syntetyka | ta sama kampania | 861 (36) | 0,982 | 0,927 | 0,718 / 0,171 | 0,925 (0,715) | 0,805 (0,717 / 0,917) |
| syntetyka | ten sam operator | 861 (90) | 0,947 | 0,557 | 0,449 / 0,100 | 0,676 (0,442) | 0,676 (0,605 / 0,767) |

Na NASK najniższy wynik pary z tej samej kampanii (0,785) jest wyraźnie nad najwyższym wynikiem obcej pary (0,530). Na syntetyce
przedziały się stykają (0,333 kontra 0,713), stąd F1 par 0,805 przy 0,70. Grupowanie (5.3) wypada lepiej, bo łączy kampanie średnim
wiązaniem, a nie pojedynczą parą.

### 5.3. Grupowanie całej galerii (drugi przebieg, jak w interfejsie)

| zbiór | poziom | grup prawdziwych / przewidzianych | odtworzone dokładnie | precyzja par | czułość par | F1 par | ARI | AMI | V-measure | B-cubed F1 |
|---|---|---|---|---|---|---|---|---|---|---|
| NASK | kampania | 2 / 8 | 2 z 2 | 1,000 | 1,000 | 1,000 | 1,000 | 1,000 | 1,000 | 1,000 |
| NASK | operator | 1 / 6 | 1 z 1 | 1,000 | 1,000 | 1,000 | 1,000 | 1,000 | 1,000 | 1,000 |
| syntetyka | kampania | 12 / 18 | 11 z 12 | 0,971 | 0,944 | 0,958 | 0,956 | 0,956 | 0,986 | 0,972 |
| syntetyka | operator | 6 / 15 | 2 z 6 | 0,983 | 0,644 | 0,779 | 0,759 | 0,833 | 0,917 | 0,846 |

„Grup przewidzianych” liczy też materiały pojedyncze (negatywy i przypadki spoza kampanii). Na poziomie operatora syntetyka rozbija
operatorów (czułość 0,644): dwie kampanie jednego operatora nie zawsze dzielą rzadki ślad.

### 5.4. Decyzja „znana kampania” dla nowego materiału (próg 0,70; 95% bootstrap po podmiotach)

| układ | pytań | precyzja | czułość | F1 | swoistość (obce zostawione osobno) | zrównoważona trafność | fałszywe połączenia |
|---|---|---|---|---|---|---|---|
| jak test jury (A + C) | 30 | 1,000 [1,000; 1,000] | 0,933 [0,769; 1,000] | 0,966 [0,870; 1,000] | 1,000 | 0,967 | 0 |
| pełna galeria, zostaw-jeden | 52 | 0,951 [0,821; 1,000] | 0,975 [0,917; 1,000] | 0,963 [0,889; 1,000] | 0,833 | 0,904 | 2 |
| 105 losowych galerii NASK + syntetyka | 581 | 0,820 [0,663; 0,916] | 0,959 [0,906; 0,994] | 0,884 [0,779; 0,942] | 0,588 | 0,774 | 83 |

Układy opisuje sekcja 6. Losowe galerie są najtrudniejsze: zawierają materiały, których kampania jest poza galerią, a operator nie, oraz
wejścia niepełne (sam HTML, sam HAR).

### 5.5. Pozostałe pomiary

Pełne tabele z danymi, podziałem i ograniczeniami: [docs/WYNIKI.md](docs/WYNIKI.md) i [docs/POMIAR_RYGOR.md](docs/POMIAR_RYGOR.md).

| co mierzymy | na czym | wynik |
|---|---|---|
| grupowanie kampanii, wzór domyślny kontra pierwsza wersja | 80 światów syntetycznych, protokół N-LNSO (zagnieżdżony, po światach) | ARI 0,749 [0,730; 0,767] wobec 0,635 [0,610; 0,658] |
| doklejanie nowych wzorców do znanych kampanii (im mniej, tym lepiej) | j.w. | 0,148 [0,131; 0,166] wobec 0,462 [0,433; 0,491] |
| sam tekst odtwarza twórcę reklamy (TF-IDF znaków) | Meta, 3 570 tekstów, 2 162 twórców, podział po podmiotach z grafu | AUC 0,895, top-1 0,805 |
| przypisanie nowej reklamy do twórcy (tekst + leksyka + domena) | 4 481 najnowszych reklam z Mety, test po czasie | top-1 0,63 [0,55; 0,70], AUROC „znany vs nowy” 0,77 [0,72; 0,82] |
| ścieżka online od pustej galerii (próg 0,5) | 795 reklam Meta od 120 twórców, chronologicznie | precyzja 0,82 [0,74; 0,90], czułość 0,71 [0,64; 0,78], odrzucenie nowych 0,87 |
| czy sąsiad „zdjęty przez Metę” przewiduje zdjęcie reklamy | 9 622 reklamy Meta, etykieta zewnętrzna | AUROC 0,641; identyczny tekst na różnych stronach +0,43 ponad tło |
| kanał obrazu | 117 zrzutów urlscan, 10 przypadków NASK | AUC 0,73–0,83; wariant 48≈61 nie łączy się |

## 6. Walidacja jak jury i dobór progu

**Test jak jury** (`scripts/test_jak_jury_embsim.py`, kryteria z opisu wyzwania pkt 6): galeria z folderów, nowy materiał wgrany jako pliki.
A: każdy przypadek NASK ukryty po kolei; B: sam HTML, sam HAR, sam zrzut, ten sam materiał drugi raz; C: syntetyka jako zbiór ukryty
(nowe warianty, nowa kampania znanego operatora, 6 negatywów). Przy progu 0,70: **A 10/10, B 8/13 (dobra grupa 11/13), C 19/20**;
precyzja decyzji „znana kampania” 14/14, czułość 14/15, obce zostawione osobno 11/11, nowa kampania znanego operatora 4/4, każda
decyzja z przesłankami. Wyniki zapisane w `code/config/embsim/wyniki_jury.json` i widoczne w interfejsie.

**Dobór progu kampanii 0,70** (`scripts/prog_kampanii.py`, [docs/POMIAR_RYGOR.md](docs/POMIAR_RYGOR.md) §3a): podział po **podmiotach**
(operator syntetyki, sieć NASK jako jeden podmiot; 18 podmiotów), próg wybierany bez podmiotu i sprawdzany na nim. Rozkład wyniku zależy od
składu galerii, więc optima trzech układów się różnią: test jury 0,62, pełna galeria 0,685, losowe galerie 0,755. 0,70 ma najmniejszą
maksymalną stratę zrównoważonej trafności po trzech układach (0,067; 0,62 traci do 0,125). Koszt względem 0,62: przypadki 48 i 61 podane
jako sam HTML dostają „sieć” z właściwą grupą zamiast „kampanii”. Zysk: na pełnej galerii 2 zamiast 5 fałszywych połączeń.

## 7. Dodatki: domeny, wizerunki, planista, graf

**Metadane domen (kanał `infra`):** dla domen materiału bierzemy publiczne metadane z DNS i RDAP: serwer nazw, adres IP, rejestratora
i godzinę rejestracji, a także parę serwerów nazw Cloudflare, którą Cloudflare przydziela na konto. Dzięki temu łączymy strony na
różnych domenach z tej samej partii rejestracji albo z tego samego konta. Ślady wielkich dostawców (Cloudflare, AWS, popularne DNS
rejestratorów) pomijamy. Zapytania idą do resolwera DNS i rdap.org, nigdy do stron oszustów. Domyślnie (`EMBSIM_INFRA=cache`) używamy
tylko zapisanego pliku `code/config/embsim/infra_cache.json` bez sieci, więc wynik jest powtarzalny. `EMBSIM_INFRA=1` dopytuje sieć
o nowe domeny, a `python -m embsim.infra /ścieżka/do/przypadków` uzupełnia plik. Na NASK: przypadki 1 i 2 mają domeny
(`civicdaybook.live`, `acrosscommunities.live`) zarejestrowane w Dynadot w odstępie 2 minut, co niezależnie potwierdza kampanię {1,2}.

**Wizerunki znanych osób:** twarze z materiału porównujemy z małą bazą wzorców `code/config/embsim/znane_osoby.json`. Baza zawiera
6 osób, których nazwiska występują w materiałach NASK: Brzoska, Morawiecki, Olejnik, Glapiński, Lewandowski i Tusk. W pliku są tylko
osadzenia twarzy (po 128 liczb) i nazwiska, bez samych zdjęć. Interfejs pokazuje, kto jest na materiale. Dwa materiały z różnymi
zdjęciami tej samej osoby dostają przesłankę „znana osoba”, a do wyniku podobieństwa ona nie wchodzi. Osobę nazywamy tylko przy
kosinusie co najmniej 0,45 i z zapasem 0,05 nad drugą osobą. Na NASK rozpoznania zgadzają się z nazwiskami w tekstach stron (1: Brzoska
i Morawiecki, 3: Olejnik i Glapiński, 48: Morawiecki, 61: Tusk). Wyjątek to przypadek 10: wynik „Olejnik 0,56” bez jej nazwiska w
tekście, niepotwierdzony. Rozbudowa bazy: folder `osoby/<Imię Nazwisko>/*.jpg` (opcjonalnie `zrodla.json` z licencjami), potem
`python -m embsim.faces --known osoby`. Z każdego zdjęcia bierzemy twarz zgodną z resztą zdjęć danej osoby, a zdjęcia grupowe bez
zgodnej twarzy odrzucamy.

**Planista (automatyczny skan):** co N minut bierze nowe materiały, ocenia je względem galerii, dopisuje do niej i zapisuje alerty do
`code/artifacts/watch/alerty.csv`. Ten sam przebieg można uruchomić w interfejsie (zakładka analizy, sekcja „Planista”).

```bash
make watch INBOX=/ścieżka/do/skrzynki EVERY=60     # podfoldery przypadków i pliki JSONL z reklamami wrzucane do folderu
make watch URLS=adresy.txt                         # lista adresów, jeden przebieg
make watch KEYWORDS=code/config/meta_keywords.txt EVERY=60   # Meta Ad Library (wymaga META_ACCESS_TOKEN)
```

**Baza grafowa Neo4j** ([docs/13_BAZA_GRAFOWA.md](docs/13_BAZA_GRAFOWA.md)): reklamy Mety, strony reklamodawców, płatnicy, domeny i
twórcy (`Creator`, operator z Mety) oraz materiały NASK i syntetyki. Scraper (`graph/scrape.py add …`, `… watch …`) dodaje nowe
materiały z decyzją silnika, krawędziami `SIMILAR_TO` do najbliższych (wynik i powody) i wyjaśnieniem. Kontrakt decyzji rozdziela
kampanię, operatora i konto reklamowe, a zapis jest transakcyjny (`graph/decision.py`). Zakładka „Klastry” czyta bazę bezpośrednio.

## 8. Klucze API: niepotrzebne do oceny

Demonstrator, testy, `make watch` ze skrzynką lub adresami i obraz Dockera działają **bez żadnych kluczy** (model tekstu jest lokalny).
Plik `code/.env` (wzór: `code/.env.example`) jest potrzebny tylko do dodatków:

| zmienna | do czego | bez niej |
|---|---|---|
| `META_ACCESS_TOKEN` | wyszukiwanie w Meta Ad Library (planista, scraper) | reklamy Meta wczytuje się z pliku JSONL |
| `NEO4J_PASSWORD`, `NEO4J_URI` | zakładka grafu w Neo4j (`docker compose up --build`) | w compose domyślne hasło `fejki-demo`; bez bazy zakładka pokazuje ostrzeżenie, reszta działa |
| `URLSCAN_API_KEY`, `LLM_*`, `YOUTUBE_API_KEY` | tylko poprzedni silnik i eksperymenty | nieużywane w demonstratorze |

## 9. Ograniczenia

1. **Etykiet prawdziwych kampanii nie ma.** Liczby z syntetyki mierzą odzyskiwanie sygnału podłożonego przez nasz generator; NASK-10 to
   nasz odczyt, a wszystkie pozytywy NASK pochodzą z jednej sieci.
2. **Wynik zależy od składu galerii** (idf śladów i tło tekstu liczone są na galerii). Wspólna galeria NASK + syntetyka podnosi wszystkie
   wyniki o ok. 0,05. Próg 0,70 to kompromis po trzech układach, a nie gwarancja na zbiorze jury; dlatego jest suwakiem.
3. **Progi nie przenoszą się między źródłami:** strony 0,70, Meta ok. 0,5, syntetyka v2 0,95.
4. **Sam HAR** niesie głównie infrastrukturę, więc w sieci NASK nie odróżnia kampanii od operatora (wynik 0,98–1,0 do dowolnego materiału
   sieci); przypadek 14 jako sam HAR dokleja się z wynikiem ok. 0,88. HAR-y syntetyki to atrapy (same adresy).
5. **Sam zrzut reklamy** bez strony docelowej zwykle nie wystarcza do przypisania kampanii (wynik 0,23–0,38); działa, gdy zrzut jest
   identyczny z obrazem w galerii (reguła dokładna).
6. **Meta:** targetowanie psuje wynik i jest wyłączone; prawie identyczne, ale nie identyczne teksty (szablony katalogowe) dają fałszywe
   połączenia; pospolite domeny (np. instagram.com) nie są wycinane z kanału domen reklam Meta tak jak na stronach.
7. **Obrazy:** logotypów wewnątrz zrzutu nie wykrywamy (bliskie duplikaty obrazów tak); baza znanych osób ma 6 osób.
8. **OCR** bez języka polskiego jest słaby.
9. **Dodawanie po jednym:** legalne strony z pospolitymi zasobami trafiały do operatora oszustw; reguła rzadkiego śladu zmniejszyła to
   z 30 do 9 z 43 na syntetycznym zbiorze testowym (docs/WYNIKI.md §7a).

## 10. Struktura repozytorium i dokumentacja

| ścieżka | co tam jest |
|---|---|
| `code/src/embsim/` | metoda: cechy (`features.py`), wzór (`score.py`), galeria i decyzje (`api.py`), interfejs (`app.py`, `analyze.py`, `graph_view.py`), test jak jury (`jury.py`), domeny (`infra.py`), twarze (`faces.py`), obrazy (`imghash.py`), pobieranie stron (`fetch.py`), planista (`watch.py`), CLI (`cli.py`), ewaluacje (`cv.py`, `stream_eval.py`, `online_eval.py`, `threshold_stability.py`) |
| `code/graph/` | baza Neo4j: ładowanie (`load.py`), klastry do interfejsu (`clusters.py`), scraper (`scrape.py`), kontrakt decyzji (`decision.py`) |
| `code/scripts/` | test jak jury, metryki, dobór progu, walidacja na usunięciach Mety |
| `code/config/embsim/` | konfiguracje wzoru, próg demonstratora (`demo_calibration.json`), wyniki jury, pamięć domen, baza znanych osób |
| `code/tests/` | testy jednostkowe (`make test`) |
| `code/src/fejki/` | poprzedni silnik (tag `legacy-v1`), zachowany do porównań |
| `docs/archiwum/` | dokumentacja historyczna poprzedniego silnika (nie opisuje obecnej metody) |

| dokument | treść |
|---|---|
| [docs/METODYKA.md](docs/METODYKA.md) | przepływ, decyzje projektowe, zgodność z wymaganiami zadania |
| [docs/14_WZOR_PODOBIENSTWA.md](docs/14_WZOR_PODOBIENSTWA.md) | wzór podobieństwa krok po kroku, skąd każda liczba |
| [docs/WYNIKI.md](docs/WYNIKI.md) | wszystkie pomiary z danymi, podziałem, ograniczeniami i pochodzeniem danych |
| [docs/POMIAR_RYGOR.md](docs/POMIAR_RYGOR.md) | rygor pomiaru: wycieki, wybór zagnieżdżony, stabilność i dobór progu, ocena online |
| [docs/13_BAZA_GRAFOWA.md](docs/13_BAZA_GRAFOWA.md) | baza grafowa, scraper, kontrakt decyzji, instrukcje |
| [docs/15_FORMAT_KANALU_RUCHU.md](docs/15_FORMAT_KANALU_RUCHU.md) | format kanału ruchu sieciowego dla grafu |
| [docs/DEMO_FILMIK.md](docs/DEMO_FILMIK.md) | scenariusz filmu demonstracyjnego |

## 11. Licencje i dane zewnętrzne

Modele: `paraphrase-multilingual-MiniLM-L12-v2` (Apache-2.0), opcjonalnie `Qwen3-VL-Embedding-2B` (Apache-2.0). Neo4j Community (GPLv3,
osobny serwer). Dane Meta Ad Library: oficjalne API, warunki Mety. BuzzFeed-Webis (CC BY 4.0) użyto do eksperymentu pomocniczego.
Pochodzenie każdego zbioru: [docs/WYNIKI.md](docs/WYNIKI.md).

Modele twarzy: YuNet i SFace z OpenCV Zoo (Apache-2.0). Baza wizerunków znanych osób (`code/config/embsim/znane_osoby.json`) to
osadzenia twarzy policzone ze zdjęć z Wikimedia Commons. Samych zdjęć nie rozpowszechniamy. Źródła i licencje (adresy także w pliku
bazy, pole `źródła`):

| osoba | plik w Wikimedia Commons | licencja |
|---|---|---|
| Adam Glapiński | [Adam Glapiński.jpg](https://commons.wikimedia.org/wiki/File:Adam_Glapi%C5%84ski.jpg) | CC BY-SA 3.0 |
| Adam Glapiński | [Adam Glapiński.JPG](https://commons.wikimedia.org/wiki/File:Adam_Glapi%C5%84ski.JPG) | CC BY-SA 2.0 |
| Adam Glapiński | [Prof. Adam Glapinski, Nov 2015.jpg](https://commons.wikimedia.org/wiki/File:Prof._Adam_Glapinski,_Nov_2015.jpg) | CC BY-SA 2.0 |
| Donald Tusk | [Prime Minister Donald Tusk of Poland in the Oval Office in 2024 (cropped).jpg](https://commons.wikimedia.org/wiki/File:Prime_Minister_Donald_Tusk_of_Poland_in_the_Oval_Office_in_2024_(cropped).jpg) | Public domain |
| Donald Tusk | [Premier Donald Tusk KPRM.jpg](https://commons.wikimedia.org/wiki/File:Premier_Donald_Tusk_KPRM.jpg) | CC BY 3.0 pl |
| Mateusz Morawiecki | [Mateusz Morawiecki 2023.jpg](https://commons.wikimedia.org/wiki/File:Mateusz_Morawiecki_2023.jpg) | Public domain |
| Mateusz Morawiecki | [20230919 Mateusz Morawiecki election banner Medyków Ligota Katowice.jpg](https://commons.wikimedia.org/wiki/File:20230919_Mateusz_Morawiecki_election_banner_Medyk%C3%B3w_Ligota_Katowice.jpg) | CC BY-SA 4.0 |
| Mateusz Morawiecki | [20230919 Mateusz Morawiecki election banner Stawowa Street Katowice.jpg](https://commons.wikimedia.org/wiki/File:20230919_Mateusz_Morawiecki_election_banner_Stawowa_Street_Katowice.jpg) | CC BY-SA 4.0 |
| Monika Olejnik | [Monika Olejnik u prezydentowej.jpg](https://commons.wikimedia.org/wiki/File:Monika_Olejnik_u_prezydentowej.jpg) | GFDL 1.2 |
| Monika Olejnik | [Energa Camerimage Festiwal 2025 Toruń.jpg](https://commons.wikimedia.org/wiki/File:Energa_Camerimage_Festiwal_2025_Toru%C5%84.jpg) | CC BY-SA 4.0 |
| Monika Olejnik | [Monika Olejnik.JPG](https://commons.wikimedia.org/wiki/File:Monika_Olejnik.JPG) | CC BY-SA 2.0 |
| Monika Olejnik | [Monika.Olejnik.JPG](https://commons.wikimedia.org/wiki/File:Monika.Olejnik.JPG) | CC BY 3.0 |
| Rafał Brzoska | [Rafał Brzoska.png](https://commons.wikimedia.org/wiki/File:Rafa%C5%82_Brzoska.png) | CC0 |
| Rafał Brzoska | [Omenaa Mensah i Rafał Brzoska podczas gali Global Woman of Impact Award 2026.jpg](https://commons.wikimedia.org/wiki/File:Omenaa_Mensah_i_Rafa%C5%82_Brzoska_podczas_gali_Global_Woman_of_Impact_Award_2026.jpg) | CC BY 4.0 |
| Robert Lewandowski | [Robert Lewandowski (2025).jpg](https://commons.wikimedia.org/wiki/File:Robert_Lewandowski_(2025).jpg) | CC BY 4.0 |
| Robert Lewandowski | [Robert Lewandowski (2025).png](https://commons.wikimedia.org/wiki/File:Robert_Lewandowski_(2025).png) | CC BY 4.0 |
| Robert Lewandowski | [Robertlewandowskiatchicagofire.jpg](https://commons.wikimedia.org/wiki/File:Robertlewandowskiatchicagofire.jpg) | CC0 |
