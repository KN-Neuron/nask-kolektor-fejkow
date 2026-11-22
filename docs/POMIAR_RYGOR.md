# Rygor pomiaru: sprawdzenia po audycie

Uzupełnienie do [WYNIKI.md](WYNIKI.md). Każdy punkt ma polecenie, które go odtwarza.

## 1. Wyciek `e_ref` w walidacji krzyżowej (audyt, pkt 19)

Wspólne `e_ref` (mediana po światach z mediany dostępności par kanałów, statystyka bez etykiet) było liczone po wszystkich światach przed podziałem
zewnętrznym. `python -m embsim.cv` sprawdza teraz, czy zmieniłoby się, gdyby liczyć je tylko na światach treningowych każdego foldu.

- Wynik: **maksymalne odchylenie 0,0000, żaden z 90 foldów** (5 foldów × 3 podziały × konfiguracje) się nie różni. `e_ref` przyjmuje wartości dyskretne (np. 4 z 6 kanałów).
- Liczby CV się nie zmieniły: kampania ARI 0,749 [0,730; 0,767], błędne łączenie 0,148 [0,131; 0,166] (80 światów).
- Wyciek jest formalny i nie wpływa na wynik. Sprawdzenie zostaje w `cv.py` jako stały krok, zapisane w `artifacts/cv/report.json` (`e_ref_wrażliwość`).

## 2. Wybór wewnętrzny (nested) woli inną konfigurację niż domyślna

Wybór wewnętrzny wskazał `contain + PCA` w 15 z 15 foldów.

| konfiguracja | kampania ARI | błędne łączenie obcych (niżej = lepiej) | operator ARI |
|---|---|---|---|
| `contain + PCA` (wybór wewnętrzny) | 0,772 [0,756; 0,788] | 0,180 [0,161; 0,198] | 0,759 [0,737; 0,780] |
| domyślna (`overlap` dla kampanii, `contain` dla operatora) | 0,749 [0,730; 0,767] | 0,148 [0,131; 0,166] | 0,759 [0,737; 0,780] |

Zostawiamy domyślną kosztem ok. 0,02 ARI, bo rzadziej łączy obce materiały. To świadomy wybór kryterium „niełączenia obcych”, nie wynik procedury doboru.

## 3. Stabilność progu kampanii

`python -m embsim.threshold_stability`: 43 materiały z testu na zbiorze ukrytym (A: przypadki NASK ukryte po kolei, B: inne formaty, C: syntetyka).
Oczekiwane decyzje to nasz odczyt danych NASK, nie etykiety organizatora.

| podzbiór | n | trafność przy progu 0,62 | zrównoważona trafność, plateau progów | leave-one-out: trafność / wybrane progi |
|---|---|---|---|---|
| wszystko | 43 | 0,884 | 0,911 przy 0,57–0,64 | 0,884 / 0,60–0,61 |
| bez zrzutów bez tekstu i śladów | 40 | 0,950 | 0,960 przy 0,57–0,64 | 0,950 / 0,60–0,61 |
| tylko A i C | 30 | 1,000 | 1,000 przy 0,57–0,67 | 1,000 / 0,61–0,64 |

Najsilniejszy negatyw ma wynik 0,56. Leave-one-out (próg dobierany bez jednego materiału i sprawdzany na nim) daje tę samą trafność co dobór na całości, więc próg nie jest
dostrojony do pojedynczych przypadków. Zastrzeżenia: zapas do najmocniejszego negatywu to 0,06, materiałów jest mało i pochodzą z tego samego źródła co kalibracja. To dowód
stabilności procedury, nie jej trafności na nowych danych.

## 3a. Dobór progu kampanii po podmiotach (obecny próg 0,70)

Pomiar w pkt 3 dotyczy jednego układu galerii (test jury), w którym najsilniejszy negatyw ma 0,56. Rozkład wyniku zależy jednak od składu galerii
(idf śladów i tło tekstu liczone są na galerii), więc ten sam próg zachowuje się różnie w różnych galeriach. Skrypt `code/scripts/prog_kampanii.py`
zbiera najlepsze dopasowanie w trzech układach i dobiera próg **z podziałem po podmiotach**:

- **podmiot** = operator syntetyki z `prawda.json` (O1–O6, każdy negatyw osobno); w NASK sieć {1, 2, 3, 48, 61} (wspólna infrastruktura) jako jeden
  podmiot, pozostałe przypadki osobno; razem 18 podmiotów. Wszystkie pytania o materiały jednego podmiotu idą razem do doboru albo do oceny;
- układy: **jury** (jak test jury, A+C, 30 pytań), **pełna** (zostaw-jeden-materiał, galeria = reszta, 52 pytania), **mieszane** (105 losowych galerii
  NASK + syntetyka, każdy materiał z prawdopodobieństwem U(0,4; 0,95), pytania o materiały spoza galerii jako komplet, sam HTML albo sam HAR;
  581 pytań; pytania samym HAR-em syntetyki pominięte, bo to atrapy ok. 600 B z samymi adresami);
