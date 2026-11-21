# data/: dane zbierane ręcznie

| Plik | Do czego |
|---|---|
| `reklamy_reczne.jsonl` | **Plik roboczy** (na start pusty). Jedna reklama = jedna linia JSON. |
| `reklamy_reczne.template.jsonl` | Wzór z dwoma przykładami. Nie wczytuj go do bazy. |
| `zrzuty/` | Zrzuty ekranu reklam; nazwę pliku wpisz w `meta.zrzut`. |

## Pola (zgodne ze schematem `Ad` w kodzie)
Wymagane w praktyce: **`body`** (tekst reklamy). Reszta opcjonalna.

- `ad_id`: unikalny, np. `reczne:001`. Jeśli pominiesz, kod nada `file:<nazwa-pliku>-<nr linii>`.
- `source`: zostaw `"file"`.
- `page_name`, `page_id`: reklamodawca / strona.
- `body`, `title`, `description`: tekst reklamy, nagłówek, opis.
- `link_caption`: domena z przycisku reklamy (ważne dla kanału domen).
- `lang`: `"pl"`.
- `delivery_start`, `delivery_stop`: daty ISO (`2026-11-10T00:00:00Z`) lub `null`.
- `truth_campaign`: etykieta kampanii, jeśli *Ty* uznajesz, że reklamy należą do jednej kampanii (np. `"kampania-A"`). Służy do oceny, więc nie wpisuj, jeśli nie jesteś pewien.
- `meta`: dowolne dodatkowe dane (`platforma`, `url_reklamy`, `url_docelowy`, `zrzut`, `uwagi`).

Plik JSONL nie ma komentarzy ani przecinków między liniami; każda linia to osobny, kompletny obiekt.

## Wczytanie do bazy
Z katalogu `code/`:

    .venv/bin/fejki ingest jsonl ../data/reklamy_reczne.jsonl

Błędne pole lub data zgłosi walidator (pydantic) z numerem problemu.
