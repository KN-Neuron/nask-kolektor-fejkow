# 12. Zgodność z wymaganiami wyzwania (macierz weryfikacji)

Źródło wymagań: [brief/opis-wyzwania.pdf](../brief/opis-wyzwania.pdf) (numeracja punktów jak w PDF). Stan na 2026-11-21.
Legenda: ✅ spełnione i zweryfikowane · ⚠️ spełnione częściowo (luka opisana) · ⬜ nie zrobione.
Kolumna „Jak sprawdzić” zawiera polecenie lub miejsce w interfejsie, które to pokazuje.

## Pkt 3: oczekiwany rezultat

| # | Wymaganie | Stan | Jak jest zrealizowane | Jak sprawdzić |
|---|---|---|---|---|
| 3.1 | przyjmować URL reklamy/strony | ✅ | pole URL, analiza bierna (domena, schemat parametrów, identyfikatory, wzorce ścieżek, opcjonalnie DNS/RDAP/crt.sh) | UI → „Analiza nowego materiału” → URL |
| 3.2 | przyjmować zrzut ekranu | ✅ | OCR (Tesseract, pol), pHash, odczyt reklamodawcy i identyfikatora Ad Library ze zrzutu | UI → wgraj PNG |
| 3.3 | przyjmować log komunikacji | ✅ | log HAR: adresy, parametry, przekierowania, hosty, znaczniki czasu | UI → wgraj `.har` |
| 3.4 | przyjmować plik multimedialny | ✅ | MP4: klatki (FFmpeg), OCR i pHash klatek | UI → wgraj `.mp4` |
| 3.5 | przyjmować dane ze zbioru organizatora / inną wskazówkę | ✅ | folder przypadku, zip, płaski folder, `info.json`, tekst, nazwa produktu | UI → „Nowy zbiór (folder / zip)”, `fejki demo match` |
| 3.6 | zbierać i porządkować: tekst, słowa kluczowe, tematykę | ✅ | tekst strony i OCR, słowa kluczowe, tematyka (słownik), DNA perswazji (10 ruchów) | zakładka „Materiały” |
| 3.7 | wizerunki osób | ⚠️ | osoby po nazwiskach w tekście i OCR (baza `config/osoby.txt`, odmiana polska); **bez rozpoznawania twarzy** (pkt 5 dopuszcza małą bazę referencyjną) | karta materiału: „Osoby” |
| 3.8 | logotypy | ⚠️ | marka/portal podrabiany rozpoznawana po nazwach logotypów w zasobach strony (np. `logo-gazeta.svg`); **bez detekcji logotypu na obrazie** | dowód „podrabiana ta sama marka” |
| 3.9 | cechy wizualne | ⚠️ | pHash zrzutów, kreacji, klatek i obrazów ze stron; szablon strony (klasy HTML); embeddingi obrazu (Meta PE-Core B/16, opcjonalnie): na zrzutach stron AUC 0,75, ale na kartach reklam nie rozróżniają kampanii (pomiar w METODYKA 5d), więc same zrzuty nadal łączą się słabo | `fejki demo eval` (niepełne wejście: **same zrzuty trafiają do właściwej sieci w 0 z 4 przypadków**, sam HTML i sam HAR w 5 z 5) |
| 3.10 | domeny, przekierowania, linki, struktura stron | ✅ | domeny docelowe, usługi zewnętrzne, przekierowania z HAR, linki, klasy HTML, cloaking | karta materiału |
| 3.11 | publiczne metadane domen i infrastruktury | ✅ | DNS, ASN (Team Cymru), RDAP (rejestrator, data), crt.sh; wiek domeny | panel boczny → „Zbierz dane infrastruktury” |
| 3.12 | zamieniać dane na zestaw cech do porównań | ✅ | model `Material` (pydantic, ~35 pól) | `code/src/fejki/demo/material.py` |
| 3.13 | identyfikować duplikaty i warianty tego samego przekazu | ✅ | relacje „duplikat” i „wariant tego samego przekazu” | tabela „Kampanie i sieci” |
| 3.14 | metoda podobieństwa i grupowania | ✅ | dowody w 12 kanałach + noisy-OR; grupowanie średnim wiązaniem (bez łańcuchowania); opis: [10_PODOBIENSTWO.md](10_PODOBIENSTWO.md) | `fejki demo eval` |
| 3.15 | analiza nowego materiału względem zbioru, wskazanie nowych kampanii | ✅ | `match()`: przypisanie / nowa kampania w znanej sieci / do weryfikacji / nowy wzorzec; wsad z propozycjami nowych kampanii | UI → „Nowy zbiór” |
| 3.16 | prezentacja: klastry, graf, lista | ✅ | tabele kampanii i sieci, graf pyvis, lista najbliższych kampanii, karty kampanii | UI → „Kampanie i sieci”, „Graf” |
| 3.17 | wskazywać cechy i przesłanki powiązań | ✅ | każda krawędź ma listę przesłanek (kanał, waga, opis po polsku) | UI → rozwiń „Najbliższe kampanie” |
| 3.18 | prosty interfejs graficzny | ✅ | Streamlit, 7 zakładek | `fejki demo app` |
| 3.19 | dokumentacja metodyki | ✅ | [code/docs/METODYKA.md](../code/docs/METODYKA.md), [10_PODOBIENSTWO.md](10_PODOBIENSTWO.md) | |
| 3.20 | niekompletne dane, niedostępne strony | ✅ | braki w polu `missing`, analiza nie przerywa się; testy „niepełne wejście” (sam HTML, sam HAR, same zrzuty) i uszkodzone pliki | `fejki demo eval` |
| 3.B | (bonus) wyszukiwanie w bibliotekach reklam, okresowe aktualizacje, nowe materiały powiązane z kampaniami | ✅/⚠️ | kolektor Meta Ad Library (97 447 reklam), scheduler `fejki demo watch` (jednorazowo lub w pętli) dopasowuje nowe reklamy do kampanii; **działa po podaniu aktualnego tokenu** (token wygasa po kilku godzinach; wcześniej zweryfikowane na żywo) | `fejki demo watch`, test `test_meta_ad_becomes_material…` |

