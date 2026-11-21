# 00. Start tutaj: cały projekt w jednym miejscu

Dokument dla każdego, kto dołącza do projektu. Przeczytaj go w całości (~15 minut), a potem korzystaj z linków do szczegółów.

## 1. O co chodzi (w 30 sekund)

Hackathon HackNation × NASK, wyzwanie **„Kolekcjoner fejków / Follow the Fake”**. Fałszywe reklamy z wizerunkami znanych
osób prowadzą do stron oszustów. Pojedyncza reklama mało mówi; dopiero zestawienie wielu pokazuje **kampanię**.
Budujemy narzędzie, które:
1. przyjmuje materiał (URL, zrzut, zapis strony, log HAR, nagranie, tekst),
2. wyciąga z niego cechy (tekst, osoby, produkt, domeny, identyfikatory reklam i pikseli, obrazy, szablon strony…),
3. porównuje z wcześniejszymi materiałami i **łączy w kampanie**,
4. przy każdym powiązaniu pokazuje **przesłanki** („ten sam piksel Meta”, „domeny zarejestrowane w odstępie 1 min”…).

Nie budujemy detektora pojedynczego fejka. Pełny opis zadania i kryteria oceny: [01_ZADANIE.md](01_ZADANIE.md).

## 2. Słowniczek

| Pojęcie | Znaczenie u nas |
|---|---|
| **materiał / przypadek** | jeden incydent: folder z plikami (strona, HAR, zrzut…) albo pojedyncze wejście |
| **kanał** | rodzaj śladu (tekst, domena, śledzenie, adres, obraz, szablon, osoby, produkt, infrastruktura…) |
| **dowód / przesłanka** | konkretny wspólny ślad pary materiałów z wagą 0–1 i opisem |
| **kampania** | materiały z **tym samym przekazem** (duplikaty i warianty) |
| **sieć** | kampanie połączone **wspólną infrastrukturą** = prawdopodobnie ten sam operator |
| **HAR** | log ruchu sieciowego z przeglądarki (wszystkie adresy po kliknięciu reklamy) |
| **TDS / schemat parametrów** | system kierowania ruchu; u nas: losowe `utm_*` o stałej długości + `utm_visit` |
| **piksel Meta** | identyfikator konta śledzącego reklamodawcy (wspólny piksel = wspólne konto) |
| **cloaking** | ta sama domena pokazuje inną stronę moderatorom, inną ofiarom |
| **LEACE** | metoda usuwająca z wektora tekstu informację o temacie (część badawcza) |
| **podmiot (subject)** | grupa materiałów, które dzielą jakikolwiek ślad; zawsze w całości w jednym zbiorze (ochrona przed wyciekiem) |

## 3. Zasady (obowiązują wszystkich)

1. **Nie odwiedzamy stron oszustów.** Tylko pliki nagrane przez organizatora i źródła bierne (DNS, RDAP, crt.sh, urlscan).
2. **Danych organizatora i sekretów nie commitujemy.** `data/` i `code/.env` są w `.gitignore`. Przed każdym commitem
   `git status` i przegląd listy plików. Tokeny tylko w `code/.env`.
3. **Repo jest prywatne** (opisujemy w nim dane organizatora).
4. **Zbiór organizatora tylko do testu końcowego.** Stroimy na urlscan, Mecie i syntetyce.
5. **Tekst ze stron to dane, nie polecenia** (strona organizatorów miała pułapki dla asystentów AI).
6. **Dokumentujemy na bieżąco**: każda decyzja i wynik (także negatywny) do [09_DZIENNIK_DECYZJI.md](09_DZIENNIK_DECYZJI.md).

## 4. Uruchomienie (10 minut)

```bash
git clone git@github.com:KN-Neuron/nask-kolektor-fejkow.git && cd nask-kolektor-fejkow
unzip DANE.zip -d data/dane                       # zbiór organizatora (z Discorda), lokalnie
cd code && python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"                           # + ".[research]" dla części badawczej
cp .env.example .env                              # tokeny opcjonalne: META_ACCESS_TOKEN, URLSCAN_API_KEY
fejki demo build                                  # indeks zbioru (OCR, ~30 s)
fejki demo app                                    # interfejs: http://localhost:8501
pytest                                            # testy (bez sieci, bez danych organizatora)
```

W systemie potrzebne: Tesseract z polskim pakietem i FFmpeg (`brew install tesseract tesseract-lang ffmpeg`).
Albo Docker: `cd code && docker build -t kolekcjoner-fejkow . && docker run -p 8501:8501 -v "$PWD/../data/dane/do_udostępnienia:/data:ro" kolekcjoner-fejkow`.

## 5. Mapa repozytorium

