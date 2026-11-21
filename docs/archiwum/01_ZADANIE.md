# 01. Zadanie: „Kolekcjoner fejków / Follow the Fake”

Źródła: [brief/opis-wyzwania.pdf](../brief/opis-wyzwania.pdf) (formalny opis, 6 stron + plakat),
[brief/plakat.jpg](../brief/plakat.jpg), [brief/brief.md](../brief/brief.md) (przepisany tekst plakatu).
Zgłaszający: Ośrodek Badań nad Bezpieczeństwem Sztucznej Inteligencji, NASK PIB.

## Krótko

Zbudować narzędzie, które z chaosu pojedynczych podejrzanych reklam wydobędzie wspólne ślady i połączy je w większe kampanie
oszustw. Ma automatycznie analizować **treść, warstwę wizualną i publiczne metadane infrastruktury**, a potem pokazywać
podobieństwa i zależności między incydentami w czytelnej formie.

**Nie** chodzi o idealny detektor pojedynczej fałszywej reklamy. Liczy się **skuteczna, możliwa do wyjaśnienia metoda łączenia**
niezależnych materiałów w większe struktury, z uwzględnieniem dostępnych danych i wiarygodności powiązań.

## Kontekst (z opisu)

Fałszywe reklamy z wizerunkami znanych osób są publikowane masowo, prowadzą do spreparowanych stron i żyją na krótko
żyjących domenach. Pojedyncze zgłoszenie ma małą wartość; informacja pojawia się dopiero po zestawieniu wielu przypadków
(cechy, narracje, materiały wizualne, ślady infrastruktury). Brakuje ustrukturyzowanego sposobu, by automatycznie wyciągać
cechy, porządkować je, usuwać duplikaty i łączyć pozornie niezależne reklamy w kampanie. Sygnały: podobna narracja, te same
osoby, zbliżony szablon produkcyjny, wspólne domeny, mechanizmy przekierowań, inne drobne sygnały.

## Oczekiwany rezultat (pkt 3 opisu)

Działający demonstrator + opisana metodyka. Rozwiązanie powinno:

| Wymóg | Stan u nas |
|---|---|
| przyjmować materiały: URL reklamy lub strony, zrzut ekranu, log komunikacji, plik multimedialny, dane ze zbioru, inną wskazówkę | ✅ folder, HTML, HAR, PNG/JPG, MP4, info.json, URL, tekst |
| zbierać i porządkować: tekst, słowa kluczowe, tematykę, wizerunki osób, logotypy, cechy wizualne, domeny, przekierowania, linki, strukturę stron, metadane domen i infrastruktury | ✅ prawie wszystko; ⚠️ logotypy brak; ⚠️ osoby tylko po nazwiskach (bez twarzy) |
| zamieniać dane na zestaw cech do porównań | ✅ `Material` (code/src/fejki/demo/material.py) |
| identyfikować duplikaty i warianty tego samego przekazu | ✅ relacje „duplikat” / „wariant” |
| metoda podobieństwa i grupowania w kampanie | ✅ dowody w kanałach + noisy-OR + składowe spójne; dwa poziomy: kampania i sieć |
| analiza nowego materiału względem zbioru, wskazanie potencjalnych nowych kampanii | ✅ zakładka „Analiza nowego materiału” |
| prezentacja: klastry, graf, lista podobnych | ✅ tabele, graf pyvis, lista najbliższych kampanii |
| wskazywać cechy i przesłanki powiązania | ✅ każda krawędź ma listę przesłanek z wagami |
| prosty interfejs graficzny | ✅ Streamlit |
| dokumentacja metodyki | ✅ code/docs/METODYKA.md |
| niekompletne dane (niedostępne strony, brak materiałów) | ✅ braki nie przerywają analizy; testy „niepełne wejście” |

**Dodatkowo punktowane:** automatyczne wyszukiwanie podejrzanych reklam w publicznych źródłach (biblioteki reklam: słowa
kluczowe, daty, reguły), okresowe aktualizacje, wykrywanie nowych materiałów powiązanych z wykrytymi kampaniami. U nas: ❌
(adapter Meta gotowy, brak tokenu i schedulera; patrz zadania D2/D3 w planie).

## Wymagania formalne (pkt 4)

1. działający demonstrator z prostym GUI ✅
2. opis metodyki: pozyskiwanie cech, podobieństwo, grupowanie ✅ (do dopracowania pod pitch)
3. instrukcja instalacji, konfiguracji, uruchomienia, zależności ✅ (README, code/README.md)
4. kod w repozytorium Git ✅ (to repo; **prywatne**, trzeba dodać organizatora jako współpracownika albo przekazać inaczej)
5. pomocne: środowisko w kontenerze ✅ (code/Dockerfile, sprawdzone)

