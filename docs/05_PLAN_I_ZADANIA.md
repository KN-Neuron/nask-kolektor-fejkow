# 05. Plan i zadania (3–4 osoby)

Cel: wygrać według kryteriów z opisu wyzwania (30% grupowanie, 30% cechy i źródła, 15% demo end-to-end,
15% interpretowalność, 10% wdrażalność) i wypaść dobrze na **ukrytym zbiorze testowym** (nowe warianty znanych kampanii
+ inne kampanie, które **nie** powinny być doklejane).

Termin oddania: **do potwierdzenia na Discordzie** (zadanie D0). Etapy poniżej są względne.

## Punkt startowy (co już działa)

- demonstrator end-to-end (Streamlit), wszystkie typy wejścia, Docker z polskim OCR;
- kanały: tekst (TF-IDF), osoby (nazwiska), produkt, reklamodawca (OCR), śledzenie (`ad_id`, piksele, Google Ads, `acc=`),
  adres (schemat TDS, wzorce ścieżek, katalogi zestawów, usługi zewnętrzne, przekierowania), domena, obraz (pHash),
  szablon (klasy HTML), cloaking, tematyka, infrastruktura (opcjonalnie);
- grupowanie na dwóch poziomach (kampania / sieć), dopasowanie nowego materiału z przesłankami;
- karty kampanii (okno obserwacji, domeny do weryfikacji, wiek domen), infrastruktura dla domen zbioru;
- 31 testów jednostkowych, test pomiń-jeden 100% spójności.

**Najważniejsze luki** (w kolejności wpływu na ocenę):
1. brak etykiet referencyjnych i testu „czy obce nie są doklejane” na trudnych przypadkach → nie wiemy, jak wypadniemy na ukrytym zbiorze;
2. same zrzuty ekranu nie łączą się z niczym (0/4) → słaby kanał wizualny (brak CLIP, logotypów, słaby OCR);
3. nagrania: tylko OCR klatek, brak transkrypcji mowy (wskazówka „SPEECHBRAIN” z zagadki);
4. brak tokenu Meta i schedulera (punkty dodatkowe, plus połączenie przypadku 5);
5. favicony, skrypty i trackery z HAR: organizatorzy wprost je wymieniają, a mamy je już nagrane (zero kontaktu ze stronami);
6. raport/karta kampanii i dokument „wzorce kampanii” dla NASK (pkt 10 opisu).

## Role

| Rola | Osoba | Obszar | Główne pliki |
|---|---|---|---|
| **A. Dane i ewaluacja** | _do przypisania_ | etykiety, testy na „ukrytym” zbiorze, kalibracja progów i wag | `data/etykiety.yaml`, `code/src/fejki/demo/evaluate.py`, `code/tests/` |
| **B. Obraz i multimedia** | _do przypisania_ | OCR, CLIP/SigLIP, logotypy, transkrypcja audio, (opcjonalnie) twarze | `demo/material.py` (obrazy, wideo), nowy `demo/vision.py`, `demo/audio.py` |
| **C. Treść i infrastruktura** | _do przypisania_ | embeddingi tekstu, narracje, HAR: favicony/skrypty/trackery, infrastruktura domen, skalowanie | `demo/similar.py`, `demo/material.py` (HAR), `infra/` |
| **D. Produkt, Meta, pitch** | _do przypisania_ (lider) | UI, raporty, Meta Ad Library + scheduler, Docker, dokumentacja, prezentacja | `app/demo_app.py`, `ingest/meta_api.py`, nowy `demo/scheduler.py`, `docs/` |

**Wariant 3 osoby:** rolę D bierze lider razem z A (A+D), a B i C bez zmian. Zadania P2 z D odpadają jako pierwsze.

## Zasady wspólne

- gałąź na zadanie: `zadanie/<id>-<opis>`, PR do `main`, `pytest` zielony, krótki opis „co i jak sprawdzone”;
- każda nowa cecha = dowód z **opisem po polsku** w `evidence()` + test na sztucznych plikach + linijka w METODYKA.md;
- nie commitujemy danych organizatora ani sekretów (patrz README); nie odwiedzamy stron oszustów;
- po każdej zmianie wag/progów: `fejki demo build && fejki demo eval` i wynik do opisu PR;
- konflikty w `material.py` / `similar.py`: nowe kanały dopisujemy w osobnych funkcjach (`_vision_evidence`, `_har_evidence`),
  a w `evidence()` tylko jedno wywołanie, żeby nie edytować tych samych linii.

---

## Etap 1: fundamenty (pierwsze godziny, P0)