## Pkt 2 i 6: cel i walidacja (co sprawdza organizator)

| Kryterium walidacji | Stan | Dowód |
|---|---|---|
| skuteczność identyfikowania podobnych materiałów i wariantów kampanii | ✅ | zbiór organizatora: K1={1,2}, K2={48,61}; urlscan: B-cubed P 0,98 |
| poprawność przypisywania nowych materiałów do grup | ✅ | test pomiń-jeden: 100% spójności kampanii i sieci |
| identyfikowanie materiałów, które **nie** powinny być połączone | ✅ | 0 doklejonych negatywów (urlscan); test jednostkowy: obcy przepis/kasyno nie są doklejane; poprawka: sam szablon HTML nie przekracza progu weryfikacji |
| przydatność i różnorodność cech | ✅ | 12 kanałów (tekst, semantyka, osoby, produkt, reklamodawca, śledzenie, adres, domena, obraz, logo, szablon, infrastruktura) |
| odporność na duplikaty, niekompletne dane, różne formaty | ✅ | wsad: folder, płaski folder, zip (bezpieczne rozpakowanie); testy |
| interpretowalność, przesłanki | ✅ | patrz 3.17 |
| kompletność: od wczytania do prezentacji | ✅ | UI + `fejki demo match` → CSV |

**Niepewność wyniku na ukrytym zbiorze:** nasze liczby pochodzą z 10 przypadków organizatora (jeden podmiot wieloelementowy)
oraz z danych dodatkowych; nie mamy etykiet organizatora. Ryzyka: [08_KRYTYKA_I_RYZYKA.md](08_KRYTYKA_I_RYZYKA.md).

## Pkt 4 i 5: wymagania formalne i techniczne

