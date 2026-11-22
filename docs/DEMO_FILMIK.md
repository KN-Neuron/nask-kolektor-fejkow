# Demo pod filmik konkursowy (2–3 min)

Scenariusz przechodzony 22.11.2026 na `main` = `0838cbf` w przeglądarce, okno 1440×900. Zrzuty z tego przejścia: `docs/demo_filmik/`.
Liczby niżej to faktyczne wyniki z tego przebiegu (krok 2 policzony z kodu, bo wgrywania plików nie dało się wykonać automatem).

## Przygotowanie (raz, przed nagraniem)

```bash
make demo                      # http://localhost:8501 (albo kontener, gdy obraz będzie gotowy)
```

- Uwaga: na porcie 8501 może wisieć stare demo sprzed dzisiejszych zmian (na tej maszynie działało od 21.11, 18:03). Przed nagraniem
  zatrzymaj je albo uruchom świeże na innym porcie (`--server.port 8621`), inaczej na filmie zabraknie kanału infra i bazy twarzy.
- Pusta galeria na start: `EMBSIM_GALLERY=/tmp/galeria_filmik.jsonl make demo` (inaczej wczyta zapisaną galerię z `code/artifacts`).
- Folder do kroku 2 (galeria BEZ przypadku 2, same dowiązania, w `.gitignore`): `data/dane/demo_bez_2/`. Odtworzenie:
  `mkdir -p data/dane/demo_bez_2 && for d in data/dane/do_udostępnienia/*/; do n=$(basename "$d"); [ "$n" = 2 ] || ln -sfn "$PWD/$d" data/dane/demo_bez_2/$n; done`
- Okno przeglądarki szerokie (1440×900): przy wąskim pasek boczny nachodzi na treść i łatwo kliknąć suwak progu.
- Nagrywanie ekranu: QuickTime (Plik → Nowe nagranie ekranu) albo `screencapture -v plik.mov`; terminal musi mieć uprawnienie
  „Nagrywanie ekranu” (Ustawienia systemowe → Prywatność). Na tej maszynie terminal go NIE ma (zrzut pokazał tylko tapetę), więc filmu nie nagrałem.

## Kolejność (pod kryteria oceny)

Przykłady z pierwszego panelu (krok 3 i 4) PODMIENIAJĄ galerię na syntetyczną (14 materiałów), więc robimy je na końcu albo po nich
wczytujemy NASK jeszcze raz.