### A1. Etykiety referencyjne zbioru (P0, ~1,5 h) — A
- Spisać `data/etykiety.yaml`: dla każdego przypadku kampanię i sieć wg **naszego odczytu** z uzasadnieniem (bez kopiowania
  treści stron). Start: K1={1,2}, K2={48,61}, S1={1,2,3,48,61}; reszta osobno. Zaznaczyć niepewności (np. czy 3 to osobna
  kampania, czy wariant K1).
- Dopisać do `evaluate.py` metryki względem etykiet: B-cubed precision/recall/F1 dla kampanii i sieci, liczba fałszywych
  połączeń (obce doklejone).
- **Gotowe gdy:** `fejki demo eval` wypisuje B-cubed i fałszywe połączenia względem `etykiety.yaml`.

### A2. Test „obce nie są doklejane” (P0, ~1,5 h) — A
- Zbudować trudne negatywy **bez danych organizatora**: sztuczne przypadki z tą samą osobą publiczną, tą samą tematyką,
  tym samym CDN-em / Cloudflare, popularnym szablonem (WordPress), ale innym operatorem. Plus „rozbite” warianty: ta sama
  strona z inną domeną, bez HAR, tylko zrzut.
- Generator w `code/tests/fixtures_demo.py` (rozszerzenie `_case` z `test_demo.py`).
- **Gotowe gdy:** test pokazuje, że żaden negatyw nie przekracza progu 0,7; jeśli przekracza, zgłoszenie do C/B z przykładem.

### A3. Próba generalna na „nowym zbiorze” (P0, ~1 h) — A
- Symulacja oceny: podziel zbiór (np. 1, 48 jako „ukryte”), zbuduj indeks z reszty, wczytaj „ukryte” przez UI („Analiza
  nowego materiału” → folder) i przez CLI. Zmierz czas, spisz każdy problem.
- Dodać do CLI `fejki demo match <FOLDER>`: dopasowuje wszystkie podfoldery jako nowe i zapisuje CSV z decyzją i przesłankami
  (to będziemy uruchamiać na ukrytym zbiorze).
- **Gotowe gdy:** jedna komenda daje CSV „przypadek → decyzja → kampania → przesłanki” dla folderu z wieloma przypadkami.

### B1. Polski OCR lokalnie i lepszy odczyt zrzutów (P0, ~1 h) — B
- Lokalnie: `brew install tesseract-lang` (albo pobrać `pol.traineddata`); sprawdzić, że `_ocr()` używa `pol`.
- Przetwarzanie obrazu przed OCR (skala 2×, binaryzacja, przycięcie pasków UI Facebooka), `--psm 6`.
- Z OCR zrzutu reklamy wyciągnąć osobno: reklamodawcę, nagłówek kreacji, tekst przycisku, domenę z podpisu linku.
- **Gotowe gdy:** dla zrzutów z przypadków 1, 3, 48 OCR ma poprawne polskie znaki, a `advertisers` = „Formal Favorable”,
  „EasyJoy”, „Sharon Coleman” (dziś 48 nie łapie nazwy).

### C1. Favicony, skrypty i trackery z HAR (P0, ~2 h) — C
- HAR ma zapisane odpowiedzi. Wyciągnąć bez kontaktu ze stronami:
  - hash favicony (`/favicon.ico`, `<link rel=icon>`; mmh3 jak w Shodan albo sha256 treści + pHash obrazu),
  - hashe treści skryptów własnych domeny (nie CDN), np. `main.js`, `events-stat.js`; nazwy plików zestawów,
  - identyfikatory z ciał skryptów (piksele, Google Ads, klucze API, adresy endpointów, `clickid`, nazwy kampanii),
  - łańcuchy przekierowań z nagłówków `Location` i meta refresh / `window.location` w HTML.
- Nowe dowody: `shared_favicon`, `shared_script`, `shared_endpoint` (ślady techniczne).
- **Gotowe gdy:** dowody działają na sztucznym HAR w teście i pojawiają się w przesłankach na prawdziwym zbiorze (sprawdzić,
  czy wzmacniają S1 i czy łączą coś nowego; każde nowe połączenie zweryfikować ręcznie).

### D0. Organizacja (P0, ~0,5 h) — D
- Potwierdzić na Discordzie: termin oddania, format ukrytego testu (czy taki sam układ folderów), formę przekazania repo
  (dodać konto organizatora jako współpracownika prywatnego repo?).
- Przypisać osoby do ról w tej tabeli i w README.
- **Gotowe gdy:** termin i forma oddania wpisane w `docs/01_ZADANIE.md`.

### D1. Wejście „cały folder” w UI i eksport (P0, ~1 h) — D
- ✅ **Zrobione:** karta kampanii (okno obserwacji, domeny do weryfikacji z priorytetem, przesłanki, braki) w UI
  i `fejki demo cards`; eksport Markdown i CSV domen do weryfikacji.
