# Kolekcjoner Fejków (Follow the Fake): HackNation × NASK

Narzędzie, które z pojedynczych podejrzanych reklam i stron wydobywa wspólne ślady, łączy je w kampanie i pokazuje, **dlaczego** materiały
zostały połączone. Wyzwanie zgłosił Ośrodek Badań nad Bezpieczeństwem Sztucznej Inteligencji NASK PIB.

> **Repozytorium jest prywatne i musi takie zostać, dopóki zawiera opisy danych organizatora.** Danych organizatora nie wolno publicznie
> rozpowszechniać. Surowe dane nie są w repo (są w `.gitignore`).

## Metoda w jednym akapicie

Każdy materiał (zrzut, HTML, ruch sieciowy HAR, reklama z Meta, tekst, adres) zamieniamy na kilka kanałów cech: **tekst** (embedding i
TF-IDF znaków) oraz **ślady** (domeny, zestaw zasobów strony, schemat parametrów adresu, piksele). Podobieństwo to **jedno wyrażenie
z wagami ustalonymi z góry, bez uczenia** ([docs/14_WZOR_PODOBIENSTWA.md](docs/14_WZOR_PODOBIENSTWA.md)). Nowy materiał trafia do jednej z
trzech decyzji: *znana kampania*, *znany operator, nowa kampania* albo *nowy wzorzec* (nie doklejamy). Każdą decyzję uzasadniają trzy
najsilniejsze powody. Szczegóły: [docs/METODYKA.md](docs/METODYKA.md).

## Uruchomienie

```bash
make install        # venv + zależności (ok. 2 min, ok. 1,3 GB z torchem)
make test           # testy (bez danych)
make demo           # interfejs: http://localhost:8501
make docker-run     # to samo w kontenerze (model tekstu jest w obrazie, działa offline)
```

Galerię znanych materiałów buduje się w pasku bocznym interfejsu z folderu przypadków (HTML, HAR, zrzuty) i z pliku reklam Meta (JSONL).
Zrzut bez tekstu przechodzi przez OCR (do dobrego wyniku potrzebny jest język polski `tesseract-ocr-pol`; kontener go zawiera).
CLI bez interfejsu: `python -m embsim.cli add <folder | plik.jsonl | --text "...">`.

## Wyniki (uczciwie)

Pełna tabela z danymi, podziałem i ograniczeniami: [docs/WYNIKI.md](docs/WYNIKI.md). Skrót:

| co mierzymy | na czym | wynik |
|---|---|---|
| grupowanie kampanii, wzór domyślny kontra pierwsza wersja | 80 światów syntetycznych, protokół N-LNSO | ARI 0,749 [0,730; 0,767] wobec 0,635 [0,610; 0,658] |
| doklejanie nowych wzorców do znanych kampanii (im mniej, tym lepiej) | j.w. | 0,148 [0,131; 0,166] wobec 0,462 [0,433; 0,491] |
| przypisanie nowej reklamy do twórcy (tekst + leksyka + domena) | 4 481 najnowszych reklam z Mety, test po czasie, reklamy z treścią | top-1 0,63 [0,55; 0,70], AUROC „znany vs nowy” 0,77 [0,72; 0,82] |
| kanał obrazu | 117 zrzutów urlscan, 10 przypadków NASK | AUC 0,73–0,83; wariant 48≈61 nie łączy się |

**Ograniczenia, które znamy:** (1) etykiet prawdziwych kampanii nie ma, a liczby z syntetyki mierzą odzyskiwanie sygnału podłożonego przez
generator; (2) progi pochodzą z kalibracji na syntetyce, na prawdziwych danych niesprawdzone; (3) targetowanie reklam psuje wynik na Mecie
(domena pomaga) i jest wyłączone, a formułę śladów trzeba poprawić; próg z syntetyki v2 (0,95) nie przenosi się: na stronach demonstrator używa 0,725 (docs/WYNIKI.md §5a), na Mecie optimum ok. 0,5 (suwak w interfejsie); (4) brak rozpoznawania osób i logotypów na obrazie; (5) OCR bez języka
polskiego jest słaby; (6) przy dodawaniu po jednym legalne strony z pospolitymi zasobami trafiały do operatora oszustw; reguła rzadkiego śladu zmniejszyła to z 30 do 9 z 43 na syntetycznym zbiorze testowym, ale limit jest bezwzględny i nie sprawdzony na dużej galerii ani na prawdziwych danych (docs/WYNIKI.md, §7a).

## Struktura

- `code/src/embsim/`: metoda (cechy, wzór, galeria, interfejs `app.py`, ewaluacja `cv.py` i `stream_eval.py`)
- `code/graph/`: baza grafowa Neo4j (twórca jako węzeł, scraper `scrape.py`), opis w [docs/13_BAZA_GRAFOWA.md](docs/13_BAZA_GRAFOWA.md)
- `code/src/fejki/`: poprzedni silnik (tag `legacy-v1`), zachowany do porównań
- `docs/archiwum/`: dokumentacja historyczna poprzedniego silnika (nie opisuje obecnej metody)
- `docs/15_FORMAT_KANALU_RUCHU.md`: format kanału ruchu sieciowego dla grafu

## Licencje i dane zewnętrzne

Modele: `paraphrase-multilingual-MiniLM-L12-v2` (Apache-2.0), opcjonalnie `Qwen3-VL-Embedding-2B` (Apache-2.0). Neo4j Community (GPLv3,
osobny serwer). Dane Meta Ad Library: oficjalne API, warunki Mety. BuzzFeed-Webis (CC BY 4.0) użyto do eksperymentu pomocniczego.
Pochodzenie każdego zbioru: [docs/WYNIKI.md](docs/WYNIKI.md).
