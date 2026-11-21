# Strona organizatorów i łańcuch plakat / QR / karta (2026-11-21)

## Łańcuch
1. Plakat ([../brief/plakat.jpg](../brief/plakat.jpg)) ma kod QR "Zeskanuj mnie" obok linku science.nask.pl/hacknation.
2. QR dekoduje się do `https://loyalty.nuvio.group/enroll/6586110843755849`, nie do NASK.
3. Nuvio to komercyjny dostawca kart lojalnościowych Apple/Google Wallet (push). Strona zapisu ma tytuł
   "NASK | Program lojalnościowy" (tytuł ustawia właściciel konta, więc sam nie dowodzi autorstwa NASK).
   Serwer: HTTP 200, Next.js, `noindex`, certyfikat Let's Encrypt od 2026-09-25, IP 57.128.254.99.
4. Karta w portfelu linkuje do `https://science.nask.pl/hacknation`.
Wniosek: najpewniej zamierzone przez organizatorów. Nie można tego potwierdzić niezależnie. Karta wysyła powiadomienia push.

## Strona science.nask.pl/hacknation
Parodia reklamy "FakeCollector PRO™" ("Strona powstała na hackathon Follow the Fake jako parodia reklam-naciągaczy").
Linkuje: `files/scam_links.enc`, `media/1005.mp4`, `media/footer.mp4`, `media/very_important.mp4`, `media/loop.gif`, `lusterko/`.
Sugerowane podejście techniczne ("Pod maską"): twarze (InsightFace, MagFace, facetorch), obrazy (imagehash, CLIP/SigLIP),
tekst (OCR, sentence-transformers, MinHash/LSH), infrastruktura (przekierowania, WHOIS/RDAP, DNS, crt.sh, hashe favicon,
wspólne skrypty), łączenie (HDBSCAN, graf, uzasadnienie każdej krawędzi).

## Niezrobione
Brak dat, kryteriów oceny i zasad zbierania danych na stronie; jedyny kontakt: Discord (bez linku). Pliki ze strony pobrane, patrz aktualizacja niżej.

---
# Aktualizacja 2026-11-21: pełne pobranie i analiza (folder `nask-hacknation/`)

## Pobrane (wszystko ze strony i z linków na niej)
`index.html`, `robots.txt`, `lusterko/index.html`, `files/scam_links.enc` (1 KB), `files/___BACKUP.zip` (73 MB, zaszyfrowany AES, 471 plików),
`media/1005.mp4`, `media/footer.mp4`, `media/very_important.mp4`, `media/loop.gif`, `media/czekoladka.png`, `media/_haslo.png`.
Nie ruszano ścieżek zakazanych w robots.txt (`/admin/`, `/files/backup/`). Zip nie jest rozpakowany (zaszyfrowany).

## Zawartość zipa (z listingu, bez rozpakowania)
Katalog `BACKUP/p1 … p15`: zarchiwizowane strony oszustw (np. `dorquesio.click`: HAR, HTML, MHTML, PDF, zrzuty, DNS/SSL, sumy SHA256),
fałszywy artykuł podszyty pod Gazetę.pl o zamachu na założyciela InPostu, strony produktów (Kardivix, RelieFlex, "Cactus Recipe" itd.).
To realny, bogaty materiał do zadania (kampanie, infrastruktura, obrazy), czeka na hasło.

## Zagadka
- `very_important.mp4`: Rickroll (przynęta).
- `1005.mp4`: człowiek w masce Guya Fawkesa, bez widocznego tekstu na klatkach (audio nie analizowane).
- `footer.mp4`: ruchomy szum; z ruchu (tło przesuwa się o 4 px/klatkę, litery nie) wydobyty tekst **93JNG**. Nie otwiera ani `.enc`, ani zipa (próby ze wskazanymi na stronie ustawieniami: aes-256-cbc, pbkdf2-sha256, 10000).
- `_haslo.png` (adres ukryty w ciasteczku `czekoladka`, base64): szyfr "czekoladka" (klucz w `czekoladka.png`). Odczyt: `TFWNTNJ / FNBUFNJU`
  (kropka = druga litera pary); wariant z odwróconą kropką `TEWMTMI / EMAUEMIU`. Żaden nie otwiera `.enc` ani zipa; proste przesunięcia Cezara nie dają słów.
- W kodzie strony są też ukryte "hasła" i kodowane teksty (przynęty, m.in. `nice_try_robot_watch_the_video`); nie testowane poza opisanymi wyżej.
- Nierozwiązane: `loop.gif` (9 MB, ukryty 1x1), audio z `1005.mp4`, tekst "VIHXFAEKDBQ", `lusterko/` (efekt lustra na obrazku).

---
# Aktualizacja 2 (2026-11-21): rozwiązane warstwy

