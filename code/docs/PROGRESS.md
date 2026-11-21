# PROGRESS

Stan na 2026-11-16. Dane: wyłącznie syntetyczne (fixture'y), enkoder BAAI/bge-m3, seed 1.

## Co działa

| Faza | Stan |
|---|---|
| P0 scaffold, config, schema, DuckDB, CLI | gotowe |
| P1 ingest JSONL, normalizacja, domeny, artefakty, gazeteer, SimHash i MinHash | gotowe, testy przechodzą |
| P2 enkoder z cache, klastrowanie agglo i HDBSCAN, B-cubed z bootstrapem po kampaniach | gotowe |
| P3 generator syntetyczny, kontrola C1, wabiki, podział dev i test po kampaniach | gotowe (backend regułowy; backend LLM jest szkieletem, nieprzetestowanym) |
| P4 LEACE, kontrole E4 i E5 z dopasowanym rzędem, sondy, E1 do E4 | gotowe |
| P5 koordynacja, graf Leiden, karty kampanii, `proposed_domains.csv` | gotowe |
| P6 Streamlit (widoki 1 do 6) | napisane, nieuruchomione w przeglądarce |
| P7 adaptery Meta, CERT, replay, bursty, lead time | adaptery nieprzetestowane na żywo (brak tokenu); replay i lead time działają na symulacji |
| P8 komentarze syntetyczne, MinHash LSH, artefakty, sync kont, E8 | gotowe (`fejki comments`); adapter YouTube nieprzetestowany |
| P9 README, PROGRESS, figury | README i PROGRESS gotowe; slajdy w `artifacts/pitch/` nie wygenerowane |

Testy: `pytest`, 13 przechodzi, bez wywołań sieciowych (mock w `conftest.py`).

## Wyniki (artifacts/tables/REPORT.md)

- **H1, kryterium główne** (B-cubed F1, CI nienakładające się z E0, E4, E5): niespełnione.
- **H1, kryterium wtórne** (recall między-tematowy, te same zasady CI): spełnione przez E3 (LEACE tematu, długości i języka) z HDBSCAN. To kryterium dodałem po obejrzeniu wyników, więc jest eksploracyjne.
- LEACE podnosi recall między-tematowy ponad kontrole losowe (przykład HDBSCAN: E0 0,44, E1 0,74, E3 0,86, E4 0,44, E5 0,32), ale obniża precyzję, więc ogólne F1 się nie poprawia.
- E2: po LEACE sonda liniowa na zbiorze FIT spada do poziomu losowego (0,12 przy 0,21 większościowym), ale poza FIT nadal ma 0,60, a MLP 0,85. Zgodnie z oczekiwaniem temat nie zostaje usunięty, tylko liniowo osłabiony.
- E6 (SYMULACJA listy CERT): wykryto 14 z 20 kampanii, precyzja śladów 0,96, mediana lead time około 1,8 dnia.

## Odstępstwa od SPEC

1. Cel strojenia progu na dev: F1 z precyzji ogólnej B-cubed i recallu uśrednionego po kampaniach. Zwykłe B-cubed F1 zbiegało do samych singletonów, bo tło dominuje pulę.
2. Ground truth tła: identyczne kreacje tego samego reklamodawcy to jedna kreacja, a nie osobne grupy.
3. `tau` strojony na dev (wynik około 0,29), bo wartość 0,55 z configu jest nieosiągalna; score do detekcji liczony bez sygnału `cert_hit`, żeby lead time nie był trywialny.
4. E7 liczone na grafie z Leiden, a nie na sumie komponentów (suma zlewała wszystko w jeden klaster).
5. Regiony do burstów: k-means (`bursts.region_method`), a nie HDBSCAN.

## Ograniczenia i ryzyka wyników

- **E7:** na syntetyce sama infrastruktura wygrywa, bo reklamodawcy kampanii są współdzieleni między rotowanymi domenami. Ablacja nie pokazuje więc wartości kanału treści. Potrzebny trudniejszy wariant generatora (rotacja także `page_id`). Próg `graph.edge_cos_min` 0,80 jest zbyt luźny dla bge-m3 i obniża precyzję; do strojenia na dev.
- **E2 (LEACE po nazwisku)** jest w tym przebiegu identyczny z E0 (usunięty rząd 0), bo reklamy tła we FIT nie wymieniają osób z gazeteera. Ten kanał wymaga FIT z nazwiskami (np. część kampanii dev lub tło z osobami).
- **E4:** klasyfikator "syntetyk vs tło" ma AUC około 0,98, czyli styl generatora jest łatwo odróżnialny. To ryzyko zawyżenia wyniku, nie jego dowód; kontrola C1 pokazuje tylko około 5 procent reklam C1 w klastrach kampanii. Tłem są też dane syntetyczne, więc ten test to proxy.
- **E3:** retencja par oryginał i parafraza jest niska dla wszystkich kanałów (0,04 do 0,20), parafraza poziomu 2 regułowa jest bardzo silna. Hipoteza pomocnicza o przewadze LEACE nad SimHash potwierdzona tylko słabo i bez CI.
- Wynik na syntetyce dowodzi odzysku podłożonego szablonu, a nie istnienia go w świecie.
- Reklamy tła mają ograniczony zasób fraz, więc wiele z nich to duplikaty; realne tło byłoby bardziej zróżnicowane.

## Do zrobienia

- Slajdy i figury końcowe w `artifacts/pitch/`.
- Test Streamlit w przeglądarce (`fejki app`).
- Token Meta, test `ads_archive`, schemat JSON Listy CERT (parser jest tolerancyjny).
- Strojenie `edge_cos_min` i wariant trudniejszej syntetyki.
- Wartości `[N]` ze SPEC nadal niezweryfikowane (pola API, daty hackathonu).
