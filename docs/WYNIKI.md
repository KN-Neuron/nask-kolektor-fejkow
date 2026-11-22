# Wyniki: co mierzymy, na czym, jakie liczby

Zasady: każda liczba ma dane, podział i ograniczenie. Wyniki z syntetyki są oznaczone jako takie, bo generator jest pisany przez nas pod
nasze cechy i mierzy odzyskiwanie podłożonego sygnału, nie prawdziwych kampanii. Przedziały to 95% bootstrap po niezależnych jednostkach
(światy albo twórcy). Skrypty: `make eval` (log na żywo: `code/artifacts/stream/live.log`).

## 1. Syntetyka: grupowanie kampanii (protokół N-LNSO, 80 światów)  [syntetyka]

Każdy świat jest testowy dokładnie raz; progi i wybór dostrojone w światach treningowych; 3 podziały; `embsim/cv.py`.

| konfiguracja | ARI kampanii | błędne łączenie nowych wzorców | ARI kampanii bez HAR | ARI operatora |
|---|---|---|---|---|
| v1 (Jaccard, średnia) | 0,635 [0,610; 0,658] | 0,462 [0,433; 0,491] | 0,242 | 0,778 |
| v1 z leksyką i korekcją | 0,698 [0,680; 0,714] | 0,326 [0,303; 0,347] | 0,533 | 0,778 |
| **domyślna (`v3_mixed_pca`)** | **0,749 [0,730; 0,767]** | **0,148 [0,131; 0,166]** | 0,565 | 0,759 [0,737; 0,780] |
| domyślna bez PCA | 0,746 | 0,143 | 0,567 | 0,759 |
| domyślna bez leksyki | 0,722 | 0,144 | 0,541 | 0,759 |

Różnice względem domyślnej (Wilcoxon z korektą Holma): v1 +0,114 [0,097; 0,131], v1 z leksyką +0,052 [0,038; 0,065], brak leksyki +0,027
[0,021; 0,035], wszystkie p < 0,0001; **brak PCA +0,003, p = 0,14 (nieistotne)**. Wybór zagnieżdżony wskazał wariant bez PCA w 15 z 15
foldów. Poziom operatora: domyślna jest o 0,019 gorsza od v1 (p = 0,0006).
Świeże ziarna 33–35 (po wyborze trybów): ARI kampanii 0,715 wobec 0,263 (v1), ARI operatora 0,705 wobec 0,470.

## 2. Meta: czy sam tekst odtwarza twórcę  [prawdziwe dane, podział po podmiotach z grafu]

Test: 3 570 tekstów od 2 162 twórców; etykieta = `page_id`; próg z walidacji.

| reprezentacja tekstu | AUC | AP | ARI | top-1 |
|---|---|---|---|---|
| TF-IDF znaków (zero modelu) | 0,895 | 0,459 | 0,523 | 0,805 |
| MiniLM surowy | 0,788 | 0,084 | 0,144 | 0,633 |
| MiniLM, średnia i pierwsza składowa PCA usunięte | 0,901 | 0,243 | 0,328 | 0,665 |
| Qwen3-VL (podzbiór krótszych tekstów) surowy → wyśrodkowany | 0,883 → 0,937 | 0,308 → 0,355 | 0,411 → 0,432 | 0,773 → 0,791 |

Wniosek: prosta leksyka bije embedding MiniLM; PCA poprawia embedding, ale go nie dogania w AP i top-1.

## 3. Meta: strumień po czasie (nowa reklama względem wcześniejszych)  [prawdziwe dane]

Próbka S1 (14 936 reklam, 2 002 twórców), chronologicznie 50/20/30; test: 4 481 najnowszych reklam, z tego z treścią 3 385
(1 039 ze znanym twórcą, 2 346 z nowym). Wyniki dla reklam z treścią. Próg z walidacji. `embsim/stream_eval.py`.