## `scam_links.enc`: OTWARTE
Hasło: **`93jng`** (małymi literami; klucz z `footer.mp4` wyświetla się wielkimi). Ustawienia: `openssl enc -d -a -aes-256-cbc -pbkdf2 -iter 10000 -md sha256`.
Odszyfrowane: `nask-hacknation/files/scam_links.dec.txt`, 3 linki oznaczone "ZIDENTYFIKOWANY SCAM" (reklamy Google, `gclid`):
`caepertss.com`, `tlbjyhce.com` (oba `/products/<długi numer>`), `zzvn.info`. Linków nie otwierano (strona ostrzega). Bierna analiza:
caepertss.com i tlbjyhce.com → ten sam IP 104.17.232.29 (Cloudflare), rejestratorzy chińscy (Xin Net 2025-12-03, HiChina 2026-06-30), NS Huawei Cloud / HiChina;
zzvn.info → 195.116.107.99. Dwie pierwsze domeny to ta sama "fabryka" sklepów-wabików (kanał infrastruktury do projektu).

## `footer.mp4`: dwie warstwy
1. Ruch: tło przesuwa się o +4 px/klatkę, litery `93JNG` o -4 px/klatkę (analiza błędu dopasowania dla przesunięć -12..+12; brak innych warstw ruchu).
2. Średnia jasność pikseli w czasie (po odjęciu wzoru pionowych pasków z czystych wierszy): **"WRITTEN / IN / GHOST / FONT"**.
   (Wcześniejsza analiza zgadywała "COMIC SANS": błąd. Środkowe wiersze to "IN" i "GHOST".) Znaczy: klucz jest zapisany "czcionką-duchem" (tekst ukryty w szumie). Nowego hasła ta warstwa nie daje.

## `loop.gif`: ukryte litery
15 pogrubionych białych liter w deszczu Matrixa. Kolejność pojawiania się: `EIDBARMRSAETBIA`; wg kolumn (X): `MEETAAADSIIBBRR`. Obie (i małe litery) NIE otwierają zipa ani `.enc`. Znaczenie nieznane (anagram? klucz do szyfru?).

## Dalej nierozwiązane: hasło do `___BACKUP.zip`
Sprawdzone bez skutku: 93JNG (warianty), odczyt `_haslo.png` (czekoladka) w kilku wariantach, EIDBARMRSAETBIA / MEETAAADSIIBBRR, hasła z kodu strony, VIHXFAEKDBQ.
Zostały: audio z `1005.mp4`, tekst "VIHXFAEKDBQ", poprawny odczyt `_haslo.png`.

---
# Aktualizacja 3 (2026-11-21): audio z `1005.mp4`

Ścieżka audio (10 s) to ludzka mowa po polsku (spektrogram: formanty, bez ukrytego obrazka). Transkrypcja (Whisper large-v3-turbo, beam 5):
"Trzy ku górze, siedem ku dołowi. Krok za krokiem, na przemian. Koniec prowadzi do początku, początek do końca."
(Słuchowo/z mniejszego modelu: "Trzy kule, siedem kół do łowi", czyli to samo zniekształcone.)

Interpretacja: szyfr przesuwający litery na przemian o 3 w jedną i o 7 w drugą stronę, alfabet cykliczny (koniec -> początek).
Zastosowany do `VIHXFAEKDBQ` (z fałszywej opinii na stronie) z przesunięciami (-3, +7) daje **`SPEECHBRAIN`**, czyli prawdziwe słowa: to potwierdza odczyt frazy.
`SPEECHBRAIN` (w kilku zapisach) NIE otwiera `___BACKUP.zip`; użyte jako klucz Vigenère'a do ciągów z `loop.gif` i `_haslo.png` też nic nie dało.
Hipoteza: wskazówka narzędziowa (toolkit SpeechBrain do przetwarzania mowy) albo kolejny krok układanki. Do ustalenia (Discord organizatorów).
Modele ASR pobrane do cache HF (~/.cache/huggingface): whisper-small, whisper-large-v3-turbo.

---
# Aktualizacja 4: kanał infrastruktury na 3 domenach z `scam_links`
Kod: `code/src/fejki/infra/` (collect.py, link.py), CLI `fejki infra collect|link <plik z URL>`, testy `code/tests/test_infra.py`.
Bierne źródła (bez kontaktu ze stronami oszustów): DNS, ASN (Team Cymru po DNS), RDAP (rdap.org), dziennik CT (crt.sh).
Wynik (artifacts/infra/links.json): caepertss.com <-> tlbjyhce.com, wynik 0.66: wspólny wzorzec /products/<N> (0.50), wspólne parametry śledzące aatid+adset_id (0.20),
wspólny IP Cloudflare 104.17.232.29 (0.15, słaby, CDN). Różnią się rejestratorem (Xin Net vs HiChina), dostawcą DNS (Huawei vs HiChina) i datą rejestracji (2025-12-03 vs 2026-06-30).
zzvn.info: IP Orange Polska (AS5617), DNS Cloudflare, rejestrator Dynadot, utw. 2026-09-10: brak powiązania.