- Zostaje: w zakładce analizy wskazanie folderu z wieloma przypadkami (ścieżka albo upload zip) → dopasowanie każdego,
  tabela wyników i CSV dopasowań (wspólnie z A3).
- **Gotowe gdy:** z UI da się w 3 kliknięciach przejść „nowy zbiór → wyniki → raport do pobrania”.

---

## Etap 2: jakość kanałów (P1)

### A4. Kalibracja wag i progów (P1, ~2 h) — A (po A1, A2)
- Siatka progów (0,5–0,9) i skal wag kanałów; wybór ustawienia maksymalizującego F1 na etykietach przy zerze fałszywych połączeń
  na negatywach. Uczciwie opisać, że to mały zbiór (ryzyko przeuczenia), więc zmiany wag tylko gdy poprawiają oba testy.
- Opcjonalnie: wagi z prostej regresji logistycznej na parach (cechy = kanały) z ograniczeniem do nieujemnych wag.
- **Gotowe gdy:** tabela „przed/po” w METODYKA.md, nowe wagi w `W` z komentarzem.

### B2. Embeddingi obrazów: CLIP / SigLIP (P1, ~3 h) — B
- `demo/vision.py`: embedding zrzutów, kreacji, klatek i większych zasobów stron (open_clip ViT-B-32 lub SigLIP; CPU OK).
- Dowód `visual_similar` (kosinus ≥ próg) z opisem „podobna kreacja/układ” + miniatury w UI dla najlepszej pary.
- **Cel:** domknąć lukę „same zrzuty” (test `partial_inputs`) bez fałszywych połączeń z A2.
- **Gotowe gdy:** „tylko zrzuty” trafia do właściwej sieci w ≥ 2/4 przypadków albo jest uczciwie opisane, dlaczego nie.

### B3. Transkrypcja nagrań (P1, ~2 h) — B
- `demo/audio.py`: ścieżka audio z mp4 (ffmpeg) → Whisper (faster-whisper small, CPU) lub SpeechBrain (wskazówka z
  zagadki); tekst do `Material.text` z oznaczeniem źródła.
- **Gotowe gdy:** przypadki 5, 14, 47 mają transkrypcję; czas budowy indeksu mieści się w kilku minutach (cache po hashu pliku).

### B4. Logotypy i podróbki marek (P1, ~2 h) — B
- Wykrywanie podszywania pod portale/marki: tytuł/og:site_name/logo w zasobach (np. `logo-gazeta.svg`, „TVN24”,
  „App Store”) → cecha `impersonated_brand`; dowód słaby (wiele kampanii podrabia te same portale), ale świetny do opisu.
- **Gotowe gdy:** materiały 1, 2, 3, 10, 48, 61 mają rozpoznaną podrabianą markę w karcie materiału.

### C2. Embeddingi tekstu i narracja (P1, ~2,5 h) — C
- Obok TF-IDF: bge-m3 lub multilingual-e5 (jest w części badawczej `embed/encoder.py`) na tytułach i pierwszych akapitach;
  dowód `narrative_similar` („ten sam schemat narracji”: atak/aresztowanie znanej osoby → platforma inwestycyjna).
- Opcjonalnie LEACE tematu z części badawczej (wyjaśnić w pitchu jako atut metodyczny, ale nie główną oś).
- **Gotowe gdy:** 3 (Olejnik) i 1 (Brzoska) mają dowód narracji, a negatywy z A2 nie przekraczają progu.

### C3. Infrastruktura dla domen z DANE.zip (P1, ~0,5 h) — C
- ✅ **Zrobione:** `fejki demo build --infra` dla 9 domen; potwierdza S1 (rejestracje w odstępie 1 min i ~95 min,
  certyfikaty tego samego dnia), wyniki w `docs/02_DANE.md`; wykluczone słabe dowody (`/favicon.ico`, makra adresów Meta).
- Zostaje: ponowić crt.sh dla 3 domen z timeoutem (meroporepufulo.life, shryxla-mynx.icu, novumfy.com); sprawdzić, czy
  wspólne `clickid`/`key` (2↔14, wynik 0,41) to tylko popularny system TDS, czy coś więcej.
- Połączyć z wynikami ze strony-zagadki (piksel 2012165449475163 z p15 `lundevra.live` = przypadki 1 i 2).
- **Gotowe gdy:** opis w `docs/02_DANE.md` (sekcja wzorców) zaktualizowany o wyniki infrastruktury.

### D2. Meta Ad Library: sprawdzanie `ad_id` (P1, ~2 h) — D (po uzyskaniu tokenu)
- Token w `code/.env`; test adaptera `ingest/meta_api.py`; funkcja `lookup_ad(ad_id)` → `page_id`, `page_name`, tekst, daty,
  kraje; nowe cechy materiału i dowód `same_page_id` (bardzo silny).