| profil cech | top-1 twórcy | przypięcie (poprawny twórca i wynik ≥ próg) | odrzucenie nowych | AUROC znany vs nowy | pokrycie kandydatów |
|---|---|---|---|---|---|
| tekst gęsty, bez PCA | 0,452 [0,38; 0,53] | 0,295 [0,23; 0,36] | 0,943 | 0,729 [0,68; 0,78] | 0,60 |
| tekst gęsty, PCA | 0,464 [0,39; 0,54] | 0,377 [0,31; 0,45] | 0,813 | 0,742 [0,69; 0,79] | 0,65 |
| tekst leksykalny | 0,594 [0,52; 0,67] | 0,446 [0,37; 0,52] | 0,832 | 0,743 [0,69; 0,79] | 0,77 |
| gęsty + leksyka | 0,554 [0,47; 0,63] | 0,450 [0,37; 0,53] | 0,816 | 0,753 [0,70; 0,81] | 0,79 |
| **gęsty + leksyka + domena** | **0,628 [0,55; 0,70]** | **0,557 [0,48; 0,63]** | 0,775 | **0,771 [0,72; 0,82]** | 0,84 |
| … + targetowanie | 0,457 [0,38; 0,53] | **0,013** [0,00; 0,03] | 0,992 | **0,638** [0,58; 0,69] | 0,86 |
| … + targetowanie + płatnik | 0,570 [0,49; 0,64] | 0,179 [0,13; 0,23] | 0,822 | 0,666 [0,61; 0,71] | 0,95 |

- **Domena pomaga** (top-1 0,554 → 0,628), **targetowanie psuje** (AUROC 0,771 → 0,638, próg wychodzi na 1,00, system prawie niczego nie
  przypina). Przyczyna: miara śladów daje 1 − (df+0,5)/(N+1), więc wartość targetowania wspólna dla 10% reklam dostaje wynik 0,9; na
  syntetyce nie było śladów o średniej częstości. Wniosek: targetowania nie używamy; formułę śladów trzeba poprawić (zob. §7).
- **PCA** nie zmienia istotnie wyniku (AUROC 0,742 vs 0,729, przedziały się nakładają).
- Dla tekstu nowego (bez identycznego w galerii) najlepszy profil: top-1 0,552, przypięcie 0,448, AUROC 0,714.
- Optymalny próg na Mecie wyszedł ok. 0,5, a nie 0,95 (kalibracja na syntetyce): **progi zależą od zbioru** (suwak w interfejsie).
- Płatnik jest silnie związany z definicją twórcy w grafie, więc profil z płatnikiem jest częściowo tautologiczny.

## 4. Obraz  [prawdziwe zrzuty]

| porównanie | AUC | AP | top-1 |
|---|---|---|---|
| 117 zrzutów urlscan, histogram kolorów | 0,826 | 0,832 | 0,948 |
| j.w., Qwen3-VL | 0,791 | 0,840 | 0,974 |
| j.w., odcisk dHash | 0,733 | 0,809 | 0,957 |

Etykiety urlscan wynikają z infrastruktury (ślepe na wygląd), więc mierzymy, czy obraz widzi szablon, nie czy poznaje kampanię. Na
przypadkach NASK obraz nie łączy znanego wariantu 48≈61 (podobieństwo 0,47); sieć {1, 3, 48, 61} wypada o 0,04 lepiej niż reszta.
Wniosek: kanał obrazu jest słaby; priorytetem jest OCR zrzutu (zob. §7).

## 5. Przypadki NASK-10  [diagnostyka, zbiór nie jest czysty]

Cztery znane pary oglądaliśmy przy poprawianiu metody, więc nie służą już jako niezależny test. Domyślna konfiguracja łączy znany duplikat 1≈2
(0,97 przy progu 0,95) i nie łączy wariantu 48≈61 (0,72). Konfiguracja z miarą „zawierania” (próg 0,57) łączyła obie pary. To cztery
pary, więc to anegdota, nie dowód.

## 5a. Demonstrator na stronach: test na zbiorze ukrytym i dokładne obrazy  [NASK-10 + syntetyka v1, zostaw-jeden]

`code/scripts/test_jak_jury_embsim.py` odtwarza przebieg użytkownika w interfejsie (walidacja z pkt 6 opisu wyzwania): galeria z folderów, nowy materiał
wgrany jako pliki. A: każdy przypadek NASK ukryty raz; B: sam HTML / sam HAR / sam zrzut / ten sam materiał drugi raz; C: syntetyka v1 jako
ukryty zbiór (nowe warianty, nowa kampania znanego operatora, 6 negatywów). Raport: `code/artifacts/jury/raport_embsim.md`.

| wersja | A (NASK) | B (formaty, braki) | C (syntetyka) |
|---|---|---|---|
| przed (próg 0,95, ślady jak w kalibracji) | 7/10 | 3/13 | 6/20 |
| + obrazy i bez pospolitych usług, próg 0,95 | 8/10, 0 błędów | 6/13 | 9/20 |
| + próg 0,725 (kalibracja niżej) | 10/10 | 8/13 | 13/20 |
| + próg 0,62 i drugi przebieg grupowania (obecnie) | **10/10** | **10/13** | **20/20** |