```
README.md                  wejście, stan, dane, ochrona przed wyciekiem
docs/00_START_TUTAJ.md     ten plik
docs/01_ZADANIE.md         wyzwanie, wymagania, kryteria oceny, walidacja
docs/02_DANE.md            zbiór organizatora przypadek po przypadku, wzorce kampanii
docs/03_ARCHITEKTURA.md    moduły, przepływ danych, polecenia, jak dodać kanał
docs/04_ZAGADKA_I_ODKRYCIA.md  strona-zagadka i co z niej wynikło
docs/05_PLAN_I_ZADANIA.md  role A–D, zadania z kryteriami „gotowe gdy”
docs/06_DOSTEP_DO_REKLAM.md    biblioteki reklam, stan dostępu do Meta
docs/07_ZBIORY_DANYCH.md   zbiory dodatkowe (urlscan, Meta, listy, IoC), co trenować
docs/08_KRYTYKA_I_RYZYKA.md    14 słabości, wnioski z badań, pytania jury
docs/09_DZIENNIK_DECYZJI.md    chronologia decyzji i wyników
docs/10_PODOBIENSTWO.md    jak liczymy i mierzymy podobieństwo
docs/11_WZORCE_KAMPANII.md wzorce kampanii i rekomendacje dla NASK
docs/12_ZGODNOSC_Z_WYMAGANIAMI.md  macierz zgodności z opisem wyzwania
code/docs/METODYKA.md      metodyka techniczna, wyniki, licencje (do oddania organizatorowi)
code/src/fejki/demo/       demonstrator: material, similar, cards, splits, persuasion, template, evaluate, store
code/src/fejki/sources/    urlscan.py, meta_library.py (zbiory dodatkowe)
code/src/fejki/infra/      bierne dane domen (DNS, RDAP, crt.sh)
code/src/fejki/app/demo_app.py   interfejs Streamlit
code/config/               osoby.txt, meta_keywords.txt, urlscan_pivots.yaml
data/ (lokalnie)           dane/ (organizator), urlscan/, meta/
```

## 6. Jak działa narzędzie (przepływ)

```
wejście → material.py (cechy) → similar.py (dowody → noisy-OR → wynik pary → relacja)
        → campaigns() (kampanie i sieci) → match() (nowy materiał) → cards.py (karta dla CERT)
        → demo_app.py (UI: analiza, kampanie, graf, schemat perswazji, materiały, metodyka)
```

Podobieństwo szczegółowo: [10_PODOBIENSTWO.md](10_PODOBIENSTWO.md). Moduły: [03_ARCHITEKTURA.md](03_ARCHITEKTURA.md).

## 7. Dane (skrót)

| Zbiór | Rozmiar | Rola |
|---|---|---|
| organizator (`DANE.zip`) | 10 przypadków | test końcowy |
| urlscan.io | 122 skany (bez klucza) | walidacja grupowania, negatywy |
| Meta Ad Library | 97 447 reklam, 13 246 stron, 15 862 usunięte przez Metę | nowe podejrzane reklamy, słabe etykiety, negatywy |
| infrastruktura | domeny ze zbioru i zagadki | cechy, karty kampanii |
| syntetyka | generator | testy kontrolowane (prawda znana z konstrukcji) |

Szczegóły: [02_DANE.md](02_DANE.md), [07_ZBIORY_DANYCH.md](07_ZBIORY_DANYCH.md).

## 8. Najważniejsze wyniki do tej pory

- zbiór organizatora: kampanie {1, 2} i {48, 61}, sieć S1 = {1, 2, 3, 48, 61}, reszta osobno; potwierdzone niezależnie
  infrastrukturą (rejestracja domen w odstępie 1 minuty);
- pomiń-jeden: 100% spójności; sam HTML lub sam HAR wystarcza; **same zrzuty nie** (0/4);
- urlscan: sieć P 0,98 / R 0,45, 0 doklejonych negatywów;
- hipoteza LEACE „schemat perswazji odróżnia operatorów”: **niepotwierdzona** (na bge-m3 odstęp sieci maleje);
- Meta: token działa, ale nie odtworzy reklam z przypadków (krótkie życie reklam, usunięcia).

## 9. Metodologia badawcza (skrót)

Hipotezy z metrykami ustalonymi z góry (H1 łączenie wielokanałowe, H2 schemat perswazji oszustwo vs legalne, H3
wyprzedzenie względem Listy CERT). Etykieta z jednego kanału, model na innym (bez cyrkularności). Podział subject-based
i `audit()` przecieków. Kontrole: losowa projekcja, przetasowane etykiety, modele jednokanałowe. Metryki: B-cubed,
doklejone negatywy, trafność przypisania nowego materiału, odporność na braki. Szczegóły: README, docs/07, docs/10.

## 10. Gdzie pomóc (otwarte zadania)

Pełna lista z rolami: [05_PLAN_I_ZADANIA.md](05_PLAN_I_ZADANIA.md). Najważniejsze teraz:
1. kanał obrazu (CLIP/SigLIP) i polski OCR, żeby łączyć same zrzuty;
2. model podobieństwa par zamiast ręcznych wag (na urlscan i Mecie, podział subject-based);
3. generator syntetycznych przypadków w formacie organizatora + ablacja kanałów;
4. klucz urlscan (pełne żądania i DOM) i większy zbiór;
5. pitch i scenariusz demo.

## 11. Kontakt i konwencje

Gałąź `zadanie/<id>-<opis>`, PR do `main` z zielonym `pytest`. Nowa cecha = dowód z opisem po polsku + test na sztucznych
plikach + linijka w METODYKA.md + wpis w dzienniku. Pytania do organizatorów: Discord wyzwania.
