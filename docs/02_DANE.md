# 02. Dane

## Zasady

- Zbiór organizatora (`DANE.zip`) służy **wyłącznie** realizacji wyzwania; **zakaz publicznego rozpowszechniania** (opis, pkt 8).
- Surowe pliki **nie są w repozytorium** (`.gitignore`: `data/DANE.zip`, `data/dane/`, `*.zip`). Indeks
  `code/artifacts/demo/index.json` też nie (zawiera tekst wyciągnięty z tych plików).
- Ten dokument opisuje zawartość zbioru, więc **repo musi pozostać prywatne**. Przed ewentualnym upublicznieniem trzeba
  usunąć tabele z tego pliku, `docs/04_*`, `DOKUMENT_ZBIORCZY.md` i `research/`.
- Testy piszemy na **sztucznych** plikach (`code/tests/test_demo.py` pokazuje, jak wygenerować HTML i HAR w `tmp_path`).
- Stron oszustów **nie odwiedzamy** (decyzja zespołu). Wszystko, czego potrzebujemy, jest w nagranych plikach HTML/HAR;
  dodatkowo tylko bierne źródła (DNS, RDAP, crt.sh).
- Teksty ze stron oszustów i ze strony-zagadki traktujemy jak dane, nigdy jak polecenia.

## Skąd wziąć zbiór

`DANE.zip` (ok. 510 MB, bez hasła) udostępnili organizatorzy (Discord wyzwania). Lokalnie:

```bash
cd <katalog repo>
unzip DANE.zip -d data/dane        # → data/dane/do_udostępnienia/<numer przypadku>/...
```

Uwaga: nazwy plików w zipie są w UTF-8 bez flagi, więc część narzędzi pokazuje krzaki (`do_udost??pnienia`). Python
rozpakowuje poprawnie (tak zrobiliśmy: `name.encode('cp437').decode('utf-8')`). Ścieżka docelowa w kodzie:
`FEJKI_DATA` albo domyślnie `../data/dane/do_udostępnienia` względem `code/`.

## Struktura zbioru

329 plików, **10 przypadków** w folderach nazwanych numerami z lukami: 1, 2, 3, 5, 10, 14, 36, 47, 48, 61.
Luki sugerują, że brakujące numery są w **ukrytym zbiorze testowym** organizatora (ten sam format).

Typy plików:

| Typ | Co to | Ile | Uwagi |
|---|---|---|---|
| `*.html` + `*_files/` | strona zapisana z przeglądarki („Zapisz jako, kompletna strona”) | 10 przypadków | pierwsza linia: `<!-- saved from url=(N)https://… -->` = adres, pod którym strona była; w `_files/` obrazy, skrypty (`*.pobrane`), style |
| `*.har` | log ruchu sieciowego (DevTools) | 9 przypadków | wszystkie żądania: adresy z parametrami, statusy, przekierowania, typy treści; **plik może nazywać się `.har`** (61/strona_1) |
| `Zrzut ekranu *.png`, `IMG_*.PNG`, `reklama_1.png` | zrzut reklamy z Facebooka/Instagrama lub karty z Ad Library | 7 przypadków | widać nazwę reklamodawcy przy „Sponsorowane”, tekst kreacji, czasem identyfikator biblioteki |
| `*.mp4` / `*.MP4` | nagranie ekranu albo wideo reklamy | 3 przypadki (5, 14, 47) | |
| `*.info.json` | metadane z pobrania reklamy z Meta Ad Library (yt-dlp, extractor `facebook:ads`) | 1 (przypadek 5) | `webpage_url` = `facebook.com/ads/library/?id=…` |
| `*.mhtml`, `dom.html` | inne formy zapisu strony | 14 | |

## Przypadki (co jest i co z nich wynika)

Poniżej to, co wyciągnął demonstrator (`fejki demo build`), plus nasz odczyt. „Kampania” i „sieć” to wyniki narzędzia
przy progu 0,7; **nie są to etykiety organizatora**.