Technologie dowolne. Przy zewnętrznych usługach/modelach/API: opisać jak uzyskać dostęp i umożliwić weryfikację; **nie
przekazujemy prywatnych kluczy**. Wskazać biblioteki, modele, usługi wraz z licencjami i ograniczeniami ✅ (METODYKA, pkt 8).

## Wymagania techniczne (pkt 5)

- demonstrator np. w Streamlit/Gradio; estetyka nie jest oceniana (na plakacie: ocena 0/1 „jest albo nie ma”);
- zakres analizy i metoda podobieństwa otwarte (reguły, ważenie, ML, embeddingi, klastrowanie, grafy; np. Neo4j);
- porównywanie nowych materiałów z wcześniej przeanalizowanymi, przy niekompletnych danych;
- identyfikacja osób: dopuszczalna **niewielka baza referencyjna** najczęściej występujących osób; rozmiar nie jest kluczowy;
- łatwe przenoszenie i uruchomienie: preferowana wersja w kontenerze z instrukcją.

## Walidacja (pkt 6)

Ocena na podstawie **demonstracji** i **testów na materiałach organizatora**: udostępniony zbiór przykładowy +
**dodatkowy, wcześniej nieudostępniony zbiór testowy** z nowymi wariantami znanych kampanii i materiałami innych kampanii.

Sprawdzane:
- skuteczność identyfikowania podobnych materiałów i wariantów tych samych kampanii;
- poprawność przypisywania nowych materiałów do istniejących grup;
- zdolność do **niełączenia** materiałów, które nie powinny być połączone ze znanymi kampaniami;
- przydatność i różnorodność cech;
- odporność na duplikaty, niekompletne dane i różnice w formacie;
- interpretowalność (przesłanki powiązań);
- kompletność od wczytania danych do prezentacji wyników.

Na demonstracji zespół pokazuje pełny proces: przetworzenie wejścia → cechy → porównanie → grupowanie → prezentacja.
Ocenia się też **sensowność metodyki**: dobór źródeł i cech, liczenie podobieństwa, odporność na duplikaty, wyjaśnialność.

**Wniosek dla nas:** ukryty zbiór testowy najpewniej ma ten sam układ co `DANE.zip` (folder = przypadek, numery z lukami:
mamy 1, 2, 3, 5, 10, 14, 36, 47, 48, 61, więc brakujące numery są zapewne w zbiorze testowym). Demonstrator musi umieć
**szybko wczytać nowy folder z wieloma przypadkami** i pokazać wynik: to już działa (`fejki demo build <folder>`), ale
trzeba to przećwiczyć (zadanie A3).

## Kryteria oceny (pkt 9)

| Kryterium | Waga | Co nas tu niesie | Co trzeba dociągnąć |
|---|---|---|---|
| Jakość metody korelacji i grupowania | 30% | dwa poziomy (kampania/sieć), noisy-OR z przesłankami, test pomiń-jeden | etykiety referencyjne, kalibracja wag, test negatywny |
| Użyteczność i trafność cech oraz źródeł danych | 30% | kilkanaście kanałów, schemat TDS, piksele, ad_id, cloaking, infra | obraz (CLIP), logotypy, polski OCR, transkrypcja audio, Ad Library |
| Kompletność demonstratora (end-to-end) | 15% | wszystkie wejścia, Docker | wczytanie całego nowego zbioru z UI, eksport raportu |
| Czytelność i interpretowalność powiązań | 15% | graf, tabele przesłanek | raport kampanii (karta), lepszy graf |
| Potencjał wdrożeniowy, skalowalność, przenośność | 10% | Docker, CLI | indeks inkrementalny, Neo4j/eksport, scheduler |

## Zasady danych (pkt 8)

Materiały organizatora tylko na potrzeby wyzwania, **zakaz publicznego rozpowszechniania**. Dodatkowe dane i publiczne źródła
dozwolone, pod warunkiem wskazania pochodzenia. Organizator może testować na materiałach spoza zbioru.

## Kontekst wdrożeniowy (pkt 10)

Dla NASK ważna jest też wiedza z wyzwania: wzbogacony i uporządkowany zbiór danych, opis zidentyfikowanych wzorców kampanii,
metodyka łączenia cech, wskazanie użytecznych źródeł metadanych. Warto to oddać jako osobny dokument (zadanie D4).

## Kontakt

Mentorzy techniczni i merytoryczni w punkcie konsultacyjnym; pytania na kanale Discord wyzwania.
Termin oddania: **do potwierdzenia** (nie mamy go zapisanego).