- **Próg 0,62** (obecny, `config/embsim/demo_calibration.json`). Przegląd na tym samym teście: 0,60 i 0,62 dają warianty 15/15 i C 20/20,
  0,65 daje B 9/13, 0,69 daje C 19/20; 0,725 dawało czułość „znanej kampanii” 8/15, bo 7 wariantów miało wynik 0,70–0,72 (dobra grupa,
  zły poziom). Najmocniejszy negatyw ma 0,56, więc zapas jest mały, a próg dobrany na zbiorach, na których go mierzymy.
- **Drugi przebieg grupowania** (`Gallery.regroup`, wywoływany po wczytaniu folderów i po każdym przebiegu planisty): każdy materiał
  porównany z resztą PEŁNEJ galerii, kampanie i operatorzy jako spójne składowe krawędzi powyżej progów. Wcześniej galeria zależała od
  kolejności: przy galerii z 1 materiału przypadek 3 dostawał 0,856 z samego tekstu (brak tła do centrowania) i doklejał się do kampanii 1,
  a za nim 48. Budowa galerii z całej syntetyki v1 (42 materiały, prawda z generatora): ARI kampanii 0,596 → **0,956**, ARI operatora
  0,560 → 0,723. NASK-10: kampanie {1,2} i {48,61}, operator {1,2,3,48,61}, reszta osobno, czyli dokładnie nasz odczyt. Ryzyko: spójne
  składowe mogą łączyć łańcuchem; na bardzo małej galerii (3 materiały) przeliczenie bywa błędne, więc planista zapisuje je obok decyzji
  podjętej w chwili napływu, a nie zamiast niej.
- **Ochrona przed łańcuchem w drugim przebiegu** (`LINK_FRAC = 0,8`): krawędzie kampanii łączone od najsilniejszej, a dwie grupy (razem
  ponad 2 materiały) tylko wtedy, gdy średni wynik WSZYSTKICH par między nimi ≥ 0,8 progu kampanii (średnie wiązanie; reguła identycznego
  obrazu omija ten warunek). Na syntetyce v1 i NASK-10 wynik bez zmian dla ułamka od 0 do 1,0 (ARI 0,956 / 0,723, NASK zgodny z odczytem),
  bo nasze kampanie mają po 2–3 materiały i łańcuchów w nich nie ma; ochrona działa na łańcuchach A≈B≈C≈D z niepodobnymi końcami
  (test `test_regroup_average_link_blocks_chain`). Wartość 0,8 jest więc wyborem ostrożnym, nie dostrojonym: nie mamy danych z łańcuchami.
- **Kanał `infra`: co daje na NASK-10.** Łączy dwie pary: 1–2 (różne domeny, rejestracja u Dynadot w tej samej godzinie, 2026-10-08 ok.
  18:00 UTC; nowy, niezależny od domen dowód) oraz 2–3 (para NS Cloudflare i rejestracja NICENIC, ale z domeny `healthlinkq.pro`, którą
  oba materiały już dzielą: to był ten sam dowód liczony drugi raz). Podwójne liczenie usunięte: ślad infra pochodzący wyłącznie ze
  wspólnej domeny nie wchodzi do wyniku (`score.py`, `meta["infra_src"]`). Grupy NASK i test jak jury są identyczne z kanałem i bez niego:
  kanał dokłada przesłanki i siłę dowodu, decyzji na naszych 10 przypadkach nie zmienia.
- **Wiek domeny w chwili obserwacji** (data rejestracji z RDAP, chwila obserwacji z HAR): domeny stron oszustw 1, 2 i 48 zarejestrowano
  0–6 dni przed zapisem ruchu, 61 po 39 dniach, a legalny sklep (10) i strona 47 mają 115 i 243 dni. To opis w karcie materiału („świeża
  domena” ≤ 30 dni), nie składnik wyniku: dwie świeże domeny nie mają przez to wspólnego operatora.
