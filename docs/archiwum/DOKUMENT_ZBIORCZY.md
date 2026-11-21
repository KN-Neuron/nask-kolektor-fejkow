# Kolekcjoner Fejków (Follow the Fake): dokument zbiorczy

Stan na 2026-11-21. Hackathon HackNation x NASK. Wszystko, co mamy, w jednym miejscu: zadanie, nasz pomysł, kod, dostęp do reklam, to, co dali organizatorzy, wyniki, ryzyka i kolejne kroki.
Pliki projektu: `/Users/gsk/documents/projects/kolekcjoner-fejkow/` (kod w `code/`, materiały w `research/`, dane w `data/`).

---

## 0. Aktualizacja (2026-11-21, popołudnie): demonstrator na oficjalnym zbiorze

- **Oficjalny zbiór to `data/DANE.zip`** (bez hasła, 10 przypadków: 1, 2, 3, 5, 10, 14, 36, 47, 48, 61), rozpakowany do
  `data/dane/`. `___BACKUP.zip` ze strony był częścią zagadki, a nie zbiorem danych. Danych organizatora nie wolno publicznie
  rozpowszechniać (opis wyzwania, pkt 8).
- **Formalny opis wyzwania** (PDF): punktacja 30% grupowanie, 30% cechy i źródła, 15% demonstrator end-to-end,
  15% interpretowalność, 10% wdrażalność; ocena na ukrytym zbiorze (nowe warianty znanych kampanii i inne kampanie).
- **Demonstrator gotowy** (`code/src/fejki/demo/`, `code/src/fejki/app/demo_app.py`): wejście = folder, HTML, HAR, zrzut,
  nagranie, info.json, URL, tekst; cechy w 11 kanałach; każde powiązanie z przesłankami; dwa poziomy: **kampania**
  (ten sam przekaz) i **sieć** (wspólna infrastruktura). Tylko dane nagrane i bierne (decyzja: bez pobierania stron na żywo).
- **Wynik na zbiorze:** kampanie {1, 2} (duplikat: ten sam piksel 2012165449475163, tekst, obrazy) i {48, 61} (wariant:
  te same obrazy, tytuł, szablon); sieć S1 = {1, 2, 3, 48, 61} (ten sam schemat `utm_*`+`utm_visit`, katalog `/aio-static/sdk`,
  wspólna domena healthlinkq.pro dla 2 i 3). Przypadek 61 to cloaking (przykrywka + wabik + produkt na jednej domenie).
  Pozostałe (5, 10, 14, 36, 47) bez wspólnych śladów.
- **Testy:** pomiń-jeden 100% spójności (kampanie i sieci); sam HTML albo sam HAR trafia do właściwej sieci; **same zrzuty nie
  wystarczają** (0/4). 29 testów jednostkowych przechodzi. Metodyka i licencje: `code/docs/METODYKA.md`.
- **Do zrobienia:** repozytorium Git (wymóg formalny), token Meta do sprawdzania `ad_id` (opcjonalnie), polski OCR lokalnie.

---

## 1. W skrócie (TL;DR)