| # | co robisz | co widać (wynik z przebiegu) | kryterium |
|---|---|---|---|
| 1 | Pasek boczny → „Zbuduj galerię”, folder `data/dane/demo_bez_2` (albo pełny `do_udostępnienia`), zaznacz OCR, „Dodaj przypadki z folderów” | „Przyjęto 9 folderów.”, galeria 9 / 8 / 7 (pełny folder: „Przyjęto 10 folderów.”, 10 / 8 / 6) · zrzut `1_galeria.jpg` | kompletność |
| 2 | Zakładka „Analiza”, przeciągnij z `do_udostępnienia/2` trzy pliki: `acrosscommunities.live.har`, `healthlinkq.pro.har`, plik `.html` (bez folderu `_files`), „Analizuj” | **Znana kampania K1, wynik 0,94** (próg 0,62); najbliższy materiał 1; powody: podobne brzmienie tekstu 1,00, te same obrazy 1,00 (logo-gazeta.svg, brzoska-avatar.jpg, shot-pko.webp), zestaw zasobów `/aio-static/sdk`, `/api/v1`, schemat `utm_campaign,utm_content,utm_id,utm_medium,utm_visit`, **ta sama obsługa domen: rejestracja Dynadot 2026-10-08 ok. 18:00 UTC**, **znane osoby z bazy wizerunków: Mateusz Morawiecki, Rafał Brzoska**. Sekcja „2. Cechy”: domeny `acrosscommunities.live` i `healthlinkq.pro` zarejestrowane **w dniu zapisu ruchu, świeża domena** | jakość korelacji, cechy, interpretowalność |
| 3 | Rozwiń „Jak to działa”, „Pokaż: nowa kampania znanego operatora” | **Znany operator, nowa kampania**: wynik kampanii 0,59 (próg 0,62), operatora 0,48 (próg 0,25); powody: ten sam zestaw zasobów 1,00, ten sam piksel śledzący 0,90, schemat adresu 0,83 · `3_znany_operator.jpg` | rozpoznanie wariantów i nowych kampanii |
| 4 | „Pokaż: obcy materiał (legalna strona)” | **Nowy wzorzec, nie doklejam do żadnej grupy**: wynik kampanii 0,00, operatora 0,00 · `4_nowy_wzorzec.jpg` | niełączenie obcych |
| 5 | Wczytaj znów pełny `do_udostępnienia` (jeśli robiłeś 3–4), sekcja „Wiele materiałów naraz”, folder `data/testy_apki/A_przypadki_czesciowe`, OCR, „Oceń wszystkie” | **Znana kampania: 5** (47 sam HAR → K7, 48 sam HAR → K8, 1 sam zrzut → K1, 3 sam zrzut → K2, 61 tylko strona produktu → K8), powód „identyczne obrazy jak w … (reguła dokładna)” · `5_wsadowo.jpg` | odporność na braki i format |
| 6 | Zakładka „Klastry”, galeria offline | tabela operatorów (O1: 3 kampanie, 5 materiałów); rysunek: operator O1 z kampaniami K1 {1, 2}, K2 {3}, K8 {48, 61}; „1, 2 to jedna kampania: obsługa domen: rejestracja domeny Dynadot Inc, 2026-10-08 ok. 18:00 UTC; te same obrazy (12)” · `6a_klastry.jpg`, `6b_rysunek.jpg` | czytelność |
| 7 | Zakładka „Jak liczymy i wyniki” | jeden wzór z wagami z góry, progi 0,62 / 0,25, test na zbiorze ukrytym · `7_jak_liczymy.jpg` | metodyka |

Tekst lektora (propozycja, ok. 2,5 min): „Wczytujemy znane przypadki NASK: system grupuje je w kampanie i operatorów… Nowa strona: znana
kampania, bo te same obrazy, ten sam zestaw zasobów i domeny zarejestrowane u Dynadot w tej samej godzinie; na obrazach ci sami ludzie,
rozpoznani z bazy wizerunków… Inna oferta na tej samej infrastrukturze: ten sam operator, nowa kampania… Legalna strona o tych samych
osobach: nic nie doklejamy… Niepełne materiały, sam zrzut albo sam HAR: 5 na 5… Klaster: widać, co dokładnie skleja grupę…”

## Uwagi z przejścia (do poprawy, kodu nie zmieniałem)

1. **Zakładka „Jak liczymy”, akapit pod wzorem**: „ta sama osoba na obrazach (detektor YuNet i SFace, **bez nazw osób**)” jest nieaktualne
   od `042e23e` (baza znanych osób). Niżej na tej samej stronie jest już poprawny opis bazy wizerunków. Plik: `code/src/embsim/app.py` / `guide.py`.
2. **Przykłady podmieniają galerię** bez ostrzeżenia (NASK 10/8/6 → syntetyka 14/5/3). Na filmie robić je po kroku 6 albo dopisać w UI
   informację „przykład zastępuje bieżącą galerię”.
3. **Ocena wsadowa** pokazuje „Znana kampania” z wynikiem 0,118 / 0,063 dla samych zrzutów: to reguła dokładna (identyczny plik), a powód to
   mówi, ale na filmie warto to jednym zdaniem skomentować, żeby niski wynik nie wyglądał na błąd.
4. Wgrywania plików (krok 2) nie da się zautomatyzować w przeglądarce, której używałem; wynik kroku 2 pochodzi z tego samego kodu
   (`case_from_inputs` + `Gallery.query`), nie z kliknięcia.