- **Nowe domeny (np. materiały jury)**: tryb domyślny `auto` bierze zapisany plik, a brakujące domeny pyta krótko w DNS i RDAP (dwie nowe
  domeny w ok. 1 s; bez crt.sh; wynik tylko w pamięci). Bez sieci bezpiecznik pomija zapytania przez 10 minut. Test jak jury wymusza sam
  plik, żeby wynik nie zależał od sieci. Certyfikaty z crt.sh (wspólny certyfikat na kilka różnych domen) tylko w pełnym trybie
  `EMBSIM_INFRA=1`, bo crt.sh odpowiada wolno; w zapisanym pliku dla NASK ich nie ma.

- **Obrazy bez modelu** (`img`): odcisk SHA-256 bajtów obrazów strony z HAR i z zasobów `*_files`; pomijamy obrazy < 2 KB (ikonki,
  reakcje widżetów komentarzy, które krążą między zestawami). Na NASK łączy 1↔2 (11 obrazów), 48↔61 (6), 2↔3 (3) i jedną ikoną z CDN
  operatora sieć {1, 2, 48, 61}; żadnego połączenia poza naszym odczytem. Metadanych EXIF/PNG zrzutów nie używamy: opisują urządzenie
  zgłaszającego (iPhone przy 10 i 14, Wycinanie Windows przy 1, 3, 36, 48), więc łączyłyby po tym, kto zgłosił.
- **Reguła dokładna**: jeśli każdy obraz nowego materiału jest w jednym materiale galerii, a choć jeden występuje tylko w jednej kampanii,
  to ta kampania (np. ten sam zrzut drugi raz). Wspólna ikona sieci reguły nie uruchomi.
- **Pospolite usługi** (Google, Meta, CDN, czcionki) nie dają śladów hosta, zestawu ani schematu w ścieżce demonstratora. Wcześniej w galerii
  z 9 przypadków google.com u dwóch z nich wyglądał na rzadki wspólny ślad (61 z samym HAR „znaną kampanią” 10, wynik 0,98). Ewaluacja
  z §1 (`bench`, `cv`) czyta materiały bez tego filtra, więc jej liczby się nie zmieniają.
- **Próg 0,725** (poprzedni, pierwotna kalibracja): zostaw-jeden na NASK-10 i syntetyce v1, maksimum zrównoważonej trafności
  (0,875 przypiętych dobrze, 0,833 bez pary osobno; przy 0,95: 2/40 przypiętych). Na NASK każdy próg z (0,53; 0,82) daje 10/10. To kalibracja
  na naszych zbiorach dev, nie na zbiorze ukrytym. Kanał `img` jest dokładany w `Gallery` (wagi jak inne ślady, rotujący); `e_ref`
  przeskalowane tak, że materiały bez obrazów dostają dokładnie ten sam wynik co przed zmianą.
- **Wg kryteriów walidacji z opisu wyzwania** (test na zbiorze ukrytym, 15 nowych wariantów i przypadków kampanii, 11 negatywów, 13 wejść niepełnych):
  obecnie (0,62 + drugi przebieg): precyzja decyzji „znana kampania” 15/15, czułość 15/15, obce materiały zostawione osobno 11/11, nowa
  kampania znanego operatora rozpoznana 4/4, wejścia niepełne trafione dokładnie 10/13. Przy 0,725 było: precyzja 8/8, czułość 8/15,
  wejścia niepełne 8/13. Wyniki zapisane w `code/config/embsim/wyniki_jury.json`.
- **Słabe nadal**: zrzut samej reklamy nie trafia w stronę docelową innego materiału (B, 3 błędy). OCR działa (tesseract z językiem
  polskim), ale kreacja ma kilkanaście ogólnych słów („Wydarzenie, które wstrząsnęło całą Polską”) bez wspólnego tekstu z artykułem;
  to granica danych, nie błąd. Ocena wsadowa od pustej galerii (syntetyka v1, 42 materiały po kolei): kampanie precyzja 0,80, czułość 0,33, negatywy osobno 3/6.
  Pierwsze decyzje zapadają na galerii z 1–2 materiałów, gdzie rzadkość śladu nic nie znaczy.

## 6. Zbiory zewnętrzne  [prawdziwe, tylko tekst]

BuzzFeed-Webis (811 artykułów, 9 wydawców): tekst słabo odtwarza wydawcę (AUC 0,55), bo wszystkie artykuły są z jednego tygodnia o tym samym.
Dezinformacja i teksty scam się nie mieszają (połączone międzyklasowo 0,0001), ale to prosty przypadek (angielski vs polskie szablony).

## 7. Znane problemy i ograniczenia

