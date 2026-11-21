# 03. Architektura kodu

Pakiet Python `fejki` w `code/src/fejki/`. Dwie części:
- **demonstrator** (`demo/`, `app/demo_app.py`, `infra/`): to, co pokazujemy i co oceniają;
- **część badawcza** (`process/`, `embed/`, `analyze/`, `eval/`, `synth/`, `ingest/`): pipeline na danych syntetycznych,
  LEACE, eksperymenty E1–E8 (wyniki: [code/docs/PROGRESS.md](../code/docs/PROGRESS.md)). Wymaga `pip install -e ".[research]"`.

Metodyka (co liczymy i dlaczego): [code/docs/METODYKA.md](../code/docs/METODYKA.md).

## Przepływ danych demonstratora

```
wejście (folder przypadku | pliki z formularza | URL | tekst)
   │
   ▼
demo/material.py  build_material()  ──►  Material (pydantic): tytuły, tekst, OCR, słowa kluczowe, tematyka, osoby,
   │   parse_html, parse_har,             produkty, reklamodawcy, domeny docelowe, usługi zewnętrzne, przekierowania,
   │   url_features, phash, _ocr,         wzorce ścieżek, katalogi zestawów, schematy parametrów, ad_id, piksele,
   │   video_frames, find_persons         trackery, konta, kontakty, klasy HTML, pHash obrazów, cloaking, braki
   ▼
demo/store.py  build() / save() / load()  ──►  Index (artifacts/demo/index.json) [+ infra: dane DNS/RDAP/crt.sh]
   │
   ▼
demo/similar.py
   evidence(a, b)  →  lista Evidence(kod, kanał, waga, opis)
   combine()       →  noisy-OR w kanale, potem między kanałami  →  wynik pary 0–1
   relation()      →  duplikat | wariant tego samego przekazu | wspólna infrastruktura / operator | podobieństwo treści
   campaigns()     →  składowe spójne: poziom „kampania” (duplikat/wariant) i „sieć” (wszystkie krawędzie ≥ próg)
   match(new)      →  decyzja dla nowego materiału + ranking kampanii z przesłankami
   │
   ▼
app/demo_app.py (Streamlit): Analiza nowego materiału · Kampanie i sieci · Graf powiązań · Materiały · Metodyka i testy
demo/evaluate.py: leave_one_out(), partial_inputs()  (CLI: fejki demo eval)
```

## Moduły demonstratora

| Plik | Odpowiada za | Najważniejsze funkcje |
|---|---|---|
| `demo/material.py` | ekstrakcja cech z dowolnego wejścia | `build_material`, `material_from_folder`, `material_from_inputs`, `parse_html`, `parse_har`, `url_features`, `phash`, `find_persons`, `advertisers`, `topics` |
| `demo/similar.py` | dowody, wynik, relacje, grupowanie, dopasowanie | `W` (wagi), `TextSpace` (TF-IDF), `evidence`, `combine`, `relation`, `all_pairs`, `campaigns`, `match` |
| `demo/store.py` | indeks na dysku, zbieranie infrastruktury | `build`, `save`, `load`, `case_dirs`, `collect_infra`, `infra_records` |
| `demo/evaluate.py` | testy zachowania bez etykiet | `leave_one_out`, `partial_inputs` |
| `app/demo_app.py` | interfejs | zakładki, `graph_html` (pyvis), `show_material` |
| `infra/collect.py` | bierne dane domeny: DNS, ASN (Team Cymru), RDAP, crt.sh; cache w `data/raw/infra/` | `collect`, `collect_cached`, `url_shape` |
| `infra/link.py` | reguły łączenia domen z uzasadnieniem | `evidence`, `score`, `link` |
| `config/osoby.txt` | baza osób publicznych (format w nagłówku pliku) | |
| `cli.py` | polecenia `fejki …` | `demo build|eval|app`, `infra collect|link`, część badawcza |

## Polecenia

| Polecenie | Działanie |
|---|---|
| `fejki demo build [FOLDER] [--no-ocr] [--infra]` | buduje indeks z folderu przypadków (domyślnie `FEJKI_DATA` / `../data/dane/do_udostępnienia`) |
| `fejki demo eval [--thr 0.7] [--no-partial]` | test pomiń-jeden i test niepełnego wejścia; CSV w `artifacts/demo/` |
| `fejki demo app [--port 8501]` | interfejs Streamlit |
| `fejki infra collect PLIK` / `fejki infra link PLIK` | infrastruktura dla adresów z pliku tekstowego |
| `pytest` | wszystkie testy (bez sieci, bez danych organizatora) |

## Jak dodać nowy kanał (przykład: hash favicony)

1. **Cecha**: dodaj pole do `Material` (`demo/material.py`), np. `favicon_hashes: list[str]`, i wypełnij je w `build_material`
   (np. z odpowiedzi w HAR albo z pliku w `_files/`).
2. **Dowód**: w `evidence()` (`demo/similar.py`) dodaj regułę, np.
   `for h in set(a.favicon_hashes) & set(b.favicon_hashes): add("shared_favicon", W["shared_favicon"], f"ta sama favicona ({h[:8]})")`.
3. **Waga i kanał**: dopisz `"shared_favicon": 0.7` do `W` i `"shared_favicon": "obraz"` do `CHANNELS`. Jeśli to ślad techniczny
   (nie treść), dopisz kod do zbioru `tech` w `relation()`.
4. **Widok**: pokaż cechę w `show_material()` (`app/demo_app.py`).
5. **Test**: sztuczny przypadek w `tests/test_demo.py` (wzór: `_case`) sprawdzający, że dowód powstaje i ma sensowny opis.
6. **Dokumentacja**: dopisz kanał w `code/docs/METODYKA.md` (pkt 2 i tabela wag).

## Ważne szczegóły implementacji

- **Pospolite cechy tracą wagę**: `_rarity(df) = 2/df` dla cech występujących w więcej niż 2 materiałach (osoby, usługi,
  katalogi, tematyka).
- **Osoby** z limitem 0,5 na kanał, żeby same nazwiska nie sklejały kampanii.
- **Hosty masowe** (Google, Facebook, CDN-y, jsdelivr, unsplash…) są pomijane: lista `COMMON_HOSTS` w `material.py`.
- **Schemat parametrów** liczony tylko gdy niesie informację (losowe wartości o stałej długości albo nietypowe klucze);
  klucze-hashe (losowe na każdej stronie) i `fbclid/gclid/access_token` pomijane.
- **Cache Streamlit**: lista par liczona raz na zestaw materiałów; po zmianie kodu w `demo/` trzeba zrestartować serwer
  (Streamlit nie przeładowuje importowanych modułów).
- **Wydajność**: O(n²) par; przy 10 przypadkach ~1 s, budowa indeksu z OCR ~30 s (najwolniejszy przypadek 14, 361 MB).
  Przy setkach materiałów potrzebne blokowanie kandydatów (zadanie C4).