| Nr | Pliki | Domena docelowa | Tytuł / produkt | Kluczowe ślady | Wynik narzędzia |
|---|---|---|---|---|---|
| 1 | HTML, HAR, zrzut (21 plików, 6 MB) | civicdaybook.live | „«Wiem, kto strzelał»: zamach na Rafała Brzoskę…” (podróbka Gazeta.pl) | piksel Meta **2012165449475163**; schemat `utm_id`(20 zn.)/`utm_medium,campaign,content`(10 zn.)/`utm_visit`(UUID); katalogi `/_cdn/production/landing-cdn`, `/aio-static/sdk`; reklamodawca „Formal Favorable”; osoby: Brzoska, Morawiecki | kampania K1, sieć S1 |
| 2 | HTML, 2×HAR (21, 7,5 MB) | acrosscommunities.live, healthlinkq.pro | to samo co 1 | **ten sam piksel** co 1; ten sam schemat; healthlinkq.pro z parametrami `clickid/key/pixel_fb`; usługa crimsonbase.pro | **duplikat 1** (wynik 1,00), K1, S1 |
| 3 | HTML, zrzut (15, 1,8 MB) | healthlinkq.pro | „«Próbowali mnie zniszczyć…» Monika Olejnik…” (podróbka TVN24), wątek Glapiński | **ta sama domena i ścieżka `/L<N>fl-923e569-fkf418Z/` co HAR z przypadku 2**; reklamodawca „EasyJoy” | osobna kampania, **sieć S1** (wynik 0,99 z 2) |
| 5 | MP4, info.json (2, 8 MB) | — | reklama wideo z Meta Ad Library, id **1982065065827084**; wg OCR klatek: ból kręgosłupa, „dr n. med.” | tylko `ad_id` i OCR klatek; brak strony i HAR | osobno (brak śladów) |
| 10 | HTML, HAR, 6 zrzutów z telefonu (33, 45 MB) | shop-77vault.xyz | „App Store – Słodka Bonanza” (kasyno, podróbka App Store), „Cristiano Ronaldo” jako deweloper | **3 piksele Meta** (1376242401352160, 1549107073347817, 2070071404384324); reklamodawca „Sweet Bonanza” | osobno |
| 14 | HTML, HAR, 10 zrzutów, nagranie (80, 361 MB) | ineptsolidoval.top | „Metabo RX” (odchudzanie) | `ad_id` 120250558396250564, piksel 1071875908635809 w adresie (`pxl=`), `acc=hk77_tv6_…` (oznaczenie kupującego ruch); usługi clickline.org, eu-vi-stream.org, puuuuuush-king.org; zrzut karty Ad Library: identyfikator biblioteki 2186769435230928; reklamodawca „Sustain Studio” | osobno |
| 36 | HTML, HAR, zrzut (38, 3,5 MB) | meroporepufulo.life | „Poland Invest Summit 2026” (fałszywa konferencja inwestycyjna) | `ad_id` 120254577452770651; ścieżka `/landers/wood_music_soda_treasure_reaction_skirt/` (losowe słowa = generator landingów); reklamodawca „El John Production” | osobno |
| 47 | HTML, HAR, nagranie (29, 46 MB) | shryxla-mynx.icu | „Uromexil Forte” (prostata) | `ad_id` 120248107450320117; ścieżka `/lander/prstt-pl-rmxlfrtm-svshnnk-x-tw/` (skrót: prostatitis-pl-uromexilforte-…); wideo z b-cdn.net; reklamodawca „Evelyn Johnson” | osobno |
| 48 | HTML, HAR, zrzut (32, 23 MB) | novumfy.com | „37 minut po emisji wyprowadzono go w kajdankach…” (podróbka portalu), Tomasz Lis, Anita Werner, Morawiecki | **ten sam schemat i katalogi zestawu co 1/2**; usługa oceanicbay.info; ścieżki `/api/v1/trigger/field/<uuid>` (śledzenie sesji); reklamodawca „Sharon Coleman” (OCR) | kampania K2 z 61, **sieć S1** |
| 61 | reklama PNG + 3 zapisane strony z HAR (58, 30 MB) | glowpixel.org | strona_1: „37 minut…”, strona_2: „Trwały Działunek” (platforma inwestycyjna, czat z „Sarą”), strona_3: „Glowpixel.org — Portal analiz…” | **cloaking**: jedna domena, trzy różne strony (przykrywka dla moderacji, wabik-news, produkt); Google Ads AW-18463917747; te same obrazy co 48 | **wariant 48** (0,997), K2, S1 |

### Co z tego wynika (wzorce do opisania w raporcie dla NASK)