| Wymaganie | Stan | Gdzie |
|---|---|---|
| działający demonstrator z GUI | ✅ | `fejki demo app` / Docker |
| opis metodyki | ✅ | METODYKA.md |
| instrukcja instalacji, konfiguracji, uruchomienia, zależności | ✅ | README, `docs/00_START_TUTAJ.md`, `code/README.md` |
| kod w repozytorium Git | ✅ | prywatne repo KN-Neuron/nask-kolektor-fejkow (**dodać organizatora jako współpracownika** albo przekazać inaczej) |
| konteneryzacja | ✅ | `code/Dockerfile` (z polskim OCR i FFmpeg) |
| zewnętrzne usługi i modele: opis dostępu, licencje, ograniczenia | ✅ | METODYKA.md pkt 8 (tabela licencji); bez przekazywania kluczy (`.env.example`) |
| osoby: mała baza referencyjna | ⚠️ | baza nazwisk (26 osób); bez twarzy |
| porównywanie nowych materiałów z przeanalizowanymi, niekompletne dane | ✅ | patrz 3.15 i 3.20 |
| Neo4j (jeden z kierunków) | ⚠️ | eksport do Neo4j (Cypher, CSV) i GraphML; **bez uruchomionej bazy** (nie wymagana) |
| dowolność technologii i metody | ✅ | |

## Pkt 8: zasady danych

| Zasada | Stan |
|---|---|
| materiały organizatora tylko na potrzeby wyzwania, bez publicznego rozpowszechniania | ✅ dane lokalnie, w `.gitignore`; repo prywatne; skan sekretów i danych przed commitem |
| dodatkowe dane z podaniem pochodzenia | ✅ urlscan.io i Meta Ad Library opisane w README, docs/02, docs/07 i METODYKA |

## Pkt 9: kryteria oceny, gdzie jesteśmy

| Kryterium | Waga | Co mamy | Główna luka |
|---|---|---|---|
| jakość korelacji i grupowania | 30% | wielokanałowe dowody z przesłankami, grupowanie bez łańcuchowania, model par uczony (AUC 0,79 > ręczne 0,78), podział bez wycieku | model par nie jest jeszcze wpięty w grupowanie; ręczne wagi |
| użyteczność i trafność cech i źródeł | 30% | 12 kanałów, infrastruktura bierna, Meta, urlscan, bge-m3 | brak embeddingów obrazu i twarzy |
| kompletność demonstratora, end-to-end | 15% | 7 zakładek, wsad z CSV, scheduler, eksport grafu, Docker | — |
| czytelność i interpretowalność | 15% | przesłanki w języku analityka, karty kampanii, graf | — |
| wdrażalność i skalowalność | 10% | Docker, CLI, eksport do Neo4j | O(n²) par; indeks w jednym JSON (plan: blokowanie kandydatów) |

## Pkt 10: wiedza dla organizatora

| Oczekiwanie | Stan | Dokument |
|---|---|---|
| wzbogacony i uporządkowany zbiór danych | ✅ | indeks cech zbioru organizatora; zebrane lokalnie 97 tys. reklam i 122 skany (opis w docs/07) |
| opis zidentyfikowanych wzorców kampanii | ✅ | [11_WZORCE_KAMPANII.md](11_WZORCE_KAMPANII.md) |
| metodyka łączenia cech | ✅ | METODYKA.md, 10_PODOBIENSTWO.md |
| wskazanie użytecznych źródeł metadanych | ✅ | docs/06, docs/07 |

## Co jeszcze warto zrobić (w kolejności wpływu)

1. Dostrojenie embeddingów obrazu kontrastowo na zrzutach urlscan (surowy PE-Core nie rozróżnia kampanii na kartach reklam) oraz model wizyjno-językowy do OCR; domyka 3.7–3.9.
2. Skalibrować próg modelu par i włączyć go domyślnie (dziś opcjonalny przełącznik).
3. Rozszerzyć syntetykę o obrazy (zrzuty) i trudniejsze zbieżności schematów.
4. Indeks inkrementalny (blokowanie kandydatów jest, kosztem czułości przy małych zbiorach).
5. Nowy token Meta przed demonstracją (scheduler na żywo).