1. **Kod działa**, ale wyniki główne są na danych **syntetycznych**. Prawdziwych reklam z Meta nie mamy: konto nie ma dostępu do Ad Library API (błąd 10 / 2332002).
2. **Strona organizatorów to układanka, a nie tylko zajawka.** Rozwiązaliśmy kilka warstw i otworzyliśmy `scam_links.enc` (3 linki oszustw). Ukryta w niej paczka `___BACKUP.zip` (73 MB) jest **zamknięta hasłem, którego nie znamy**.
3. **Największe odkrycie:** nazwy plików w zipie są jawne. Widać z nich, że to 15 zarchiwizowanych stron oszustw z 2026-10-08, w wyraźnych kampaniach (m.in. 4 strony o fałszywym „zamachu na Rafała Brzoskę"), oraz **11 domen**. Na tych domenach uruchomiliśmy nowy **kanał infrastruktury** i odtworzył on wszystkie 5 par stron z jednej kampanii (patrz pkt 7).
4. **Nowy kanał infrastruktury** (DNS, ASN, RDAP, certyfikaty): działa na żywo, ma testy, wpina się w graf kampanii.
5. **Do rozstrzygnięcia:** hasło do zipa (zapytać organizatorów), dostęp do danych (Meta/TikTok/ręczna próbka), ile mamy czasu do oddania.

---

## 2. Zadanie

> „Fałszywe reklamy wykorzystujące wizerunki znanych osób pozorują wiarygodność i prowadzą użytkowników wprost w pułapkę oszustów. Szybko znikają, zmieniają formę i wracają pod nowymi adresami, utrudniając rozpoznanie skali zagrożenia. Pojedynczy podejrzany materiał może być zaledwie fragmentem znacznie większej kampanii. Jak dostrzec szerszy obraz w chaosie internetowych oszustw i skuteczniej chronić ich potencjalne ofiary?"

Brief z plakatu (`brief/brief.md`, `brief/plakat.jpg`): z chaosu pojedynczych reklam wyciągnąć strukturę, rozpoznać cechy wspólne, określić podobieństwo i połączyć materiały z tych samych lub podobnych kampanii. Oczekiwana jest też **wiedza o tym, jak dostać się do bibliotek reklam**.
Strona zajawki podpowiada oczekiwaną metodę: łączyć po twarzach, obrazach, tekście i infrastrukturze (WHOIS/RDAP, DNS, certyfikaty, favicony), grafem z uzasadnieniem każdej krawędzi.

---

## 3. Nasz pomysł (z pierwotnego planu)

Narzędzie wyciągające strukturę kampanii z pojedynczych reklam: tekst z OCR i transkrypcji, hashe (pHash, SimHash), embedding zamrożonego wielojęzycznego enkodera, usunięcie liniowego wpływu tematu (**LEACE**), klastrowanie w oknach czasowych, graf (kreacje, reklamodawcy, domeny, komentarze jako hashe), detekcja fal per region i **wyprzedzenie względem Listy Ostrzeżeń CERT Polska**. Bez biometrii twarzy.
Czego nie twierdzimy: że graf kampanii jest nowy (to praca NASK), że LEACE usuwa temat całkowicie (gwarancja tylko liniowa), że widzimy cały ekosystem.
Plan dnia: pipeline offline na syntetyce, Eksperyment 1 (odzysk kampanii), dane prawdziwe przez `ingest csv`, graf + Streamlit, wyprzedzenie względem CERT, slajdy dla Jakuba (3–5).

---

## 4. Co jest zbudowane (kod, `code/`)

Pakiet `fejki` (Python 3.13, `code/.venv`). Testy: **22 przechodzą**.

| Obszar | Stan |
|---|---|
| Pipeline: schemat, DuckDB, normalizacja, domeny, artefakty, SimHash/MinHash, enkoder bge-m3 | gotowe |
| Klastrowanie (agglo, HDBSCAN), metryki B-cubed z bootstrapem po kampaniach | gotowe |
| Generator syntetyczny z kontrolami, LEACE, sondy, eksperymenty E1–E4 | gotowe |
| Graf (Leiden), karty kampanii, koordynacja, bursty, wyprzedzenie względem CERT (symulacja) | gotowe |
| Streamlit (`fejki app`) | napisany, **nie uruchomiony** w przeglądarce |
| Adapter Meta (token w nagłówku, obsługa błędu 10/2332002 i 613) | gotowy, **nie sprawdzony z działającym tokenem** |
| Adapter CSV (`fejki ingest csv`) | gotowy, sprawdzony tylko na przykładowych danych |
| Adapter Google BigQuery | gotowy, **nie sprawdzony na żywo**; tabela raczej bez tekstu reklam |
| Adapter YouTube, CERT | nieprzetestowane na żywo |
| **Kanał infrastruktury** (`fejki infra collect/link`) | **nowy, działa na żywo** (pkt 7) |

Wyniki na syntetyce (z `code/docs/PROGRESS.md`): kryterium główne H1 (F1 B-cubed z nienakładającymi się CI) **niespełnione**; wtórne (recall między-tematowy) spełnione przez LEACE tematu, ale to kryterium dodano po obejrzeniu wyników, więc jest eksploracyjne. LEACE podnosi recall (HDBSCAN: 0,44 → 0,86), ale obniża precyzję. Wykryto 14 z 20 kampanii w symulacji CERT, mediana wyprzedzenia ok. 1,8 dnia (symulacja, nie dane prawdziwe).
Znane ograniczenia: styl syntetyki łatwo odróżnić (AUC ok. 0,98), więc wynik może być zawyżony; na syntetyce sama infrastruktura wygrywa, bo reklamodawcy są współdzieleni.

---

## 4a. Dostęp do reklam: stan

| Źródło | Stan | Uwagi |
|---|---|---|
| **Meta Ad Library API** | **zablokowane** | Błąd 10 / 2332002: konto/aplikacja nie ma dostępu. Trzeba potwierdzić tożsamość (facebook.com/ID, do kilku dni) i warunki na facebook.com/ads/library/api. Dane komercyjne (`spend`, `impressions`) tylko dla reklam politycznych; użyć `eu_total_reach`. |
| Meta Ad Library UI | brak eksportu dla reklam komercyjnych | Eksport CSV jest tylko dla reklam społecznych/politycznych. Scraping UI jest wbrew regulaminowi Meta (nie robiliśmy). |
| **TikTok Commercial Content API** | do złożenia wniosku | Wg oficjalnej strony: dla „public and researchers", odpowiedź ok. 2 dni robocze, dane z UE. **Nie wiadomo, czy zwraca tekst reklamy.** |
| Snapchat Ads Gallery API | nieprzydatne | Otwarte bez tokena, ale wymaga nazwy reklamodawcy (brak szukania po słowie); sprawdzone na żywo. |
| Google Ads Transparency (BigQuery) | adapter gotowy | Wymaga projektu GCP; tabela raczej bez tekstu reklam. |
| Zbiór ręczny | szablon gotowy | `data/reklamy_reczne.jsonl` + opis w `data/README.md`. |
| **Paczka od organizatorów** | zamknięta hasłem | Patrz pkt 5. |

Tokeny Meta wklejone na czacie wygasły. Należy je uznać za ujawnione i unieważnić.

---

## 5. Co dali organizatorzy (strona `science.nask.pl/hacknation`)

### 5.1 Łańcuch dojścia
Plakat (QR „Zeskanuj mnie") → `loyalty.nuvio.group/enroll/…` (karta lojalnościowa Apple/Google Wallet, tytuł „NASK | Program lojalnościowy", komercyjny dostawca Nuvio) → karta w portfelu linkuje do `science.nask.pl/hacknation`. Najpewniej zamierzone przez organizatorów (nie da się tego niezależnie potwierdzić). Karta wysyła powiadomienia push.

### 5.2 Strona
Parodia reklamy „FakeCollector PRO™" („Strona powstała na hackathon Follow the Fake jako parodia reklam-naciągaczy"). Linkuje: `files/scam_links.enc`, trzy filmy (`1005.mp4`, `footer.mp4`, `very_important.mp4`), `loop.gif`, podstronę `lusterko/` (z `___BACKUP.zip` i `czekoladka.png`). Pobraliśmy wszystko do `research/nask-hacknation/` (ścieżek zakazanych w `robots.txt` nie ruszaliśmy).