1. **Brak etykiet prawdziwych kampanii.** Etykieta „twórca” to `page_id`, a „scam” to zdjęcie ≥50% reklam przez Metę (sygnał egzekwowania).
2. **Progi z syntetyki nie przenoszą się.** Na Mecie optimum ok. 0,5 wobec 0,95; na stronach (NASK + syntetyka v1) 0,725 (§5a).
3. **Formuła śladów** zawyża dowód dla wartości o średniej częstości (targetowanie). Poprawka (np. `max_df` albo skala rzadkości) do zmierzenia.
4. **Doklejanie nowych wzorców** do znanych kampanii: ok. 0,15 na syntetyce; na Mecie odrzucenie nowych 0,78–0,83 przy najlepszych profilach.
5. **Poziom operatora:** miara „zawierania” jest nieznacznie gorsza od Jaccarda (−0,019 ARI).
6. **Osoby i logotypy** na obrazie: brak. Zrzut bez HTML i HAR zależy od OCR, a lokalny `tesseract` nie ma języka polskiego (kontener ma).
7. **Reklamy zdjęte przez Metę** (ok. jedna trzecia próbki S1) nie mają tekstu ani domeny.
8. **Skala:** wyszukiwanie z blokowaniem kandydatów kosztuje 0,3–47 ms na zapytanie przy galerii ok. 10 tys.; 97 tys. nie mierzyliśmy.
9. Próbka S1 ma 50% twórców scam (populacja ok. 16%), więc precyzje liczone na S1 nie przenoszą się na całą Metę.

## 5b. Wizerunki osób i bliskie duplikaty obrazów  [NASK-10]

Wykrywanie twarzy (YuNet) i porównanie osadzeń (SFace, kosinus ≥ 0,45 = ta sama osoba), `embsim/faces.py`; bliskie duplikaty obrazów: dHash 64 bity,
odległość Hamminga ≤ 6, `embsim/imghash.py`. Oba bez treningu u nas, bez nazw osób.

- Na 10 przypadkach NASK twarz łączy przypadki 1 i 2 (kosinus 1,0, ta sama kampania) oraz 48 i 61 (0,52, ta sama kampania); 1 i 48 (0,73) dzielą osobę
  mimo różnych kampanii (ta sama sieć wg naszego odczytu). Bliskie duplikaty obrazów łączą 2 i 61 oraz 3 i 61 (zrzut strony banku, odległość 4).
- **Jako składnik wzoru kanał twarzy nie pomógł:** test formatów (B) 8/13 → 7/13, A (10/10) i C (13/20) bez zmian; zrzuty bez tekstu zyskały wynik
  (0,00 → 0,23–0,38) ale nie przekroczyły progu. Dlatego twarz i podobny obraz są **przesłankami poza wynikiem** (`Match.extra_shared`, widoczne w „Trzech
  najsilniejszych powodach”), a kanał `face` w `score.py` jest dostępny do włączenia wagą w konfiguracji.
- Ograniczenia: ta sama osoba występuje też na legalnych stronach (czysta przesłanka, nie dowód); na NASK nie mamy etykiet osób, więc nie mierzymy
  precyzji dopasowania twarzy; logotypów wewnątrz zrzutu nie wykrywamy.

## 7a. Przyrostowe dodawanie do galerii (tak działa demo i scraper)  [syntetyka v2, dev, 6 światów]

Dotychczasowe wyniki grupowania były wsadowe (CV). Przy dodawaniu materiałów po jednym (`Gallery.add`, kolejność losowa, konfiguracja domyślna)
jest gorzej: ARI kampanii 0,609 (wsadowo 0,749), ARI operatora 0,07–0,74 zależnie od świata, a **legalne strony (negatywy) wpadają do operatorów
oszustw** przez wspólne pospolite ślady (np. `/static`, `/artykul`): w 4 z 6 światów wszystkie, razem 27 z 42 przy progu operatora 0,25.

| próg operatora (przyrostowo) | ARI operatora | legalne strony wpięte w operator | grup operatora / prawdziwych |
|---|---|---|---|
| 0,25 (domyślny) | 0,562 | 27 z 42 | 46 / 84 |
| 0,45 | 0,652 | 10 z 42 | 79 / 84 |
| 0,60 | 0,476 | 8 z 42 | 140 / 84 |
| 0,75 i 0,90 | 0,488 | 0 z 42 | 164 / 84 (każdy osobno) |

