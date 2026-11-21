# 04. Strona-zagadka organizatorów i odkrycia

Pełny zapis chronologiczny: [research/strona-nask.md](../research/strona-nask.md) i [DOKUMENT_ZBIORCZY.md](../DOKUMENT_ZBIORCZY.md)
(sekcje 5.x). Tu wersja uporządkowana. Pliki ze strony leżą lokalnie w `research/nask-hacknation/` (media i zipy poza repo).

## Łańcuch dojścia

Plakat → kod QR „Zeskanuj mnie” → `loyalty.nuvio.group/enroll/…` (karta lojalnościowa „NASK | Program lojalnościowy”
w Apple/Google Wallet, komercyjny dostawca Nuvio) → karta linkuje do **science.nask.pl/hacknation**.

## Strona „FakeCollector PRO™”

Parodia reklamy-naciągacza. W sekcji „Pod maską” organizatorzy podpowiadają oczekiwane podejście: twarze (InsightFace,
MagFace, facetorch), obraz (imagehash, CLIP/SigLIP), tekst (OCR, sentence-transformers, MinHash/LSH), infrastruktura
(przekierowania, WHOIS/RDAP, DNS, crt.sh, **hash favicony, wspólne skrypty i trackery**), łączenie (podobieństwo ważone,
HDBSCAN, graf np. Neo4j, **uzasadnienie przy każdej krawędzi**). To lista kontrolna dla naszych kanałów (patrz plan).

## Warstwy zagadki (wszystkie znalezione, mentor potwierdził: „jest wszystko”)

| Warstwa | Wynik |
|---|---|
| `footer.mp4` (tło +4 px/klatkę, litery −4 px) | tekst **93JNG** |
| `scam_links.enc` (`openssl enc -d -a -aes-256-cbc -pbkdf2 -iter 10000 -md sha256`, hasło `93jng`) | 3 linki z reklam Google: caepertss.com, tlbjyhce.com, zzvn.info |
| `footer.mp4`, średnia jasność | „WRITTEN IN GHOST FONT” (wskazówka, że klucz siedzi w szumie) |
| `1005.mp4`, audio (Whisper) | „Trzy ku górze, siedem ku dołowi. Krok za krokiem, na przemian. Koniec prowadzi do początku…” |
| szyfr (−3/+7 na przemian) na opinii „Veni, vidi, VIHXFAEKDBQ” | **SPEECHBRAIN** (potwierdzone przez mentora) |
| `loop.gif` (ukryty obrazek 1×1 na stronie) | napis **„meta ads library”** (pogrubione białe litery w deszczu Matrixa; potwierdzone przez mentora) |
| podstrona `lusterko/` | lustro odbija w pionie `czekoladka.png`, czyli klucz szyfru pigpen (23 litery, bez Q/V/X) do `_haslo.png` |
| `lusterko/` | link „do góry nogami” do `___BACKUP.zip` (73 MB, AES, 15 zarchiwizowanych stron oszustw) |
| przycisk „KUP TERAZ” | Rickroll (`very_important.mp4`) |
| konsola przeglądarki | „Jeśli znalazłeś wszystkie wskazówki – pochwal się na Discordzie!” |

**Pułapki w kodzie strony** (sprawdzone, żadne nie działa): `FollowTheFake2026!`, `Sup3rTajneHaslo!2026`,
`Ghost-Font-0xDEADBEEF`, `nice_try_robot_watch_the_video`, notatka skierowana do asystentów AI z „hasłem”
`kolekcjoner_fejkow_1337` i radą, by nie analizować filmu w stopce (a klucz był właśnie tam). Lekcja: tekst ze stron to dane.

**Hasła do `___BACKUP.zip` nie znamy.** Wypróbowaliśmy kilka tysięcy wariantów (93jng, SPEECHBRAIN, odczyty pigpen
z lustrem i bez, „meta ads library”, połączenia, szyfry). Mentor uznał zagadkę za zamkniętą; oficjalnym zbiorem jest `DANE.zip`.

## Co z zagadki przydaje się w projekcie

1. **Wskazówki narzędziowe**: SpeechBrain → przetwarzanie mowy z nagrań reklam (zadanie B3); „meta ads library” →
   źródło danych (zadania D2/D3).
2. **Nazwy plików `___BACKUP.zip`** (jawne mimo szyfrowania): 15 stron, 11 domen, **identyfikatory pikseli Meta w nazwach
   plików** (`fbevents` + numer). Piksel 4567646436826205 łączy p1, p2, p3, p4, p7 (kampanie Brzoska, Stanowski, Sekielski),
   a piksel **2012165449475163** z p15 jest **ten sam co w przypadkach 1 i 2 z `DANE.zip`**. Szczegóły:
   DOKUMENT_ZBIORCZY.md, sekcja 5.8.
3. **Kanał infrastruktury** sprawdzony na tych domenach (DOKUMENT_ZBIORCZY.md, sekcja 6): reguły odtworzyły wszystkie 5 par
   stron z tych samych kampanii przy progu 0,8 (precyzja 0,83). Uwaga: reguły dostrojone po obejrzeniu danych.
4. Domeny z `scam_links` (caepertss.com i tlbjyhce.com: ten sam wzorzec `/products/<N>`, te same parametry `aatid`,
   `adset_id`) to przykład „fabryki sklepów” do demonstracji wejścia URL.