- Bez tokenu: przycisk w UI „Sprawdź w Ad Library” z linkiem `facebook.com/ads/library/?id=…` (działa od razu).
- **Gotowe gdy:** dla przypadków 5, 14, 36, 47 UI pokazuje dane z Ad Library albo czytelny komunikat o braku dostępu.

---

## Etap 3: punkty dodatkowe i oddanie (P1/P2)

### D3. Scheduler wyszukiwania w bibliotekach (P2, ~2 h) — D
- `demo/scheduler.py` + `fejki demo watch`: co N minut zapytanie `ads_archive` (PL, ostatnie dni) po słowach kluczowych
  z kampanii (produkty, nazwiska, frazy-wabiki) → nowe reklamy jako materiały → dopasowanie → lista „nowe w kampanii K…”.
- **Gotowe gdy:** jedno uruchomienie na żywo z tokenem zapisuje wyniki i UI je pokazuje (nawet jeśli 0 trafień).

### C4. Skalowanie (P2, ~1,5 h) — C
- Blokowanie kandydatów zamiast O(n²): indeksy odwrócone po domenie, pikselu, schemacie, katalogu, produkcie + MinHash/LSH
  tekstu (jest w części badawczej); indeks inkrementalny (dokładanie materiałów bez przeliczania całości).
- Opcjonalnie eksport grafu do Neo4j (CSV do `neo4j-admin import` albo Cypher).
- **Gotowe gdy:** test na 1000 sztucznych materiałów mieści się w kilku sekundach na parę wejście–zbiór.

### B5. (opcjonalnie) Twarze z małą bazą referencyjną (P2, ~3 h) — B
- Brief dopuszcza małą bazę osób. InsightFace (ArcFace) na klatkach i zrzutach + 3–5 zdjęć referencyjnych na osobę z
  `config/osoby.txt`; dowód `same_face`. **Decyzja zespołu przed startem** (prywatność, licencje modeli InsightFace są
  niekomercyjne; dziś osoby rozpoznajemy tylko po nazwiskach).

### A5. Wzorce kampanii dla NASK (P1, ~1,5 h) — A
- Dokument `docs/07_WZORCE_KAMPANII.md`: opis sieci S1 (zestaw stron, TDS, rotacja domen i reklamodawców, narracje),
  cloakingu, kampanii produktowych, przydatnych źródeł metadanych. To „wiedza z wyzwania”, o którą prosi pkt 10 opisu.

### D4. Pitch i demo (P0 na koniec, ~2 h) — D (+ wszyscy)
- Slajdy 5–7: problem → podejście (kanały + przesłanki) → demo na żywo (nowy materiał → kampania z uzasadnieniem) →
  wyniki testów (uczciwie, z lukami) → wzorce kampanii → wdrożenie (Docker, skalowanie, biblioteki reklam).
- Scenariusz demo na 3 minuty + plan B (nagranie ekranu), gdyby coś padło.
- Ostatnie: `docker build` od zera, `pytest`, `fejki demo eval`, README sprawdzony przez osobę spoza zadania.

## Zależności

```
A1 ─► A4 ◄─ A2          B1 ─► B2 ─► (A4)        C1 ─► (A4)        D0 ─► D2 ─► D3
A3 (niezależne)          B3, B4 (niezależne)     C2 ─► (A4)        D1 (niezależne)
                                                 C3, C4            D4 na końcu (wszyscy)
```

## Sugerowany przydział czasu (dla 4 osób)

| Blok | A | B | C | D |
|---|---|---|---|---|
| 1 | A1 | B1 | C1 | D0, D1 |
| 2 | A2, A3 | B2 | C1, C3 | D1, D2 |
| 3 | A4 | B3 | C2 | D2 (gdy token), raport |
| 4 | A5 | B4 (B5?) | C4 | D3, D4 |
| finał | testy, liczby do pitchu | demo wizualne | demo infrastruktury | pitch, Docker, oddanie |

## Definicja „gotowe do oddania”

- [ ] `docker build` i `docker run` z czystego klonu repo działają według README;
- [ ] `pytest` zielony, `fejki demo eval` z metrykami względem etykiet i negatywów;
- [ ] UI: nowy materiał (każdy typ wejścia), cały nowy folder, kampanie, graf, raport do pobrania;
- [ ] METODYKA.md aktualna (kanały, wagi, testy, ograniczenia, licencje nowych bibliotek i modeli);
- [ ] `docs/07_WZORCE_KAMPANII.md` dla NASK;
- [ ] repo przekazane organizatorowi zgodnie z ich instrukcją; brak danych organizatora i sekretów w historii gita.
