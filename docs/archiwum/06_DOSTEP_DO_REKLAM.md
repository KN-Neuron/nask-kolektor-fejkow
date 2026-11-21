# 06. Dostęp do bibliotek reklam

Brief: „Musimy posiąść wiedzę, jak dostać się do bibliotek takich reklam”. W formalnym opisie automatyczne wyszukiwanie
w bibliotekach to funkcja **dodatkowo punktowana**, nie wymóg. Szczegóły z pierwszego dnia: [research/dostep-do-reklam.md](../research/dostep-do-reklam.md).

| Źródło | Dostęp | Stan u nas | Co daje |
|---|---|---|---|
| **Meta Ad Library API** (`graph.facebook.com/<wersja>/ads_archive`) | 1) potwierdzenie tożsamości na facebook.com/ID, 2) akceptacja warunków na facebook.com/ads/library/api, 3) aplikacja na developers.facebook.com, 4) token użytkownika (np. Graph API Explorer) | tożsamość **potwierdzona (Polska)**; warunki i token do zrobienia; wcześniej błąd 10 / 2332002 | wyszukiwanie po słowach, kraju (`ad_reached_countries=PL`), dacie; dla reklam komercyjnych w UE ograniczony zestaw pól (tekst, link, daty, `eu_total_reach`), bez wydatków |
| Meta Ad Library (strona) | bez logowania | ręcznie | podgląd; eksport CSV tylko reklam społecznych/politycznych; scraping wbrew regulaminowi (nie robimy) |
| TikTok Commercial Content API | wniosek „researchers”, ok. 2 dni robocze | nie złożono | dane z UE; niepewne, czy zwraca tekst reklamy |
| Google Ads Transparency Center (BigQuery public dataset) | projekt GCP | adapter `ingest/bigquery_google.py`, nietestowany | reklamodawca, daty, regiony, URL podglądu; raczej bez tekstu |
| Snapchat Ads Gallery API | otwarte | sprawdzone, mało przydatne | wymaga nazwy reklamodawcy (brak wyszukiwania po słowie) |
| Lista Ostrzeżeń CERT Polska (hole.cert.pl) | otwarte | adapter `ingest/cert.py` | domeny oszustw: etykiety i sprawdzanie wyprzedzenia |

## Stan dostępu (2026-11-21, po uzyskaniu tokenu)

- **Token działa**, `ads_archive` zwraca wyniki dla `ad_reached_countries=["PL"]`, `ad_type=ALL` (komercyjne też).
- **Nie da się pobrać reklamy po identyfikatorze** (ani id z Ad Library, np. 1982065065827084, ani `ad_id` z adresu,
  np. 120250558396250564): `GET /{id}` zwraca „Unsupported get request”. API tylko wyszukuje (`search_terms`,
  `search_page_ids`, kraje, daty).
- Wyszukiwanie po treściach z naszych przypadków (Metabo, Uromexil, Bonanza, Brzoska, Olejnik, „kajdankach”…) **nie
  zwróciło naszych reklam ani reklamodawców**: reklamy-oszustwa żyją krótko, a usunięte przez Metę mają w API treść
  „This content was removed because it didn't follow our Advertising Standards”. Dla „Uromexil” 4 z 23, dla „Poland Invest
  Summit” 11 z 48 trafień to reklamy usunięte; strony-reklamodawcy mają przypadkowe nazwy (np. „Tihomir Maclean”).
- Wniosek: Meta przyda się do **wyszukiwania nowych podejrzanych reklam** (słowa kluczowe, usunięte reklamy jako sygnał,
  `page_id` reklamodawców) i do dat emisji, a nie do odtwarzania reklam z przypadków organizatora.

## Jak to wpiąć w demonstrator (zadania D2, D3)

- Materiały ze zbioru mają **identyfikatory reklam Meta** (przypadki 5, 14, 36, 47: `ad_id` w adresie, link Ad Library,
  identyfikator biblioteki z OCR). Z tokenem: pobrać kartę reklamy (tekst, reklamodawca `page_id/page_name`, daty, kraje),
  dołożyć jako cechy (wspólny `page_id` = bardzo silny dowód).
- Scheduler (bonus): okresowe zapytanie `ads_archive` po słowach kluczowych z wykrytych kampanii (np. nazwy produktów,
  „zamach”, „Brzoska”, „inwestycja”), nowe reklamy → `material_from_inputs` → dopasowanie do kampanii → lista „nowe
  materiały powiązane z kampanią K…”.

## Token: zasady

- token tylko w `code/.env` (`META_ACCESS_TOKEN=`), nigdy na czacie, w kodzie ani w repo;
- tokeny wklejone wcześniej na czacie uznajemy za ujawnione (wygasły);
- dla organizatora opisujemy kroki uzyskania dostępu (powyżej), nie przekazujemy klucza (opis wyzwania, pkt 4).