- dobór zagnieżdżony: próg z podmiotów treningowych (środek przedziału z maksymalną zrównoważoną trafnością), ocena na odłożonych.

Zrównoważona trafność (`scripts/prog_kampanii.py zbierz`, potem `dobierz`; wyniki w `code/artifacts/prog/wyniki.json`):

| układ | próg wybierany bez podmiotu | 0,62 | 0,665 | **0,70** | 0,725 | 0,745 |
|---|---|---|---|---|---|---|
| jury | 0,615–0,635 | 1,000 | 1,000 | **0,967** | 0,767 | 0,667 |
| pełna | 0,685–0,690 | 0,779 | 0,904 | **0,904** | 0,854 | 0,792 |
| mieszane | 0,755 | 0,736 | 0,755 | **0,774** | 0,801 | 0,841 |

- **Wybór wewnątrz układu jest stabilny względem podmiotów** (rozrzut do 0,02): żaden operator ani przypadek NASK nie przesuwa progu sam,
  więc dzielenie po materiale zamiast po podmiocie (pkt 3) nie zawyżało wyniku. **Optima układów się różnią** (0,62 / 0,685 / 0,755) z powodu składu galerii. Efekt jest duży: gdy w trybie „pełna” NASK i syntetyka
  tworzą JEDNĄ galerię, wszystkie wyniki rosną o ok. 0,05 (przypadek NASK 3, obcy dla kampanii, z 0,53 do 0,73), dlatego „pełna” to galeria z reszty
  tego samego zbioru. Optimum mieszanych zależy od losowania galerii (inne ziarno dało 0,74).
- **0,70 ma najmniejszą maksymalną stratę** do najlepszego z progów porównywanych w danym układzie: 0,067 (0,665: 0,086; 0,62: 0,125; 0,725: 0,233). Nie znamy
  składu galerii przy ocenie jury, więc wybieramy próg najbezpieczniejszy dla wszystkich trzech.
- Koszt względem 0,62 w teście jury: B 10/13 → 8/13 (przypadki 48 i 61 jako sam HTML, wynik 0,64 i 0,65, dostają „sieć” z właściwą grupą), C 20/20 → 19/20
  (s012, 0,674). Zysk: pełna galeria 5 → 2 fałszywe połączenia; galerie mieszane 16,7 → 14,3 fałszywych połączeń na 100 pytań.
- Progi nie naprawią: pytań samym HAR-em w NASK (przypadki 1, 2, 48, 61 dostają 0,98–1,0 do dowolnego materiału sieci, bo HAR niesie głównie
  infrastrukturę, a przypadek 14 dokleja się z ok. 0,88).
- Zastrzeżenia: 18 podmiotów, wszystkie pozytywy NASK to jeden podmiot (sieć), większość pozytywów to 6 operatorów z naszego generatora.

## 4. Etykieta „reklama zdjęta przez Metę”

`python -m embsim.meta_harm` (próbka S1; twórcy dzieleni na galerię 60% i test 40% przed jakimkolwiek przetwarzaniem; 3 ziarna; bez progu, więc bez wycieku z walidacji).
Etykieta twórcy: ma co najmniej jedną zdjętą reklamę. To sygnał egzekwowania, nie dowód oszustwa.

| profil | AUROC [95% CI, bootstrap po twórcach] | bez dokładnych duplikatów tekstu | precyzja w górnych 10% (baza 0,32) |
|---|---|---|---|
| tekst gęsty (PCA) | 0,629 [0,597; 0,657] | 0,568 | 0,54 |
| tekst leksykalny | 0,659 [0,628; 0,691] | 0,616 | 0,57 |
| tekst + leksyka + domena (wzór) | 0,642 [0,608; 0,673] | 0,592 | 0,58 |

Sygnał jest słaby. Znaczna część to kopiowanie treści między twórcami, a etykieta jest szumna (Meta zdejmuje też spam, a twórca bez zdjętych reklam może być oszustem
jeszcze nieprzyłapanym).

## 5. Ścieżka online od pustej galerii na reklamach Meta (luka: ocena strumieniowa)

`python -m embsim.online_eval`: 795 reklam z treścią od 120 losowych twórców (min. 3 reklamy, do 10 na twórcę), chronologicznie, galeria zaczyna pusta,
każda reklama oceniana kodem, którego używają interfejs, CLI i scraper (`Gallery.query` / `add`, profil „meta”). Prawdy kampanii nie ma; proxy to twórca.
Grupy nie wpływają na wynik kampanii, więc jeden przebieg pozwala przeliczyć dowolny próg. Przedziały: bootstrap po twórcach.

| próg kampanii | uznane | precyzja | czułość (twórca już w galerii) | odrzucenie nowych twórców |
|---|---|---|---|---|
| 0,3 | 633 | 0,81 [0,74; 0,89] | 0,76 [0,69; 0,83] | 0,80 [0,73; 0,87] |
| **0,5 (profil meta)** | 587 | 0,82 [0,74; 0,90] | 0,71 [0,64; 0,78] | 0,87 [0,81; 0,92] |
| 0,7 | 545 | 0,82 [0,73; 0,90] | 0,66 [0,59; 0,74] | 0,92 [0,86; 0,96] |
| 0,9 | 515 | 0,82 [0,73; 0,90] | 0,62 [0,55; 0,71] | 0,92 [0,87; 0,97] |