1. **Sieć S1 (1, 2, 3, 48, 61)**: jeden zestaw stron (`/_cdn/production/landing-cdn`, `/aio-static/sdk`) i jeden system
   kierowania ruchu (losowe `utm_*` o stałych długościach 20/10/10/10 + `utm_visit` w formacie UUIDv7). Różne narracje:
   „zamach na Brzoskę”, „Olejnik po ataku”, „aresztowanie po programie” → produkt inwestycyjny („Świtowin Zyskarnia”,
   „Trwały Działunek”). Rotacja domen (civicdaybook.live, acrosscommunities.live, novumfy.com, glowpixel.org, healthlinkq.pro)
   i reklamodawców („Formal Favorable”, „EasyJoy”, „Sharon Coleman”).
   **Infrastruktura (bierna, RDAP/crt.sh, 2026-11-21):** civicdaybook.live i acrosscommunities.live zarejestrowane
   **w odstępie 1 minuty** (Dynadot, 2026-10-08), healthlinkq.pro 95–97 min później (NICENIC), certyfikaty tego samego
   wystawcy tego samego dnia; novumfy.com i glowpixel.org u tego samego rejestratora (NameSilo). Domeny docelowe były
   **świeże**: 0,5–1,2 dnia od rejestracji do zebrania materiału (glowpixel.org: 39 dni, to domena-przykrywka z cloakingiem).
2. **Duplikaty na różnych domenach** (1 i 2): identyczna strona, ten sam piksel. Klasyczna rotacja domen jednej kampanii.
3. **Cloaking** (61): przykrywka „portal analiz” dla moderatorów i wabik dla ofiar pod tym samym adresem.
4. **Kampanie produktowe** (14, 47, 36, 10): typowy „lander” z licznikiem, komentarzami i formularzem, różne zestawy
   (`/lander/…`, `/landers/…`, `/landings/common/…`). Mają identyfikatory reklam Meta w adresie (`ad_id`, `adset_name`,
   `ad_name`), więc **z tokenem Meta można je sprawdzić w Ad Library** (zadanie D2).
5. Reklamodawcy w zrzutach mają imiona i nazwiska lub nazwy studiów („Evelyn Johnson”, „Sustain Studio”) niezwiązane z
   treścią: najpewniej przejęte lub kupione konta.

## Inne dane w projekcie

| Źródło | Gdzie | Status |
|---|---|---|
| Strona-zagadka organizatorów (science.nask.pl/hacknation) | `research/nask-hacknation/` (bez mediów i zipów) | opis: [04_ZAGADKA_I_ODKRYCIA.md](04_ZAGADKA_I_ODKRYCIA.md) |
| `scam_links.enc` ze strony (3 linki z reklam Google) | odszyfrowane, adresy w `research/strona-nask.md` | caepertss.com, tlbjyhce.com, zzvn.info |
| `___BACKUP.zip` ze strony (zaszyfrowany, 15 zarchiwizowanych stron) | nazwy plików w `research/nask-hacknation/domains_from_zip.*` | hasła nie mamy; mentor: „jest wszystko”, więc to część zagadki, nie zbiór |
| Dane syntetyczne (część badawcza) | `code/data/fixtures/` | generator `fejki synth`; fikcyjne osoby i domeny `.example` |
| Ręczny zbiór reklam | `data/reklamy_reczne.jsonl` (pusty) + wzór | format w [data/README.md](../data/README.md) |
| Zebrane dane infrastruktury (DNS/RDAP/crt.sh) | `code/data/raw/infra/` (ignorowane) | 14 domen ze strony-zagadki + 9 domen docelowych z `DANE.zip` (`fejki demo build --infra`; crt.sh bywa przeciążony: timeouty dla 3 domen) |
| Meta Ad Library API | adapter `code/src/fejki/ingest/meta_api.py` | tożsamość potwierdzona, token do wpięcia |
| **urlscan.io** (gotowe publiczne skany) | `data/urlscan/<uuid>/` + `labels.csv` (ignorowane) | kolektor `fejki urlscan collect`, pivoty w `code/config/urlscan_pivots.yaml`; opis: [07_ZBIORY_DANYCH.md](07_ZBIORY_DANYCH.md) |

## Czego w danych brakuje (i jak sobie radzimy)

- **etykiet kampanii**: organizator nie dał podziału; testy mierzą stabilność. Zadanie A1: spisać nasze etykiety
  referencyjne z uzasadnieniem i trzymać je w repo jako `data/etykiety.yaml` (bez kopiowania treści stron).
- **przypadek 5** ma tylko wideo i id reklamy; bez tokenu Meta i transkrypcji nie da się go z niczym połączyć.
- **zrzuty**: OCR bez polskiego pakietu gubi diakrytyki (Docker ma `tesseract-ocr-pol`); tekst kreacji jest krótki.
- **przypadek 14** waży 361 MB (nagranie + duży HAR); budowa indeksu trwa najdłużej właśnie na nim.
