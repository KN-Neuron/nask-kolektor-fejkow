# 07. Budowa zbiorów danych poza Metą (do treningu i testów)

Problem: oficjalny zbiór ma 10 przypadków, a ocena odbywa się na ukrytym zbiorze z nowymi wariantami znanych kampanii
i z innymi kampaniami. Do kalibracji i treningu potrzebujemy setek przypadków **z etykietą kampanii** oraz **trudnych
negatywów**. Zasada zespołu bez zmian: **nie odwiedzamy stron oszustów**. Korzystamy z przechwyceń zrobionych przez
kogoś innego (urlscan.io, Wayback Machine) i z publicznych list.

## Główny pomysł: etykiety z infrastruktury, model z treści

Mocne ślady techniczne (ten sam piksel, ten sam zestaw stron, schemat `utm_visit`, rejestracja domen w odstępie minut)
dają **etykiety kampanii/zestawu „za darmo”**. Na nich uczymy model, który rozpoznaje tę samą kampanię **po treści
i obrazie, bez śladów technicznych**. To odpowiedź na naszą największą lukę: same zrzuty ekranu dziś niczego nie łączą,
a ukryty zbiór organizatora może mieć materiały bez HAR.

## Źródła

| Źródło | Co daje | Etykieta | Stan |
|---|---|---|---|
| **urlscan.io** (wyszukiwarka publicznych skanów) | bez klucza: adres z parametrami, tytuł, wiek domeny i certyfikatu, ASN, język, zrzut; z kluczem: lista żądań (~HAR), przekierowania, DOM | pivot po śladzie (zestaw, TDS, tytuł) = grupa | ✅ kolektor `fejki urlscan collect` |
| Lista Ostrzeżeń CERT Polska (hole.cert.pl) | domeny oszustw w PL | „oszustwo” (bez kampanii) | adapter `ingest/cert.py`; do połączenia z urlscan (wyszukiwanie po domenie) |
| Lista ostrzeżeń publicznych KNF | nazwy fałszywych „platform inwestycyjnych” | słownik produktów | do zrobienia |
| Raporty firm bezpieczeństwa z listami IoC (CERT Polska, ESET, Check Point, Infoblox, Group-IB…) | listy domen przypisane do jednej kampanii/operatora | **najlepsze etykiety kampanii** | do przejrzenia (nie sprawdzaliśmy jeszcze, które dotyczą PL) |
| Wayback Machine | zarchiwizowane HTML domen z list | jak lista źródłowa | do zrobienia |
| Google Ads Transparency (BigQuery), TikTok Commercial Content API, DSA Transparency Database | kreacje, reklamodawcy, decyzje moderacji | reklamodawca / kategoria | patrz [06_DOSTEP_DO_REKLAM.md](06_DOSTEP_DO_REKLAM.md) |
| Zbiory akademickie phishingu ze zrzutami i marką (np. z prac Phishpedia/PhishIntention) | zrzuty + podrabiana marka | marka | do kanału wizualnego (zadanie B4) |
| Warianty syntetyczne z przypadków organizatora | inna domena, parafraza, podmiana osoby/produktu, kompresja i przycięcie zrzutu, usunięcie HAR | ta sama kampania | do zrobienia (zadanie A2) |
| Trudne negatywy | prawdziwe artykuły z podrabianych portali (Gazeta.pl, TVN24), legalne reklamy inwestycyjne i suplementów, inne oszustwa z tymi samymi twarzami | negatyw | ✅ częściowo (pivoty `neg-*` w urlscan) |
| Własne zrzuty z feedów zespołu | zrzut + identyfikator z Ad Library, format jak u organizatora | ręczna | szablon w `data/` |

## urlscan.io w praktyce

```bash
cd code
fejki urlscan search 'filename:"aio-static/sdk/main.js"'   # podgląd zapytania
fejki urlscan collect                                       # pivoty z config/urlscan_pivots.yaml → ../data/urlscan/<uuid>/
fejki urlscan eval                                          # osobny indeks + B-cubed względem etykiet pivotów
```

