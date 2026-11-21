# Dostęp do bibliotek reklam: ustalenia (2026-11-21)

| Źródło | Stan | Uwagi |
|---|---|---|
| Meta Ad Library API (`/ads_archive`) | zablokowane | Błąd 10 / subcode 2332002 ("Wymagana autoryzacja i logowanie"). Potrzebne: potwierdzenie tożsamości (facebook.com/ID, do kilku dni) i warunki "Authorized Access to Public Information" na facebook.com/ads/library/api. Token użytkownika z aplikacji; `ads_read`. Tokeny z czatu wygasły. |
| Meta Ad Library UI | brak eksportu dla reklam komercyjnych | Raport do pobrania tylko dla reklam społecznych/wyborczych/politycznych. Zasięgi (`spend`, `impressions`) tylko dla politycznych; `eu_total_reach` dla reklam dostarczonych w UE. |
| TikTok Commercial Content API | do złożenia wniosku | Wg oficjalnej strony: "public and researchers", odpowiedź ok. 2 dni robocze, dane z UE. Nieznane: czy zwraca tekst reklamy. |
| Snapchat Ads Gallery API | nie nadaje się do odkrywania | Otwarte, bez tokena (`POST adsapi.snapchat.com/v1/ads_library/ads/search`), ale wymaga `paying_advertiser_name`; brak wyszukiwania po słowie. |
| Google Ads Transparency (BigQuery) | adapter gotowy, nietestowany | Wymaga projektu GCP. Tabela raczej bez tekstu reklam (reklamodawca, URL podglądu, daty). |
| LinkedIn, X | tylko UI, bez API | Nie sprawdzane na żywo. |

Źródła etykiet i kontekstu: lista CERT Polska (hole.cert.pl), DSA Transparency Database, zgłoszenia UOKiK / Demagog / Fake Hunter,
PhishTank / OpenPhish / URLhaus.

## Scraping UI Ad Library
Odradzany: wbrew regulaminowi Meta, ryzyko dla konta potrzebnego do API, kruche. Wyszukiwanie po `"a"` sortowane po
wyświetleniach pokazuje największe (legalne) reklamy, nie oszustwa. Do rozstrzygnięcia przez organizatorów.

## Plan B
Mały zbiór ręczny prawdziwych reklam (kilkadziesiąt do ~150) z UI, przepisany do JSONL, plus adaptery z kodu.
Do prezentacji: metoda zweryfikowana na syntetyce plus próbka realna, z opisem dróg dostępu.
