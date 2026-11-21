# Kolekcjoner Fejków (HackNation x NASK)

Narzędzie dla analityka CERT, które z pojedynczych reklam składa kampanie oszukańcze. Dokumentacja całego projektu (zadanie, dane, architektura, plan i zadania): [../README.md](../README.md) i [../docs/](../docs/).

## Demonstrator (wyzwanie „Follow the Fake”)

Przyjmuje folder przypadku, zapis strony HTML, log HAR, zrzut ekranu, nagranie, `info.json`, adres URL albo tekst / nazwę produktu.
Wyciąga cechy (tekst, osoby, produkt, reklamodawca, identyfikatory reklam i pikseli, schemat adresów, przekierowania, obrazy,
szablon strony, opcjonalnie infrastrukturę domen), porównuje z wcześniejszymi materiałami, grupuje w **kampanie** (ten sam przekaz)
i **sieci** (wspólna infrastruktura, prawdopodobnie ten sam operator), a każde powiązanie uzasadnia listą przesłanek.
Stron oszustów nie odwiedza. Metodyka, testy, ograniczenia i licencje: [docs/METODYKA.md](docs/METODYKA.md).

**Lokalnie** (Python 3.11+, Tesseract i FFmpeg w systemie, np. `brew install tesseract tesseract-lang ffmpeg`):

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
export FEJKI_DATA="/ścieżka/do/do_udostępnienia"   # folder z podfolderami-przypadkami (zbiór organizatora)
fejki demo build            # indeks: artifacts/demo/index.json (opcja --infra: bierne DNS/RDAP/crt.sh, wymaga sieci)
fejki demo app              # interfejs: http://localhost:8501
fejki demo eval             # testy: pomiń-jeden i niepełne wejście
pytest tests/test_demo.py   # testy jednostkowe na sztucznych plikach
```

**Docker** (z polskim OCR):

```bash
docker build -t kolekcjoner-fejkow .
docker run --rm -p 8501:8501 -v "/ścieżka/do/do_udostępnienia:/data:ro" kolekcjoner-fejkow
```

Zbiór organizatora nie jest częścią repozytorium ani obrazu (zakaz publicznego rozpowszechniania); podaje się go przy uruchomieniu.
Sprawdzanie reklam w Meta Ad Library (opcjonalnie) wymaga tokenu `META_ACCESS_TOKEN` w `.env`; opis dostępu w metodyce.

Część badawcza (embeddingi, LEACE, eksperymenty na syntetyce) wymaga `pip install -e ".[research]"`.

**Dane w repozytorium są syntetyczne i służą wyłącznie celom badawczym.** Występują w nich tylko fikcyjne osoby, marki i domeny w zarezerwowanej strefie `.example`. Kontakty są placeholderami. Nie ma w nich działających numerów, linków ani realnych osób.

## Hipoteza i zakres twierdzeń

H1: liniowe usunięcie podprzestrzeni tematu z embeddingów (LEACE) przesuwa podobieństwo z tematu na szablon kampanii. Wynik na syntetyce dowodzi tylko, że metoda odzyskuje podłożony szablon, a nie że prawdziwe kampanie go mają. Nie twierdzimy, że graf kampanii jest nowy (to praca NASK), że temat zostaje usunięty (gwarancja jest tylko liniowa) ani że widzimy cały ekosystem reklam.

## Uruchomienie

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env            # opcjonalnie: tokeny; bez nich pracujemy offline

fejki synth --n-campaigns 20 --seed 1      # fixture'y do data/fixtures
fejki embed                                # embeddingi (BAAI/bge-m3, cache w data/emb)
fejki eval all --seed 1                    # E1 do E7, wyniki w artifacts/
fejki comments                             # warstwa komentarzy (syntetyczna)
fejki app                                  # demo Streamlit
pytest                                     # testy bez dostępu do sieci
```

Bez pobierania modelu ustaw `encoder.name: char-tfidf` w `config/default.yaml` (deterministyczny zamiennik offline).

## Polecenia

| Polecenie | Działanie |
|---|---|
| `fejki ingest jsonl PLIK` | wczytanie reklam z pliku JSONL |
| `fejki ingest meta` | Meta Ad Library (oficjalne API, wymaga `META_ACCESS_TOKEN`) |
| `fejki ingest cert` | Lista Ostrzeżeń CERT Polska v2 (snapshot) |
| `fejki synth` | generator kampanii syntetycznych, kontrole C1, wabiki, symulowana lista CERT |
| `fejki erase` / `fejki cluster` | LEACE i kontrole losowe; klastrowanie wybranego kanału |
| `fejki graph build` | karty kampanii, graf i społeczności Leiden |
| `fejki eval all` / `fejki eval one E3` | eksperymenty E1 do E7 |
| `fejki replay` | replay strumieniowy, bursty per region, lead time |
| `fejki comments` | E8 na komentarzach syntetycznych |

## Wyniki

Tabele, wykresy i konfiguracje (z seedem i hashem commita) trafiają do `artifacts/tables`, `artifacts/figures`, `artifacts/cards`, `artifacts/replay`. Raport zbiorczy: `artifacts/tables/REPORT.md`. Lead time liczony na symulowanej liście CERT jest oznaczony jako SYMULACJA.

## Prawo i etyka

Brak przetwarzania twarzy. Osoby publiczne identyfikujemy wyłącznie po wzmiance w tekście z zamkniętej listy. Dane z Meta tylko przez oficjalne API. Komentarze: tylko hash autora, brak łączenia kont. System priorytetyzuje kolejkę analityka i niczego nie wpisuje automatycznie.

Źródła: Lista Ostrzeżeń CERT Polska (hole.cert.pl), Meta Ad Library API.
