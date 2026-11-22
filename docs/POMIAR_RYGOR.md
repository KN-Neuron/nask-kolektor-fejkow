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

## 6. Targetowanie reklam Meta (luka: cecha wyłączona)

Targetowanie (wiek, płeć, kraje) jako składnik wyniku obniżało jakość: AUROC „znany czy nowy twórca” spadało z 0,77 do 0,64, a próg dobierał się do 1,00 (`stream_eval.py`,
profile „treść” i „treść + płatnik”). Cecha zostaje wyłączona z wyniku. Nie sprawdzaliśmy jej jako przesłanki poza wynikiem (jak twarze), więc jej wartość wyjaśniająca jest niezmierzona.
