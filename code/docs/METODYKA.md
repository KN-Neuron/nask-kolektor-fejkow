# Kolekcjoner Fejków: metodyka demonstratora

Wyzwanie „Follow the Fake” (HackNation × NASK). Narzędzie łączy pojedyncze materiały z podejrzanych reklam w kampanie
i dla każdego powiązania podaje przesłanki. Nie jest detektorem pojedynczego fejka.

## 1. Wejście

| Rodzaj | Co z niego bierzemy |
|---|---|
| folder przypadku (jak w zbiorze organizatora) | wszystko poniżej, łącznie |
| zapis strony HTML (z folderem `_files`) | tytuł, widoczny tekst, adres zapisu (`saved from url`), linki, piksele w kodzie, klasy HTML, obrazy |
| log ruchu HAR | wszystkie adresy (parametry, ścieżki, usługi zewnętrzne), przekierowania 3xx |
| zrzut ekranu / kreacja | OCR (Tesseract), pHash, nazwa reklamodawcy („… Sponsorowane”) |
| nagranie (mp4) | klatki co 3 s (ffmpeg): OCR i pHash |
| `info.json` (np. z Meta Ad Library) | identyfikator reklamy, tytuł, opis |
| adres URL | analiza bierna: domena, schemat parametrów, identyfikatory reklam i pikseli, wzorzec ścieżki; opcjonalnie DNS/RDAP/crt.sh |
| tekst / nazwa produktu | słowa kluczowe, osoby, tematyka, dopasowanie nazw produktów |

Brak dowolnego elementu nie przerywa analizy: materiał dostaje listę braków, a porównanie korzysta z dostępnych kanałów.
**Stron oszustów nie odwiedzamy.** Korzystamy z plików nagranych przez organizatora i z biernych, publicznych źródeł.

## 2. Cechy (kanały)

- **tekst**: TF-IDF słów i bigramów na tytułach (waga ×3) i treści, polskie znaki ujednolicone (OCR bez pakietu `pol` je gubi);
  w uzasadnieniu pokazujemy najmocniej wspólne słowa;
- **osoby**: mała baza osób publicznych (`config/osoby.txt`); pełne imię i nazwisko z polską odmianą, aliasy tylko dla nazwisk
  jednoznacznych (np. „Lewandowski” wymaga imienia, „Lewandowska” nie łapie „Lewandowski”);
- **produkt**: krótki tytuł strony nie będący nagłówkiem newsa; dopasowanie także gdy nazwa pada w treści drugiego materiału;
- **reklamodawca**: nazwa strony przy „Sponsorowane” odczytana ze zrzutu reklamy;
- **śledzenie**: identyfikatory reklam Meta (`ad_id`, link do Ad Library), piksele Meta (`fbq('init')`, `pxl=`, `facebook.com/tr?id=`),
  Google Ads / GTM, oznacznik konta w adresie (`acc=`);
- **adres**: schemat parametrów jako odcisk systemu kierowania ruchu (np. losowe `utm_id` 20 znaków, `utm_medium/campaign/content`
  10 znaków, `utm_visit` UUID), wzorce ścieżek z podmienionymi identyfikatorami, charakterystyczne katalogi zestawów stron,
  nietypowe usługi zewnętrzne (pomijamy CDN-y i usługi masowe), cele przekierowań;
- **domena**: domena docelowa (adres zapisu strony, nazwa pliku HAR);
- **obraz**: pHash (DCT 32×32 → 64 bity) zrzutów, kreacji, klatek i obrazów użytych na stronach;
- **szablon strony**: zbiór klas HTML (Jaccard) oraz wykrywanie cloakingu (ta sama domena serwuje różne strony);
- **tematyka**: słownik (fałszywy news, inwestycje, zdrowie, hazard, sklep); bardzo słaby sygnał;
- **infrastruktura** (opcjonalnie, wymaga sieci): DNS, ASN (Team Cymru), RDAP, dziennik certyfikatów crt.sh; reguły: wspólny
  adres IP (słaby, jeśli CDN), ten sam zestaw serwerów nazw, podsieć /24, rejestracja w krótkim odstępie, ten sam certyfikat.

## 3. Podobieństwo

Każdy kanał zwraca dowody `(kod, kanał, waga, opis)`. Wynik pary:

1. noisy-OR wag w obrębie kanału (osoby z limitem 0,5),
2. noisy-OR między kanałami: `1 − Π(1 − p_kanał)`.

Cechy pospolite tracą wagę (`2 / liczba materiałów z cechą`, gdy cechę ma więcej niż 2 materiały), więc ta sama znana twarz
w wielu kampaniach nie skleja ich sama. Wagi (`fejki.demo.similar.W`) ustawiliśmy ręcznie według specyficzności sygnału:
identyfikator reklamy 0,95, piksel 0,9, ta sama domena 0,9, niemal identyczny tekst 0,9, wspólny wzorzec ścieżki 0,7,
schemat parametrów 0,6, osoba 0,3, tematyka 0,1.

Relacja pary: **duplikat** (ten sam identyfikator reklamy albo tekst ≥ 0,95 z tym samym tytułem/domeną/obrazem),
**wariant tego samego przekazu** (tekst ≥ 0,6, ten sam tytuł lub produkt, albo podobny szablon i tekst ≥ 0,4),
**wspólna infrastruktura / operator** (tylko ślady techniczne), **podobieństwo treści**.

## 4. Grupowanie