Żaden próg nie rozwiązuje obu problemów: zlewania operatorów i wpinania legalnych stron.

**Limit częstości śladów (sprawdzony, nie pomaga).** `Corpus(hub_frac=…)` ignoruje ślad w więcej niż ułamku galerii (min. 6 materiałów; domyślnie
wyłączony). Progi kalibrowane od nowa na dev v2, ocena przyrostowa na tych samych 6 światach:

| limit | ARI operatora (próg skalibrowany / 0,45) | ARI kampanii | legalne w operatorze (skalibrowany / 0,45) |
|---|---|---|---|
| brak | 0,562 / 0,652 | 0,609 | 27 / 10 z 42 |
| 15% galerii | 0,176 / 0,588 | 0,504 | 19 / 8 z 42 |
| 25% | 0,238 / 0,533 | 0,424 | 21 / 10 z 42 |
| 40% | 0,330 / 0,539 | 0,431 | 21 / 10 z 42 |

Limit pogarsza ARI (kampanii najbardziej: ucina ślady, które w małych galeriach skleją prawdziwe kampanie) i prawie nie zmniejsza liczby wpiętych
legalnych stron.

**Reguła „operator tylko przy rzadkim wspólnym śladzie” (działa).** Decyzja „znany operator” wymaga, by materiał dzielił z galerią ślad
obecny w co najwyżej `op_rare_df` materiałach galerii (`Config.op_rare_df`, tylko ścieżka `Gallery.query`; wsad i kampania bez zmian). Dobór na dev
(próg operatora 0,25, konfiguracja `v3_mixed_pca` bez innych zmian):

| `op_rare_df` | ARI operatora | legalne w operatorze | grup operatora / prawdziwych |
|---|---|---|---|
| brak | 0,562 | 27 z 42 | 46 / 84 |
| 16 | 0,578 | 27 | 47 |
| 8 | 0,547 | 21 | 48 |
| 4 | 0,621 | 10 | 61 |
| **2** | **0,705** | **7** | **76** |

Potwierdzenie na świeżych światach testowych v2 (30–35, użyte raz, tylko dla wartości 2 i bez): ARI operatora **0,415 → 0,599**, legalne w operatorze
**30 → 9 z 43**, grup 44 → 78 przy 86 prawdziwych; ARI kampanii bez zmian (0,583). Zamrożona konfiguracja `v4_rare2`. **Poprawka po teście na zbiorze ukrytym (`embsim/jury.py`):** limit 2 pogarsza jego wynik (B: 3 → 5 błędów, C: 2 → 4 błędy, bo w małej galerii kampania z 3 wariantami ma ślad w 3 materiałach i przestaje być „rzadki”); limity 4, 6 i 10 nie pogarszają niczego (B 8/2/3, C 13/5/2 jak bez reguły). Domyślny jest więc `v4_rare4` (na dev v2: ARI operatora 0,621 zamiast 0,705 dla 2, legalne w operatorze 10 z 42 zamiast 7; na Mecie 0,633/0,656, bez gorszego wyniku niż dla 2). Uwaga: tę wartość wybrano po obejrzeniu tego testu, więc jej wynik w tym teście nie jest już niezależny.
**Sprawdzenie na prawdziwych reklamach Meta** (`embsim/meta_incremental.py`: 665 reklam z treścią od 100 losowych twórców, min. 3 reklamy, do 10 na twórcę,
dodawane chronologicznie przez `Gallery.add`; prawdy o operatorach brak, przybliżeniem jest twórca `page_id`, więc jeden operator z kilkoma stronami
liczy się jako błąd; operator ma tu tylko kanał domeny):

| próg kampanii | `op_rare_df` | ARI operatora | ARI kampanii | reklamy w grupach z >1 twórcą | grup operatora (twórców 100) |
|---|---|---|---|---|---|
| 0,95 | brak | 0,568 | 0,624 | 38% | 132 |
| 0,95 | 2 | 0,620 | 0,624 | 20% | 201 |
| 0,95 | 4 | 0,633 | 0,624 | 23% | 185 |
| 0,5 | brak | 0,555 | 0,708 | 45% | 117 |
| 0,5 | 2 | 0,650 | 0,708 | 30% | 151 |
| 0,5 | 4 | 0,656 | 0,708 | 32% | 143 |