- Pivoty definiujemy w `code/config/urlscan_pivots.yaml` (etykieta, zapytanie, limit, `kind: pozytyw|negatyw`).
  Składnia zapytań: https://urlscan.io/docs/search/ (`page.domain:`, `domain:`, `page.title:`, `page.url:`,
  `filename:`, `hash:`, `ip:`, `asn:`).
- Każdy skan zapisujemy jako **folder przypadku** (`urlscan.json`, `screenshot.png`, z kluczem `dom.html`). Demonstrator
  czyta go bez zmian (`fejki demo build ../data/urlscan`). Etykiety: `../data/urlscan/labels.csv`.
- `max_per_domain` (domyślnie 2) ogranicza powtórzone skany tej samej strony.
- **Nigdy nie zlecamy nowych skanów** (`/scan/`): to byłaby wizyta na stronie oszustów w naszym imieniu i publikacja wyniku.
  Test `tests/test_urlscan.py` pilnuje, że kolektor nie woła tego adresu.
- Klucz API (darmowe konto, zakłada osoba z zespołu): `URLSCAN_API_KEY` w `code/.env`. Daje pełny log żądań i DOM,
  czyli dane w formacie najbliższym zbiorowi organizatora.
- Dane z urlscan to dane stron trzecich: zostają lokalnie (`data/urlscan/` w `.gitignore`). W metodyce i pitchu podajemy
  źródło (wymóg opisu wyzwania, pkt 8). Przed szerszym użyciem sprawdzić warunki korzystania z API urlscan.

Pierwsze wyniki zapytań (2026-11-21, bez klucza): zestaw `aio-static/sdk` ma **318 publicznych skanów** (także
niemieckojęzyczne kopie, np. „Verdienen Sie über €950 täglich”, domeny w wieku 3 dni), `utm_visit` ma 47, „Uromexil Forte”
ma 5; domeny z oficjalnego zbioru same w sobie nie mają skanów.

**Pierwszy zbiór (2026-11-21, bez klucza):** 122 przypadki: 71 `zestaw-aio-sdk`, 45 `tds-utm-visit`, 4 `uromexil-forte`,
2 negatywy `neg-tvn24` (Gazeta.pl nie miała skanów). `fejki urlscan eval` (próg 0,7): **sieć: B-cubed P 0,976, R 0,448,
F1 0,614; kampania: P 0,992, R 0,063**; żaden negatyw nie doklejony. Czułość jest niska, bo bez klucza nie widać listy
żądań (ślad `/aio-static/sdk` jest w żądaniach, nie w adresie strony), a tekst to tylko tytuł. Grupa „uromexil-forte” to
strony z różnych krajów (HU, SK, IT), czyli etykieta „produkt”, nie jedna kampania.

## Co trenować

1. **Model podobieństwa par** (regresja logistyczna albo mały gradient boosting) na wynikach kanałów zamiast ręcznych wag
   z `W`. Wagi uzasadnione danymi, model nadal wyjaśnialny (wkład kanału = przesłanka).
2. **Embedding zrzutów i tekstu dostrojony kontrastowo** (CLIP/SigLIP, bge-m3): pary z tej samej grupy pivotu blisko, trudne
   negatywy daleko. Uczymy bez kanałów technicznych, żeby działał na „samym zrzucie”.
3. **Podział po kampaniach** (cała grupa w treningu albo w teście); przypadki organizatora **tylko do testu**.

## Ryzyka

- etykiety z pivotów technicznych są słabe: zestaw stron bywa sprzedawany wielu operatorom (wtedy „grupa” = narzędzie,
  nie kampania). Do pomiaru jakości używamy etykiet z raportów IoC i ręcznie sprawdzonej próbki;
- przesunięcie domeny: urlscan ma dużo skanów z innych krajów i języków; trzeba ważyć polskie przypadki;
- limity i warunki API urlscan; bez klucza nie ma logu żądań ani DOM, więc kanały adresów i szablonu są uboższe.