- **kampania**: składowe spójne krawędzi typu duplikat/wariant z wynikiem ≥ próg (domyślnie 0,7);
- **sieć**: składowe spójne wszystkich krawędzi ≥ próg, czyli kampanie prawdopodobnie jednego operatora.

## 5. Nowy materiał

Porównanie z każdym materiałem zbioru, wynik kampanii = najsilniejsze powiązanie z jej członkiem. Decyzja:
przypisanie do kampanii (ten sam przekaz ≥ próg) · nowy przekaz w znanej sieci (tylko infrastruktura ≥ próg) ·
możliwe powiązanie do weryfikacji (≥ 0,4) · nowy wzorzec.

## 5a. Karta kampanii (`fejki demo cards`, zakładka „Kampanie i sieci”)

Dla każdej kampanii: materiały i sieć operatora, **okno obserwacji** (najwcześniejszy i najpóźniejszy znacznik czasu:
`startedDateTime` z logów HAR, daty RRRR-MM-DD z nazw zrzutów i nagrań przeliczone z czasu polskiego na UTC, `timestamp`
z `info.json`; niejednoznaczne formaty jak `08-12-2026` pomijamy), tematyka, osoby, produkty, reklamodawcy, identyfikatory
reklam i pikseli, **domeny do weryfikacji** z priorytetem i uzasadnieniem:

| Priorytet | Rola domeny |
|---|---|
| wysoki | domena docelowa reklamy w tej kampanii |
| średni | nietypowa usługa zewnętrzna ładowana przez stronę kampanii; cel przekierowania; domena innej kampanii tej samej sieci |

Z kanałem infrastruktury karta podaje datę rejestracji, rejestratora i **wiek domeny przy pierwszej obserwacji**
(≤ 7 dni = „świeża domena”). Okno to czas zebrania materiałów, nie czas emisji reklam; daty emisji da Meta Ad Library.
Eksport: Markdown (karta lub wszystkie) i CSV domen do weryfikacji.

## 6. Testy (`fejki demo eval`)

Nie mamy etykiet kampanii od organizatora, więc „oczekiwane” = wynik na pełnym zbiorze. Test mierzy stabilność i odporność,
nie trafność względem podziału organizatora.

- **pomiń-jeden** (10 przypadków): każdy przypadek dopasowany jako nowy do reszty zbioru. Wynik: spójność kampanii 100%, sieci 100%;
  pojedyncze przypadki nie zostały doklejone do żadnej grupy.
- **niepełne wejście**: sam HTML albo sam HAR trafia do właściwej sieci we wszystkich sprawdzonych przypadkach (1, 2, 3, 48, 61).
  **Same zrzuty ekranu nie wystarczają** (0 z 4): zrzut reklamy ma mało tekstu, a w zbiorze nie ma drugiego podobnego zrzutu.
- testy jednostkowe na sztucznych plikach: `pytest tests/test_demo.py`.

## 7. Ograniczenia

- wagi i progi ustalone ręcznie, na małym zbiorze (10 przypadków);
- OCR bez polskiego pakietu gubi diakrytyki (obraz Dockera instaluje `tesseract-ocr-pol`);
- osoby rozpoznajemy po nazwiskach w tekście i OCR; bez rozpoznawania twarzy;
- transkrypcja mowy z nagrań nie jest włączona (klatki tak);
- kanał infrastruktury wymaga dostępu do sieci; bez niego działa reszta;
- schemat parametrów jest silnym sygnałem zestawu oszustów, ale te same zestawy mogą być sprzedawane wielu operatorom.

## 8. Biblioteki, usługi i licencje

| Składnik | Licencja | Do czego |
|---|---|---|
| Streamlit | Apache-2.0 | interfejs |
| pandas, NumPy, SciPy, scikit-learn | BSD-3 | dane, pHash (DCT), TF-IDF |
| pydantic, typer, rapidfuzz, PyYAML, plotly | MIT | modele danych, CLI, dopasowania rozmyte |
| networkx, httpx, tldextract, python-dotenv, lxml | BSD-3 | grafy, HTTP do RDAP/crt.sh, domeny |
| pyvis (z vis-network) | BSD-3 (vis-network: Apache-2.0/MIT) | graf powiązań |
| Beautiful Soup | MIT | parsowanie HTML |
| Pillow | MIT-CMU (HPND) | obrazy |
| pytesseract, Tesseract OCR | Apache-2.0 | OCR |
| FFmpeg | LGPL-2.1+ (zależnie od kompilacji GPL) | klatki z nagrań |
| dnspython | ISC | DNS |

Usługi zewnętrzne (tylko kanał infrastruktury, opcjonalnie): publiczne serwery DNS, Team Cymru IP-to-ASN (DNS), rdap.org,
crt.sh. Nie wymagają kluczy. **Meta Ad Library API** (opcjonalnie, do sprawdzania `ad_id`): wymaga potwierdzenia tożsamości
(facebook.com/ID), akceptacji warunków na facebook.com/ads/library/api, aplikacji deweloperskiej i tokenu w `.env`
(`META_ACCESS_TOKEN`); dla reklam komercyjnych w UE API zwraca ograniczony zestaw pól.

## 9. Dane

Zbiór organizatora (`DANE.zip`) służy wyłącznie realizacji wyzwania i nie może być publicznie rozpowszechniany. Nie jest częścią
repozytorium ani obrazu Dockera: podaje się go przy uruchomieniu (`FEJKI_DATA` lub wolumen `/data`). Indeks
(`artifacts/demo/index.json`) zawiera cechy wyciągnięte z tych danych, więc też nie trafia do repozytorium.
