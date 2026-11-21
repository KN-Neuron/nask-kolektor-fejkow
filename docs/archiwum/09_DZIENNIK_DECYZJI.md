# 09. Dziennik decyzji i procesu (prowadzony na bieżąco)

Chronologicznie: co zrobiliśmy, **dlaczego**, co wyszło, co nie wyszło. Nowe wpisy dopisujemy na dole.

## 2026-11-21

1. **Zagadka ze strony organizatorów.** Rozwiązaliśmy warstwy (93JNG → `scam_links.enc`, SPEECHBRAIN, „meta ads library”,
   lusterko). Hasła do `___BACKUP.zip` nie znaleźliśmy; mentor: „jest wszystko”. Pomyłka po drodze: uznałem `loop.gif` za
   dekorację, a był w nim napis; poprawione w dokumentacji. Wniosek: zagadka była zajawką, nie zbiorem danych.
2. **Oficjalny zbiór to `DANE.zip`** (10 przypadków). Decyzja: tylko test końcowy, nie stroimy na nim.
3. **Zakres** z formalnego PDF: łączenie w kampanie z przesłankami, nie detektor pojedynczego fejka. Kryteria 30/30/15/15/10.
4. **Decyzja: nie odwiedzamy stron oszustów.** Tylko nagrane pliki i bierne źródła (DNS, RDAP, crt.sh, urlscan). Powód: bezpieczeństwo, etyka, a nagrane HAR/HTML wystarczają.
5. **Demonstrator**: kanały dowodów + noisy-OR + dwa poziomy (kampania = ten sam przekaz, sieć = operator). Dlaczego dwa
   poziomy: nie wiemy, jak organizator definiuje kampanię. Wynik: K1={1,2}, K2={48,61}, sieć S1={1,2,3,48,61}.
6. **Karta kampanii** (okno obserwacji, domeny do weryfikacji, wiek domen) — nawiązanie do pierwotnej idei dla CERT.
   Infrastruktura potwierdziła S1 niezależnie (rejestracja domen w odstępie 1 min).
7. **Hipoteza LEACE** („schemat perswazji odróżnia operatorów”). TF-IDF: LEACE nic nie zmienia. bge-m3: LEACE zbliża
   wszystkie oszustwa i **zmniejsza** odstęp sieci (0,214 → 0,158), kontrola losowa bez zmian. **Wynik negatywny**, zapisany
   uczciwie. Nowa hipoteza H2: schemat odróżnia oszustwo od legalnej treści (do sprawdzenia na reklamach z Mety).
8. **Zbiory dodatkowe.** urlscan: 122 skany (bez klucza), sieć P 0,98 / R 0,45, 0 doklejonych negatywów. Meta: token działa,
   ale API nie pobiera reklam po id i nie znalazło reklam z przypadków (krótkie życie, usunięcia). Zebraliśmy **97 447 reklam**
   z **13 246 stron**, w tym **15 862 usuniętych przez Metę** (56 słów kluczowych + druga runda: reklamy 300 podejrzanych stron).
   Rola: nowe podejrzane reklamy, etykiety słabe (usunięta = sygnał), negatywy.
9. **Wyciek.** (a) Na zewnątrz: dane i tokeny poza gitem; incydent: plik `data/si.txt` z tokenem prawie trafił do commita,
   skan nie złapał prefiksu „EAB”; poprawione `.gitignore` i skan. (b) W ocenie: podział subject-based + `audit()`.
   Na zbiorze organizatora jest tylko jeden podmiot wieloelementowy, więc kalibracja na urlscan i Mecie.
10. **Krytyka** (docs/08): 14 ryzyk, najważniejsze: definicja kampanii, zestaw stron ≠ operator, same zrzuty nie łączą.

## Następne kroki

- etykiety słabe na reklamach Meta (usunięte + domeny z Listy CERT), negatywy = legalne reklamy;
- model podobieństwa par uczony zamiast ręcznych wag (podział subject-based);
- H2 na Mecie; kanał obrazu (CLIP) dla samych zrzutów.

## 2026-11-21 (wieczór)

11. **Dokument wejściowy** `docs/00_START_TUTAJ.md` dla nowych osób (słowniczek, zasady, uruchomienie, mapa, wyniki).
12. **Plan syntetyki**: generator folderów przypadków w formacie organizatora (szablony z prawdziwych przypadków, operator = zestaw + TDS + piksel + styl domen, warianty z kontrolowaną zmiennością i brakami, trudne przypadki, domeny `.example`/`.test`), ocena z ablacją kanałów; wyniki raportowane osobno od danych prawdziwych.

