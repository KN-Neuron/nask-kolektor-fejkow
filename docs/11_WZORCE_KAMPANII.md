# 11. Wzorce kampanii oszukańczych (wiedza dla NASK, pkt 10 opisu wyzwania)

Opis wzorców zidentyfikowanych w zbiorze organizatora (10 przypadków) i w danych dodatkowych. Każde twierdzenie ma wskazane
źródło w danych. Nie są to etykiety organizatora, tylko nasz odczyt; poziom pewności podany przy każdym wzorcu.
**Dokument opisuje dane organizatora, więc podlega zakazowi rozpowszechniania (repo prywatne).**

## Wzorzec 1: sieć „fałszywy news → platforma inwestycyjna” (przypadki 1, 2, 3, 48, 61)

**Pewność: wysoka** (kilka niezależnych śladów, potwierdzone infrastrukturą).

| Element | Obserwacja |
|---|---|
| Wabik | podrobiony portal informacyjny (Gazeta.pl, TVN24, portal z „kajdankami”); sensacyjny tytuł o znanej osobie (zamach na Brzoskę, atak na Olejnik, aresztowanie po programie) |
| Cel | platforma inwestycyjna („Świtowin Zyskarnia”, „Trwały Działunek”), formularz, wpłata od 250–1000 zł |
| Zestaw stron | wspólne katalogi `/_cdn/production/landing-cdn` i `/aio-static/sdk`; ten sam szablon na różnych domenach |
| Kierowanie ruchu | ten sam schemat parametrów: `utm_id` (20 znaków losowych), `utm_medium`, `utm_campaign`, `utm_content` (po 10), `utm_visit` (UUIDv7) |
| Rotacja | domeny: civicdaybook.live, acrosscommunities.live, novumfy.com, glowpixel.org, healthlinkq.pro; reklamodawcy: „Formal Favorable”, „EasyJoy”, „Sharon Coleman” |
| Życie domen | rejestracja w odstępie ~1 minuty (civicdaybook.live / acrosscommunities.live), następna po ~95 minutach (healthlinkq.pro); materiał zebrany 0,5–1,2 dnia po rejestracji |
| Dowód operatora | wspólny piksel Meta 2012165449475163 (przypadki 1 i 2); ta sama domena healthlinkq.pro (2 i 3); te same obrazy (48 i 61; przypadek 3 nie ma wspólnych obrazów z żadnym innym, sprawdzone po pHash i nazwach plików) |

**Wzorzec w wariantach:** ta sama strona na kilku domenach (duplikat), ta sama historia z innym produktem (wariant), różne
historie z tym samym zestawem stron (sieć). Rozróżnienie „kampania / sieć” w narzędziu odpowiada tej strukturze.

## Wzorzec 2: cloaking („portal analiz” jako przykrywka) (przypadek 61)

**Pewność: wysoka.** Jedna domena (glowpixel.org) serwuje trzy różne strony: wabik-news, stronę produktu i niewinny „Portal
analiz produkcji medialnej”. Ma to ukryć treść przed moderacją i skanerami. Domena starsza od pozostałych (39 dni).
Narzędzie wykrywa to jako „ta sama domena, różne strony”.

## Wzorzec 3: landery produktowe z licznikiem (przypadki 14, 47, 36, 10)

**Pewność: średnia** (nie znaleźliśmy wspólnych śladów między nimi, więc to osobne kampanie, a nie jedna sieć).
Typowe cechy: licznik promocji, „zostało 17 sztuk”, fałszywe komentarze, formularz zamówienia, autorytet („dr n. med.”).
Tematy: odchudzanie (Metabo RX), prostata (Uromexil Forte), fałszywa konferencja inwestycyjna, kasyno udające App Store.
Adresy zawierają makra reklamowe Meta (`ad_id`, `adset_name`, `ad_name`, `pxl`, `acc=`), więc reklamy dają się powiązać
z Ad Library. Ścieżki zestawów mają skrócone nazwy kampanii (np. `/lander/prstt-pl-rmxlfrtm-svshnnk-x-tw/`).

## Wzorzec 4: konta reklamowe z przypadkowymi nazwami

**Pewność: średnia.** Reklamodawcy na zrzutach to imiona i nazwiska lub nazwy studiów niezwiązane z treścią („Evelyn Johnson”,
„Sustain Studio”, „El John Production”), co sugeruje przejęte lub kupione konta. W Meta Ad Library 15 862 z 97 447 zebranych
reklam (16%) ma treść zastąpioną komunikatem o usunięciu przez Metę, a strony tych reklamodawców mają przypadkowe nazwy.

## Wzorzec 5: kopie tych samych zestawów w wielu krajach

**Pewność: średnia.** Skany urlscan: zestaw `/aio-static/sdk/main.js` ma 318 publicznych skanów, także niemieckojęzycznych
(„Verdienen Sie über €950 täglich”), na domenach w wieku kilku dni. Ten sam zestaw obsługuje wiele kampanii i operatorów, więc
**wspólny zestaw strony jest dowodem „narzędzia”, nie koniecznie „operatora”**. Dlatego sieć wymaga kilku niezależnych śladów.

## Czego NIE ustaliliśmy

- hipoteza „schemat perswazji odróżnia operatorów” (LEACE na bge-m3) **nie potwierdziła się**: po usunięciu tematu wszystkie
  strony oszustw zbliżają się do siebie (zostaje wspólny „język oszustwa”), a odstęp między sieciami maleje;
- reklamy ze zbioru organizatora nie istnieją już w Meta Ad Library (krótkie życie, usunięcia), więc nie odtworzyliśmy ich dat emisji;
- definicja „kampanii” u organizatora (narracja czy operator) nie jest znana; raportujemy oba poziomy.

## Źródła metadanych użyteczne dla analityków (zweryfikowane w projekcie)

| Źródło | Co daje | Uwagi |
|---|---|---|
| log HAR strony | parametry adresu, przekierowania, usługi zewnętrzne, znaczniki czasu | najbogatsze źródło; schemat TDS i zestaw stron |
| RDAP, crt.sh, DNS | data i rejestrator domeny, certyfikaty, serwery nazw, IP | rejestracja w odstępie minut = masowa rejestracja |
| piksele i identyfikatory reklam w kodzie i adresach | wspólne konto reklamowe | bardzo silny dowód |
| Meta Ad Library API | tekst, strona i płatnik, daty, reklamy usunięte | bez pobierania po identyfikatorze; token wygasa po godzinach |
| urlscan.io | gotowe skany: adres, tytuł, wiek domeny, zrzut | pivot po zestawie stron daje setki przypadków |
| Lista Ostrzeżeń CERT Polska | etykiety domen | do testu wyprzedzenia |

## Rekomendacje dla narzędzi NASK

1. Grupować po **schemacie parametrów adresu** i **katalogach zestawu stron**, nie po treści (treść zmienia się najszybciej).
2. Traktować **wiek domeny przy pierwszym zgłoszeniu** (godziny, dni) jako cechę priorytetyzacji.
3. Raportować osobno „kampanię” (przekaz) i „sieć” (operator); pierwsza zmienia się szybciej niż druga.
4. Wyszukiwać w Meta Ad Library po **stronach reklamodawców**, nie tylko po słowach kluczowych (słowa kluczowe gubią reklamy z celebrytami).
5. Dla każdej powiązanej domeny proponować ją analitykowi do weryfikacji z uzasadnieniem (karta kampanii).