### 5.3 Układanka: co rozwiązaliśmy

| Warstwa | Wynik |
|---|---|
| `footer.mp4`, ruch (tło +4 px/klatkę, litery −4 px) | tekst **`93JNG`** |
| `scam_links.enc` | **otwarte hasłem `93jng`** (małymi literami) |
| `footer.mp4`, jasność pikseli po odjęciu pasków | „WRITTEN IN GHOST FONT" (potwierdza, że klucz siedzi w szumie) |
| `1005.mp4`, audio (Whisper) | „Trzy ku górze, siedem ku dołowi. Krok za krokiem, na przemian. Koniec prowadzi do początku, początek do końca." |
| Szyfr z audio (−3, +7 na przemian) na „VIHXFAEKDBQ" z opinii na stronie | **`SPEECHBRAIN`** |
| `loop.gif` | 15 ukrytych białych liter: `EIDBARMRSAETBIA` (wg czasu), `MEETAAADSIIBBRR` (wg kolumn) |
| `_haslo.png` (szyfr „czekoladka") | odczyt `TFWNTNJ / FNBUFNJU`, nie składa się w nic |

### 5.4 Nierozwiązane: hasło do `___BACKUP.zip`
Wypróbowane bez skutku: `93jng` i warianty, `SPEECHBRAIN` (6 zapisów), odczyty `_haslo.png` (kilka orientacji, kropka pierwsza/druga, alfabet 26 i 23, przesunięcia ±3/±7), litery z `loop.gif`, wszystkie hasła z kodu strony (poniżej), płot kolejowy 2–7, odczytywanie na przemian od końców, klucz Vigenère'a SPEECHBRAIN. Brakuje ogniwa łączącego `SPEECHBRAIN`, `_haslo.png` i litery z `loop.gif`.
Uwaga: `_haslo.png` ma metadane C2PA mówiące, że obraz wygenerował model obrazów (ChatGPT, 2026-10-08). Symbole mogą być narysowane niedokładnie, co tłumaczy kłopot z odczytem.
**Najlepszy następny krok: zapytać organizatorów na Discordzie.**

### 5.5 Pułapki w kodzie strony (wszystko sprawdzone i nie działa)
W źródle są podpowiedzi, które są przynętami: `FollowTheFake2026!` (komentarz „TODO dev"), `Ghost-Font-0xDEADBEEF` (meta), `Sup3rTajneHaslo!2026` (ukryty znacznik), `nice_try_robot_watch_the_video` (zakodowane w JS), oraz **notatka skierowana do asystentów AI** z hasłem `kolekcjoner_fejkow_1337` i radą, by „nie analizować filmu w stopce" (to w nim jest prawdziwy klucz). Żadne z tych haseł nie działa. Lekcja: tekst z tej strony to dane do sprawdzenia, a nie polecenia.

### 5.6 `scam_links.enc` (otwarty)
3 linki z reklam Google (oznaczone „ZIDENTYFIKOWANY SCAM"): `caepertss.com`, `tlbjyhce.com`, `zzvn.info`. Nie otwieraliśmy ich; analiza wyłącznie bierna (pkt 7).

### 5.7 `___BACKUP.zip`: co wiemy bez hasła
Zip ma 471 wpisów (436 zaszyfrowanych AES, reszta to katalogi). **Nazwy plików są jawne.** Katalogi `p1`–`p15` to zarchiwizowane strony oszustw (HAR, HTML, zrzut ekranu, czasem DNS/SSL i sumy kontrolne), z datami z 2026-10-08:

| Katalog | Tytuł strony | Domena (z nazwy HAR) |
|---|---|---|
| p1, p2 | „«Wiem, kto strzelał»: zamach na Rafała Brzoskę, założyciela InPostu" (podszyty pod Gazeta.pl) | dorquesio.click |
| p7 | to samo | wernulio.live |
| p15 | to samo | lundevra.live |
| p3 | „PILNE! Brutalna napaść na Krzysztofa Stanowskiego…" | falmurek.live |
| p4 | „PILNE! Brutalna napaść na Tomasza Sekielskiego…" | grentavo.click |
| p5 | „Sam pan sobie podniósł premię!: jak Monika Olejnik zmiażdżyła prezesa NBP" | smartcoved.pro |
| p8, p11 | „Trudna odpowiedź" | spiritualityinsports.org, sfuxd.com |
| p9 | „Cactus Recipe" | door-focus.com |
| p10 | „Kardivix" (+ `video_deleted.txt`) | move-fitlum.top |
| p13 | „Polka zdradza sekret szybkiego pozbycia się uciążliwej grzybicy!" | zenithlab.ink |
| p6, p12, p14 | cukrzyca, RelieFlex, „Available For a LIMITED TIME ONLY" | (brak HAR) |

**To dokładnie typ oszustw z zadania** (wizerunek znanych osób jako wabik). Nie wiem, czy to oficjalny zbiór dla uczestników, ani co dokładnie jest w środku (tylko nazwy plików). Etykiety kampanii w pkt 7 to mój odczyt z tytułów.

### 5.8 Nowe (2026-11-21, druga tura): identyfikatory pikseli z nazw plików zipa
Nazwy plików w `___BACKUP.zip` są jawne i zawierają numery o 15–16 cyfrach obok `fbevents.js`. To najpewniej identyfikatory pikseli Meta (nie zweryfikowane w treści, bo zip jest zamknięty). Wspólny numer = wspólny operator konta reklamowego.

| Piksel | Katalogi (domena, kampania) |
|---|---|
| **4567646436826205** | p1, p2 (dorquesio, Brzoska), p7 (wernulio, Brzoska), p3 (falmurek, Stanowski), p4 (grentavo, Sekielski) |
| 2012165449475163 | p15 (lundevra, Brzoska) |
| 2420768028414250 | p10 (Kardivix) |
| 1396608265958754 | p12 (RelieFlex) |
| 1872419533729032 | p6 |
| 959278079792247 | p8 |
| 1550629110431763 | p9 |
| 147664324849328, 1583572655454371, 378104674982042 | p14 (trzy piksele, plus clarity, atomicpixel) |

Wniosek: p1, p2, p3, p4, p7 mają **ten sam piksel**, czyli jednego operatora, który prowadzi kampanie Brzoska, Stanowski i Sekielski. To niezależnie potwierdza hipotezę z pkt 6 (wspólna para serwerów nazw i rejestrator tych czterech domen). Lundevra (też Brzoska) ma inny piksel, więc kampania ma więcej niż jednego operatora.
Inne ustalenia: `very_important.mp4` to Rickroll (Vlipsy); `1005.mp4` ma tylko efekt glitch na wstępie (klatki 0–8), bez ukrytej treści; `czekoladka.png` to szyfr pigpen z 23 literami (bez Q, V, X), a `lusterko/` odbija go w pionie. Komunikat w konsoli strony mówi tylko: znalazłeś wszystkie wskazówki, pochwal się na Discordzie.

### 5.9 Nowe (2026-11-21, trzecia tura): loop.gif zweryfikowany jako zwykła dekoracja, pełny tytuł p6, szyfrowanie zipa
- **KOREKTA: `loop.gif` jednak niesie napis.** Użytkownik znalazł w nim „meta ads library" (Discord, mentor: „Super! Warto jeszcze pogrzebać"). Mój wcześniejszy wniosek w tej sekcji („to sama dekoracja") był błędny: detektor nie odróżniał pogrubionych białych liter od zwykłych głów strumieni. Odczyt z poprzedniej sesji (`EIDBARMRSAETBIA` / `MEETAAADSIIBBRR`) też jest niepełny (brak L i Y z „metaadslibrary").
- „meta ads library" to najpewniej wskazówka do **Meta Ad Library**, czyli źródła danych z zadania. Jako hasło do zipa nie działa: sprawdziłem 310 wariantów zapisu (spacje, wielkość liter, przyrostki, połączenia z 93jng i SPEECHBRAIN).
- **Pełny tytuł p6** (ucięty wcześniej): „Wysoki cukier, ciągłe pragnienie i chroniczne zmęczenie — pierwsze oznaki cukrzycy! Rozmowa z Ojcem Bonifacym z Jasnej Góry".
- **Zip używa WinZip AES-256 (AE-3)**, każdy plik ma osobną sól/HMAC. Tylko katalog `p1` (i duplikaty struktury w p2/p7/p15, do potwierdzenia) ma pełny zestaw `archive_info.json`, `dns_ssl.json`, `metadata.json`, `page_text.txt`, `sha256.json` — inny schemat archiwizacji niż reszta (`.har` + `_files/`). Nie znaleziono niezaszyfrowanych danych poza nazwami i rozmiarami plików; `zip.comment` jest pusty.
- Sprawdzono nagłówki HTTP strony (CSP, cookies, serwer) i typowe ścieżki (`sitemap.xml`, `humans.txt`, `.well-known/security.txt`, `favicon.ico`): same 404, nic ukrytego.
- **Wniosek: bez hasła od organizatorów dalej nie przejdziemy.** Zalecenie niezmienne: pytać na Discordzie, podając co już wiemy (93jng, SPEECHBRAIN, układ `_haslo.png`/`czekoladka.png`, że `loop.gif` prawdopodobnie jest ślepym tropem).

---

## 6. Kanał infrastruktury (nowe)

Kod: `code/src/fejki/infra/` (`collect.py`, `link.py`); CLI: `fejki infra collect <plik z URL>` i `fejki infra link <plik z URL>`; testy: `code/tests/test_infra.py`.
Źródła **wyłącznie bierne**: DNS, ASN (Team Cymru po DNS), RDAP (rdap.org), dziennik certyfikatów (crt.sh), kształt adresu z reklamy. **Nie łączymy się ze stronami oszustów.**
Reguły łączenia (wagi łączone tak, by jeden słaby sygnał nie tworzył krawędzi; każda krawędź ma listę uzasadnień): wspólny IP (słaby, jeśli adres CDN, np. Cloudflare), identyczny zestaw serwerów nazw, ta sama podsieć /24, masowa rejestracja (≤1 h), rejestracja w tej samej dobie / ≤3 dni, ten sam rejestrator, ten sam certyfikat, wspólny wzorzec ścieżki w adresie reklamy, wspólne parametry śledzące, ta sama platforma w adresie.
Krawędzie wchodzą do grafu kampanii przez `build_graph(..., infra_edges=...)`.

### Dane (14 domen)

| Domena | Źródło | Kampania (tytuł) | Rejestrator | Utworzona | DNS | IP |
|---|---|---|---|---|---|---|
| dorquesio.click | p1,p2 | Brzoska | Dynadot | 2026-10-07 | Cloudflare | 104.21.19.45, 172.67.185.56 |
| wernulio.live | p7 | Brzoska | Dynadot | 2026-10-07 | Cloudflare | 188.114.96.11, .97.11 |
| lundevra.live | p15 | Brzoska | Dynadot | 2026-10-07 | dyna-ns.net | 195.116.107.99 |
| falmurek.live | p3 | Stanowski | Dynadot | 2026-10-05 | Cloudflare | 104.21.8.235, 172.67.188.210 |
| grentavo.click | p4 | Sekielski | Dynadot | 2026-10-05 | Cloudflare | 188.114.96.11, .97.11 |
| smartcoved.pro | p5 | Olejnik/NBP | NICENIC | 2026-10-08 | Cloudflare | 195.116.107.98 |
| spiritualityinsports.org | p8 | Trudna odpowiedź | NameCheap | 2010-08-05 | mysecurecloudhost | 195.116.107.99 |
| sfuxd.com | p11 | Trudna odpowiedź | Porkbun | 2024-10-01 | mysecurecloudhost | 159.65.146.122 |
| door-focus.com | p9 | Cactus Recipe | NameCheap | 2026-07-09 | Cloudflare | 188.114.96.11, .97.11 |
| move-fitlum.top | p10 | Kardivix | Namecheap | 2026-09-22 | Cloudflare | 188.114.96.11, .97.11 |
| zenithlab.ink | p13 | Grzybica | NameCheap | 2026-02-12 | Cloudflare | 104.21.78.140, 172.67.222.109 |
| caepertss.com | scam_links | sklep | Xin Net | 2025-12-03 | Huawei Cloud | 104.17.232.29 |
| tlbjyhce.com | scam_links | sklep | HiChina | 2026-06-30 | HiChina | 104.17.232.29 |
| zzvn.info | scam_links | ? | Dynadot | 2026-09-10 | Cloudflare | 195.116.107.99 |

### Wynik oceny na 9 domenach z etykietą (skrypt: `research/nask-hacknation/eval_infra.py`)
Z 55 par 5 jest prawdziwie z jednej kampanii (wg tytułów): dorquesio↔wernulio, dorquesio↔lundevra, wernulio↔lundevra (Brzoska), falmurek↔grentavo (Stanowski/Sekielski), sfuxd↔spiritualityinsports (Trudna odpowiedź).

| Próg | Znalezione prawdziwe | Fałszywe alarmy | Precyzja | Recall |
|---|---|---|---|---|
| 0,5 | 5/5 | 8 | 0,38 | 1,00 |
| 0,7 | 5/5 | 2 | 0,71 | 1,00 |
| **0,8** | **5/5** | **1** | **0,83** | **1,00** |

Wszystkie 5 prawdziwych par ma wynik ≥ 0,83. Najmocniejsze sygnały: rejestracja w odstępie kilku sekund (dorquesio i wernulio: 18 s; falmurek i grentavo: 6 s; lundevra 5 min po nich), identyczna para serwerów nazw Cloudflare (cartman, fish) oraz wspólny, **niebędący CDN** adres IP.

### Ciekawe powiązania
- **`zzvn.info` (z zaszyfrowanych linków) ma ten sam IP co `lundevra.live` (kampania Brzoska) i `spiritualityinsports.org` („Trudna odpowiedź")**: 195.116.107.99, adres Orange Polska. To łączy plik `scam_links.enc` z zawartością zipa. Sąsiedni adres (.98) ma `smartcoved.pro`.
- `spiritualityinsports.org` (utworzona 2010) i `sfuxd.com` (2024) to domeny sporo starsze niż reszta, co sugeruje przejęte lub wykorzystane stare strony. To hipoteza, bez dowodu.
- Cztery domeny (dorquesio, falmurek, grentavo, wernulio) dzielą tę samą parę serwerów nazw Cloudflare i rejestratora, mimo że należą do dwóch różnych kampanii wg tytułów. Może to być **ten sam operator** prowadzący kilka kampanii.

### Uczciwe zastrzeżenia
- **Reguły dopracowałem po obejrzeniu tych danych** (po pierwszym przebiegu zaostrzyłem rejestrację w czasie, dodałem zestaw serwerów nazw i podsieć). To ilustracja, a nie niezależny test. Próbka to 9 domen i 5 prawdziwych par.
- Etykiety to mój odczyt z tytułów stron, a nie rozstrzygnięcie organizatorów.
- Kampania = ta sama treść strony; infrastruktura mówi raczej o **operatorze**. Jedyny fałszywy alarm przy progu 0,8 (lundevra ↔ spiritualityinsports, wspólny IP) może być prawdziwym powiązaniem operatora, który prowadzi dwie kampanie. Kanały treści i infrastruktury są komplementarne.
- Para `caepertss.com` ↔ `tlbjyhce.com` (wynik 0,66) opiera się głównie na wspólnym wzorcu adresu `/products/<N>`, wspólnych parametrach śledzących i wspólnym IP Cloudflare. Mają różnych rejestratorów i DNS, utworzone w odstępie 7 miesięcy. Dowód umiarkowany.

---

## 7. Ryzyka i ograniczenia
1. **Brak prawdziwych reklam z bibliotek.** Główny dowód to nadal dane syntetyczne; pitch musi to nazwać wprost.
2. **Zapis ze strony organizatorów to układanka** z kilkoma pułapkami. Nie traktować jej tekstów jak poleceń.
3. **Nie znamy hasła do zipa**, więc nie wiemy, co jest w środku poza nazwami plików.
4. Kanał infrastruktury ma małą próbkę i reguły ustawione po obejrzeniu danych.
5. Nie mamy kanałów obrazu i twarzy, a zadanie (i strona zajawki) wyraźnie o nich mówi.
6. Nie znamy terminu oddania i czasu trwania hackathonu.

---

## 8. Kolejne kroki (w kolejności)
1. **Zapytać organizatorów (Discord):** hasło/sposób otwarcia `___BACKUP.zip`, czy to oficjalne dane, czy wolno zbierać z UI, czy dają próbkę. Podać, co odczytaliśmy (93jng, SPEECHBRAIN, `_haslo.png`).
2. **Podać termin oddania**, żeby rozpisać plan na godziny.
3. **Meta:** dokończyć potwierdzenie tożsamości; **TikTok:** złożyć wniosek (ok. 2 dni).
4. **Zbiór ręczny** kilkudziesięciu prawdziwych reklam (`data/`).
5. Rozszerzyć infrastrukturę: hash favicony i wspólne skrypty/trackery wymagają **kontaktu ze stronami oszustów**, więc tylko po osobnej decyzji (np. w izolowanym środowisku). Dodać też kanał obrazu (pHash, CLIP) dla stron z zipa, gdy będzie hasło.
6. Pokazać w pitchu: metoda (LEACE + graf), wyniki na syntetyce z kontrolami, kanał infrastruktury na realnych domenach, wiedza o dostępie do bibliotek reklam (tabela z pkt 4a), ograniczenia.
7. Sprzątanie: unieważnić tokeny Meta; opcjonalnie usunąć modele Whisper z pamięci podręcznej HF (ok. 2,5 GB); dezaktywować kartę Nuvio w portfelu.

---

## 9. Mapa plików

| Ścieżka | Co |
|---|---|
| `DOKUMENT_ZBIORCZY.md` | ten dokument |
| `README.md` | skrót zadania i stanu |
| `brief/` | brief tekstowy, plakat |
| `research/dostep-do-reklam.md` | szczegóły o dostępie do bibliotek |
| `research/strona-nask.md` | pełne notatki o stronie i układance |
| `research/nask-hacknation/` | pobrane pliki (strona, media, `scam_links.enc` + odszyfrowane, zip), `domains_from_zip.*`, `eval_infra.py` |
| `data/` | szablon ręcznego zbioru (JSONL) |
| `code/` | kod (pakiet `fejki`), `docs/PROGRESS.md`, testy, `.env` (tokeny; poza kontrolą wersji) |
| `code/data/raw/infra/` | zebrane cechy domen (JSON) |
| `code/artifacts/infra/links.json` | krawędzie infrastruktury z uzasadnieniami |