13. **Łańcuchowanie (zarzut krytyka potwierdzony).** urlscan, próg 0,5: składowe spójne sklejają 89/122 w jedną grupę (B-cubed P 0,627). Wdrożone średnie wiązanie z wymogiem wsparcia 0,15 (`similar.campaigns`, domyślne): F1 0,627 → 0,678, największa grupa 89 → 46; zbiór organizatora bez zmian (S1 = 1,2,3,48,61). Źródło pomysłu: literatura entity resolution („black hole”, correlation clustering).
14. **Faza uczenia** (`demo/learn.py`): regresja logistyczna par z nieujemnymi wagami, leave-one-group-out na urlscan (7380 par). ROC AUC 0,791 / AP 0,797 wobec ręcznych wag 0,775 / 0,759. Kontrola cyrkularności: bez cech, z których zbudowano pivoty (schemat, ścieżka, prefiks, host), wynik ten sam (0,791 / 0,798). Model zapisany w `artifacts/demo/pair_model.json`; jeszcze NIE wpięty w demonstrator.
15. **Multimodal** (uwaga: CLIP przestarzały): kandydaci Qwen3-VL-Embedding-2B, jina-embeddings-v5-omni, SigLIP 2; plus VLM (np. Qwen3-VL) do odczytu zrzutów zamiast Tesseracta. Do decyzji: pobranie (kilka GB) i licencje.

## 2026-11-21 (audyt zgodności)

16. **Audyt wszystkich punktów opisu** (docs/12). Luki zamknięte kodem: kanał semantyczny w grupowaniu (bge-m3, podłoga 0,88),
    logotypy/podrabiane marki, wsad nowego zbioru (folder/płaski/zip → CSV + propozycje nowych kampanii; to wejście ukrytego testu),
    eksport grafu (GraphML, Cypher dla Neo4j), scheduler Meta (kod + test na atrapie).
17. **Test negatywny wykrył fałszywe powiązanie**: sam szablon HTML (90% wspólnych klas, mała strona) dawał 0,6, więc obcy przepis trafiał do
    „do weryfikacji”. Poprawka: szablon tylko dla stron z ≥ 25 elementami, waga ≤ 0,35. Wyniki na zbiorze organizatora bez zmian.
18. **Token Meta wygasł** (kod 190) po kilku godzinach, zbiór 97 447 reklam zachowany. Scheduler zgłasza to czytelnym komunikatem.
    Wniosek: przed demonstracją wygenerować nowy token.
19. **Luki, których nie zamknęliśmy** (uczciwie): embeddingi obrazu i twarze (3.7–3.9), model par niewpięty w grupowanie, skala O(n²).
    Same zrzuty nadal 0/4 w teście niepełnego wejścia.
20. **Obraz Dockera bez części badawczej**: zakładka „Schemat perswazji” importowała torch i concept-erasure, których podstawowy obraz nie ma (wykryte przy przeglądzie). LEACE wyłącza się łagodnie z ostrzeżeniem w UI; pełna wersja: `pip install -e ".[research]"`.

## 2026-11-21 (modele, uczenie, ablacja)

21. **PE-Core B/16 pobrany** (po sprostowaniu: 1,79 GB, nie „kilkaset MB”, i za zgodą). Pomiar: na kartach reklam z telefonu embedding
    odzwierciedla format (10↔14 0,84, 48↔61 0,41), na 117 zrzutach stron urlscan AUC 0,753 / precyzja 0,998 przy ≥ 0,8. Decyzja: kanał
    obrazu z podłogą 0,92 (niemal-duplikaty); ogólne „podobieństwo wyglądu” nie rozróżnia kampanii. Surowy model bez dostrojenia to za mało.
22. **Ablacja na syntetyce znalazła błąd metody** (wspólny kit i generyczny schemat sklejają operatorów; sieć F1 0,47). Dodany dowód przeciwny
    (różne piksele / różne schematy) → 0,85; organizator bez zmian. Dowód, że ablacja na danych podłożonych celowo się opłaca.
23. **Blokowanie kandydatów**: 6× mniej par, ale tracimy czułość przy małych zbiorach (0,614 → 0,49), więc tylko > 300 materiałów.
24. **Model par** wpięty jako opcja (przełącznik w UI, parametr `model`); kanał obrazu i model par w UI jako przełączniki.

## 2026-11-21 (wynik z użycia: „nowy wzorzec 0,00”)

25. **Zgłoszenie z użycia**: adres z systemem kierowania ruchu sieci S1 dostał „nowy wzorzec 0,00”. Przyczyna: dopiski platformy reklamowej
    (`utm_source`, `utm_term`, `fbclid`) zmieniały odcisk schematu. Poprawka: odcisk tylko z parametrów o losowych wartościach.
26. **Zbiór referencyjny był za mały** (10 przypadków), więc prawie każdy adres był „nowy”. Dołożone skany urlscan (132 materiały, `--extra`).
27. **Dane Meta nie były używane w analizie** (tylko zebrane). Dodany panel „Co wiemy z Meta” (domena, reklamodawca, id reklamy).
    Uczciwie: nie zmienia to wyniku podobieństwa, a domeny ze zbioru organizatora w Mecie nie występują.
28. **Interpretacja wyniku** (`demo/explain.py`): rozróżnienie „za mało danych” od „nic wspólnego”, lista danych i braków, porady, 5 najbliższych materiałów.