- Rozbicie po rozmiarze galerii przy progu 0,5: do 100 materiałów precyzja 1,00 i czułość 0,85 (mało twórców do pomylenia), 100–300: 0,77 i 0,64, ponad 300: 0,81 i 0,71.
- **Precyzja nie zależy od progu** (0,81–0,82), więc próg wymienia tylko czułość na odrzucanie nowych. Powód: **90% „błędów” (95 z 106) to reklamy o wyniku ≥ 0,95**, czyli
  prawie identyczny tekst u innego twórcy. To ta sama treść używana przez wielu twórców (realny sygnał wspólnej kampanii lub operatora), a proxy „twórca” liczy ją jako pomyłkę.
  Po ich wyłączeniu precyzja wynosi 0,98. Prawdziwą precyzję trzeba mierzyć na etykietach kampanii, których nie mamy.
- Próg 0,5 (profil „meta”) wypada rozsądnie; podniesienie go zwiększa odrzucanie nowych kosztem czułości i niczego nie poprawia w precyzji.

## 6. Targetowanie reklam Meta jako przesłanka (luka: cecha wyłączona z wyniku)

Jako składnik wyniku targetowanie (wiek, płeć, kraje) obniżało jakość: AUROC „znany czy nowy twórca” spadało z 0,77 do 0,64, a próg dobierał się do 1,00 (`stream_eval.py`).
Zostaje poza wynikiem. Zmierzyliśmy je jako **przesłankę** w tym samym przebiegu online co w pkt 5 (`online_eval.py`): czy zgodność targetowania z najlepszym dopasowaniem
mówi coś o tym, że to ten sam twórca (próg 0,5, reklamy uznane za znaną kampanię, z danymi o targetowaniu po obu stronach):

| targetowanie względem najlepszego dopasowania | reklamy | precyzja (ten sam twórca) |
|---|---|---|
| to samo | 448 | 0,89 |
| inne | 139 | 0,60 |

Wśród reklam poniżej progu to samo targetowanie ma 82 z 207, z poprawnym twórcą najlepszego dopasowania w 0,55 przypadków.

Wniosek: zgodność targetowania jest użyteczną przesłanką („ten sam profil odbiorców”), ale mierzy **tożsamość reklamodawcy**, nie wspólną kampanię: twórca zwykle powtarza
ustawienia odbiorców, więc zgodność idzie w parze z tym samym twórcą, czyli z proxy, którym mierzymy. Nie traktujemy jej jako dowodu kampanii. Dodanie jej do karty analityka
(poza wynikiem, jak twarz) wymaga zmiany w `Gallery.query`/`analyze.py` i nie jest wykonane.

## 7. Samotny zrzut reklamy: czy porównanie z treścią kreacji pomoże (pkt 5 z listy luk)

Hipoteza: zrzut bez tekstu strony i bez śladów (test B, „sam zrzut (OCR)”, 3 błędy: przypadki 1, 48 i 61) trzeba porównywać z treścią kreacji reklam, a nie z treścią stron.
Sprawdzenie na NASK-10 (OCR polski + angielski, galeria bez przypadku zapytania):

- Tekst z OCR zrzutów to **teksty kreacji, które różnią się między wariantami tej samej kampanii**: przypadek 1 „Wydarzenie, które wstrząsnęło całą Polską”, 48 „KŁAMIECIE MILIONOM
  POLAKÓW!”, 61 „Dziedzictwo gwiazd dla zwykłych ludzi”. Wspólne są tylko elementy interfejsu („Sponsorowane”, „Dowiedz się więcej”).
- Dopisanie tekstu z OCR zrzutów do tekstu przypadków w galerii nie zmieniło żadnego wyniku (kampania 0,00 dla 1, 48 i 61 w obu wariantach, w tym wynik kanału tekstowego 0,13 i leksykalnego 0,00).

Wniosek: **porównanie z treścią kreacji nie rozwiąże problemu, bo w kampanii zmienia się właśnie treść kreacji, a infrastruktura (to, co łączy warianty) nie jest widoczna na zrzucie reklamy.**
Jedyny ślad, który zrzut niesie, to wizerunek: ta sama twarz łączy 1 z 2 (kosinus 1,00) i 48 z 61 (0,52). Twarz jest już pokazywana jako przesłanka w wyjaśnieniu (`Match.extra_shared`, „wizerunek”),
więc analityk widzi kandydata, mimo że werdykt dla samego zrzutu pozostaje „nowy wzorzec”: za mało dowodów, żeby przypisać kampanię. Włączenie twarzy do wyniku dla samych zrzutów
dało wynik 0,23–0,38 przy progu 0,62, czyli nie wystarcza. Zostawiamy to jako znane ograniczenie: sam zrzut reklamy bez strony docelowej nie wystarcza do przypisania kampanii.
