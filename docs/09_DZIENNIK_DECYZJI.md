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
