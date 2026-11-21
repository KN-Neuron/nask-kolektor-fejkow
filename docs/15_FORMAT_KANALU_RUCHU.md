# 15. Kanał ruchu sieciowego: format (dla grafu, zadanie „węzły z ruchu sieciowego”)

Ten dokument mówi, **co dokładnie wyciąga kanał ruchu w `embsim`** i w jakim formacie, żeby graf zapisywał to samo, co widzi wynik
podobieństwa. Kod: `code/src/embsim/features.py` (`load_case`), format wymiany: `code/src/embsim/api.py` (`case_to_dict`,
`case_from_dict`).

## 1. Wejście

- pliki `.har` w folderze przypadku (HAR 1.2): używamy wyłącznie `log.entries[].request.url`; kilka plików HAR w przypadku = suma;
- plik `.html` zapisany przeglądarką: z komentarza `<!-- saved from url=(NNNN)URL -->` bierzemy **adres strony docelowej**, a z treści
  identyfikatory pikseli i tagów.

## 2. Wyjście kanału: cztery zbiory napisów na materiał

Wszystkie to **zbiory** (kolejność i powtórzenia nie mają znaczenia). Pusty zbiór = **brak danych**, nie „brak podobieństwa”.

| zbiór | definicja (dla każdego URL z HAR i adresu strony) | przykład |
|---|---|---|
| `host` | domena rejestrowalna przybliżona: **dwa ostatnie człony** nazwy hosta, bez listy sufiksów (znana wada: `x.co.uk` → `co.uk`) | `facebook.net`, `jsdelivr.net` |
| `kit` | katalog zasobu: `"/" +` pierwsze dwa segmenty ścieżki **bez ostatniego segmentu (nazwy pliku)**; tylko gdy ścieżka ma ≥ 2 segmenty | `https://x.com/a/b/c/app.js` → `/a/b` |
| `scheme` | **posortowane, unikalne nazwy** parametrów zapytania połączone przecinkami (wartości odrzucane); tylko gdy są parametry | `utm_id,utm_medium,utm_visit` |
| `pixel` | z HTML: `fbq('init','ID')`, `GTM-…`, `AW-…`, `UA-…-…`, `G-…` | `1330594163214458` |

Nic więcej nie wchodzi dziś do wyniku (np. kolejność przekierowań, kody odpowiedzi, czasy).

## 3. Format wymiany (JSON)

Jeden materiał = jeden obiekt (np. wiersz JSONL). To jest dokładnie wyjście `case_to_dict` (przykład z syntetyki; zbiory skrócone do
4 elementów, w prawdziwym przypadku mają 5–15):

```json
{
  "id": "s001",
  "text": "Szokujące: Dominika Kulczyk i Metabo RX …",
  "sets": {
    "pixel":  ["1330594163214458"],
    "kit":    ["/css/fonts", "/en_US", "/gtag/js", "/npm/jquery@3.6.0"],
    "scheme": ["ex,placement,pmd,utm_content,utm_medium,utm_term", "utm_term"],
    "host":   ["2zhrwy.site", "3jk0f1.xyz", "dqrretnos.test", "eecmj7r.net"]
  },
  "meta": {}
}
```

Wczytanie w Pythonie: `from embsim.api import case_from_dict`. Dodanie do galerii: `Gallery().add(case)`.

## 4. Mapowanie na graf

Schemat grafu ma już odpowiedniki; trzeba zadbać, żeby **klucze były liczone tak samo** jak w `embsim`:

| zbiór `embsim` | węzeł w grafie | krawędź |
|---|---|---|
| `host` | `Domain {name}` | `LANDS_ON` / `CALLS` |
| `kit` | `PageKit {prefix}` | `USES_KIT` |
| `scheme` | `UrlScheme {fingerprint}` | `USES_URL_SCHEME` |
| `pixel` | `Tracker {id}` | `USES_TRACKER` |

**Do uzgodnienia:** loader grafu bierze te cechy z extraktora starego silnika (`fejki.demo.material`), a `embsim` ma własne, krótsze
definicje powyżej. Należy sprawdzić na kilku przypadkach, czy dają te same wartości (zwłaszcza `kit` i `scheme`); jeśli nie, graf powinien
przyjąć definicje `embsim` albo używać eksportu z punktu 3.

## 5. Czego brakuje (wersja 2 kanału) i o co prosimy stronę grafu

Do cech TDS (długość łańcucha przekierowań, liczba różnych URL, łączność) potrzebne są dane, których dziś nie ma w kanale. Prosimy o
eksport z grafu (albo z HAR) w postaci:

```json
{"id": "...", "landing": ["domena"], "calls": ["domena", "..."],
 "redirects": [{"hop": 1, "src": "domena", "dst": "domena", "status": 302}],
 "n_requests": 37}
```

czyli **kolejność kroków** (`hop`), **kod odpowiedzi** i liczba żądań. Z HAR: `response.status`, `response.redirectURL`, kolejność wpisów
(`startedDateTime`). Po otrzymaniu dodajemy z tego kanał z wagą ustaloną z góry i oceniamy w harnessie (zadanie po stronie modeli).

## 6. Uwagi

- Trackery i CDN (np. `facebook.net`, `/signals/config`) występują w prawie każdym przypadku. **Nie filtrujcie ich w grafie**: wynik
  podobieństwa obniża ich wagę sam (`idf ≈ 0`), a w grafie warto je oznaczyć jako huby (duży stopień).
- Domeny lądowania są jednorazowe i rotowane, więc brak wspólnego `host` nie jest dowodem różnicy (kanał wtedy milczy).

## 7. Stan po stronie grafu

- Graf liczy `host`, `kit`, `scheme` i `pixel` funkcją `embsim.features.load_case`; na 52 przypadkach (NASK + syntetyka)
  zbiory `kit` i `scheme` są identyczne z `embsim`, a każdy piksel z `embsim` jest w grafie (graf ma też kilka z HAR).
- Eksport z pkt 5 jest gotowy: `python graph/load.py traffic` → `code/artifacts/traffic/traffic.jsonl`
  (`landing`, `calls`, `redirects` z `hop` i `status`, `n_requests`, `sets`, `hubs`). Przekierowań w HAR NASK jest mało (2 przypadki).
- Huby są oznaczone (`hub = true`); szczegóły i reguła: [13_BAZA_GRAFOWA.md](13_BAZA_GRAFOWA.md), sekcja „Ruch sieciowy”.
