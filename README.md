# Kolekcjoner Fejków (Follow the Fake): HackNation × NASK

Narzędzie, które z pojedynczych podejrzanych reklam i stron wydobywa wspólne ślady, łączy je w kampanie i pokazuje, **dlaczego** materiały
zostały połączone. Wyzwanie zgłosił Ośrodek Badań nad Bezpieczeństwem Sztucznej Inteligencji NASK PIB.

> **Repozytorium jest prywatne i musi takie zostać, dopóki zawiera opisy danych organizatora.** Danych organizatora nie wolno publicznie
> rozpowszechniać. Surowe dane nie są w repo (są w `.gitignore`).

## Metoda w jednym akapicie

Każdy materiał (zrzut, HTML, ruch sieciowy HAR, reklama z Meta, tekst, adres) zamieniamy na kilka kanałów cech: **tekst** (embedding i
TF-IDF znaków) oraz **ślady** (domeny, zestaw zasobów strony, schemat parametrów adresu, piksele). Podobieństwo to **jedno wyrażenie
z wagami ustalonymi z góry, bez uczenia** ([docs/14_WZOR_PODOBIENSTWA.md](docs/14_WZOR_PODOBIENSTWA.md)). Nowy materiał trafia do jednej z
trzech decyzji: *znana kampania*, *znany operator, nowa kampania* albo *nowy wzorzec* (nie doklejamy). Każdą decyzję uzasadniają trzy
najsilniejsze powody. Szczegóły: [docs/METODYKA.md](docs/METODYKA.md).

## Uruchomienie

```bash
make install        # venv + zależności (ok. 2 min, ok. 1,3 GB z torchem)
make test           # testy (bez danych)
make demo           # interfejs: http://localhost:8501
make docker-run     # to samo w kontenerze (model tekstu jest w obrazie, działa offline)
cd code && docker compose up --build    # aplikacja + Neo4j: zakładka grafu działa bez ręcznych kroków
```

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

Galerię znanych materiałów buduje się w pasku bocznym interfejsu z folderu przypadków (HTML, HAR, zrzuty) i z pliku reklam Meta (JSONL).
Zrzut bez tekstu przechodzi przez OCR (do dobrego wyniku potrzebny jest język polski `tesseract-ocr-pol`; kontener go zawiera).
CLI bez interfejsu: `python -m embsim.cli add <folder | plik.jsonl | --text "...">`.

Po wczytaniu folderów grupy są liczone drugi raz na pełnej galerii, więc wynik nie zależy od kolejności przypadków (docs/WYNIKI.md §5a).

**Adres URL:** w polu adresu w interfejsie domyślnie pobieramy stronę (HTML, łańcuch przekierowań, adresy zasobów, obrazy; bez
JavaScriptu, bez adresów prywatnych, z limitem czasu). Gdy strona nie działa albo ukrywa treść przed botami, zostaje domena i schemat
parametrów adresu. Odznacz „Pobierz stronę spod adresu”, jeśli nie chcesz odwiedzać adresu.

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

### Klucze API: niepotrzebne do oceny

Demonstrator, testy, `make watch` ze skrzynką lub adresami i obraz Dockera działają **bez żadnych kluczy** (model tekstu jest lokalny).
Plik `code/.env` (wzór: `code/.env.example`) jest potrzebny tylko do dodatków:

| zmienna | do czego | bez niej |
|---|---|---|
| `META_ACCESS_TOKEN` | wyszukiwanie w Meta Ad Library (planista, scraper) | reklamy Meta wczytuje się z pliku JSONL |
| `NEO4J_PASSWORD`, `NEO4J_URI` | zakładka grafu w Neo4j (`docker compose up --build`) | w compose domyślne hasło `fejki-demo`; bez bazy zakładka pokazuje ostrzeżenie, reszta działa |
| `URLSCAN_API_KEY`, `LLM_*`, `YOUTUBE_API_KEY` | tylko poprzedni silnik i eksperymenty | nieużywane w demonstratorze |

## Wyniki (uczciwie)

Pełna tabela z danymi, podziałem i ograniczeniami: [docs/WYNIKI.md](docs/WYNIKI.md). Skrót:

| co mierzymy | na czym | wynik |
|---|---|---|
| grupowanie kampanii, wzór domyślny kontra pierwsza wersja | 80 światów syntetycznych, protokół N-LNSO | ARI 0,749 [0,730; 0,767] wobec 0,635 [0,610; 0,658] |
| doklejanie nowych wzorców do znanych kampanii (im mniej, tym lepiej) | j.w. | 0,148 [0,131; 0,166] wobec 0,462 [0,433; 0,491] |
| przypisanie nowej reklamy do twórcy (tekst + leksyka + domena) | 4 481 najnowszych reklam z Mety, test po czasie, reklamy z treścią | top-1 0,63 [0,55; 0,70], AUROC „znany vs nowy” 0,77 [0,72; 0,82] |
| kanał obrazu | 117 zrzutów urlscan, 10 przypadków NASK | AUC 0,73–0,83; wariant 48≈61 nie łączy się |

**Ograniczenia, które znamy:** (1) etykiet prawdziwych kampanii nie ma, a liczby z syntetyki mierzą odzyskiwanie sygnału podłożonego przez
generator; (2) progi pochodzą z kalibracji na syntetyce, na prawdziwych danych niesprawdzone; (3) targetowanie reklam psuje wynik na Mecie
(domena pomaga) i jest wyłączone, a formułę śladów trzeba poprawić; próg z syntetyki v2 (0,95) nie przenosi się: na stronach demonstrator używa 0,70 (dobór po podmiotach, docs/POMIAR_RYGOR.md §3a), na Mecie optimum ok. 0,5 (suwak w interfejsie); (4) twarze porównujemy tylko między materiałami (bez ustalania, kim są) i jako przesłankę poza wynikiem, logotypów wewnątrz zrzutu nie wykrywamy (bliskie duplikaty obrazów tak); (5) OCR bez języka
polskiego jest słaby; (6) przy dodawaniu po jednym legalne strony z pospolitymi zasobami trafiały do operatora oszustw; reguła rzadkiego śladu zmniejszyła to z 30 do 9 z 43 na syntetycznym zbiorze testowym, ale limit jest bezwzględny i nie sprawdzony na dużej galerii ani na prawdziwych danych (docs/WYNIKI.md, §7a).

## Struktura

- `code/src/embsim/`: metoda (cechy, wzór, galeria, interfejs `app.py`, ewaluacja `cv.py` i `stream_eval.py`)
- `code/graph/`: baza grafowa Neo4j (twórca jako węzeł, scraper `scrape.py`), opis w [docs/13_BAZA_GRAFOWA.md](docs/13_BAZA_GRAFOWA.md)
- `code/src/fejki/`: poprzedni silnik (tag `legacy-v1`), zachowany do porównań
- `docs/archiwum/`: dokumentacja historyczna poprzedniego silnika (nie opisuje obecnej metody)
- `docs/15_FORMAT_KANALU_RUCHU.md`: format kanału ruchu sieciowego dla grafu

## Licencje i dane zewnętrzne

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