Reguła pomaga także na Mecie (ARI operatora +0,05…0,10, błędne sklejenia −15…−18 pp), kosztem rozdrobnienia (143–201 grup przy 100 twórcach).
Limity 2 i 4 dają podobnie. Próg kampanii 0,5 daje lepszy ARI kampanii (0,708) niż 0,95 (0,624), co potwierdza, że próg z syntetyki jest na Mecie za wysoki.
Próbka mała, jedno losowanie (ziarno 7), bez przedziałów ufności.

Zastrzeżenia: wartość bezwzględna (2) zależy od wielkości galerii (światy mają 20–40 materiałów; w dużej galerii prawdziwy operator z wieloma
kampaniami przekroczy limit, więc trzeba go będzie skalować), wynik dotyczy syntetyki, a na prawdziwych danych nie był sprawdzany.
Naprawiony przy okazji błąd: dzielenie przez zero w normalizacji, gdy w galerii dominują identyczne teksty.

## 7b. Poprawki po audycie backendu (22.11.2026)

Naprawione i objęte testami (`code/tests/test_api.py`, `test_exact_img.py`); wyniki testu na zbiorze ukrytym bez zmian (A 10/10, B 8/13, C 13/20):

- **Kopie tego samego tekstu** zerowały korektę PCA i po kilku kopiach otwierały nową kampanię (wynik 0,00). Korekta liczona jest teraz na unikalnych wektorach,
  a wektor zdegenerowany jest traktowany jako brak kanału. Test: 10 kopii tekstu to jedna kampania.
- **Jedno wspólne zdjęcie** (logo, zasób szablonu) nie wymusza już „znanej kampanii” przy wyniku 0,00. Reguła dokładna wymaga kompletnego zestawu co najmniej
  dwóch obrazów albo materiału będącego samym zrzutem.
- **Pierwszy ślad nowego rodzaju po wielu materiałach** przerywał zapytanie (`KeyError: 'img'`); `idf` toleruje kanał, którego nie było przy ostatnim dopasowaniu.
- **Restart zmieniał werdykt operatora:** późne dodawanie aktualizowało liczniki tylko poziomu kampanii. Liczniki śladów (idf, bramka rzadkości, huby) są
  teraz aktualizowane w obu poziomach. Słownik TF-IDF, μ i PCA nadal są dopasowywane rzadziej niż liczniki, więc wynik tekstowy może się nieznacznie
  różnić po restarcie (wersjonowanie transformacji: do zrobienia).
- **Materiał bez dowodu** (sam `page_id`) nie tworzy kampanii ani operatora: werdykt „brak danych”, nic nie jest dopisywane do galerii.
- **Domeny:** `registered()` zna najczęstsze sufiksy wieloczłonowe (`com.pl`, `co.uk` i inne) i zostawia adresy IPv4 w całości. To podzbiór Public Suffix List,
  nie cała lista.

- **Profile progów (pkt 12):** `Gallery(profile="strony" | "meta")` ustawia progi dla rodzaju źródła (strony: kampania 0,725; reklamy Meta: 0,5), te same w interfejsie,
  CLI (`--profile`), scraperze i teście; nazwa profilu trafia do `Decision.profile`.
- **Niejednoznaczność (pkt 13):** gdy druga kampania ma wynik różniący się o mniej niż 0,05 i też przekracza próg, wyjaśnienie pokazuje obie hipotezy
  (`Decision.alternative`); werdykt się nie zmienia.

Z audytu zostaje do zrobienia: rozdzielenie tożsamości materiału, odcisku zawartości i statusu importu (pkt 6), spójny zapis kampanii, operatora i konta w grafie
oraz transakcyjność liczników w `graph/scrape.py` (pkt 7–8, część koleżanki), wersjonowany trwały zapis galerii (24), niezależny zbiór relacji kampanijnych (21) i pozostałe rekomendacje P1/P2.

## 8. Pochodzenie danych

| zbiór | źródło | licencja / uwagi |
|---|---|---|
| reklamy Meta (97 447; próbka S1 14 936) | Meta Ad Library API, zebrane przez zespół | warunki Mety; poza repo |
| 10 przypadków NASK | organizator | tylko na potrzeby wyzwania; prywatne, poza repo |
| skany urlscan (117) | urlscan.io, wyszukiwanie publiczne | poza repo |
| BuzzFeed-Webis | Zenodo | CC BY 4.0; poza repo |
| syntetyka v1, v2 | generatory w repo (`fejki/demo/synth_cases.py`, `embsim/synth2.py`) | w repo |
