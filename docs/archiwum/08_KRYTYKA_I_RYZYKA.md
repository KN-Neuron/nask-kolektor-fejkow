# 08. Krytyka podejścia i ryzyka (przygotowanie do oceny)

Spisane z perspektywy krytyka: gdzie nasze podejście może się wyłożyć, co mówią o tym istniejące badania i rozwiązania,
co robimy, żeby się zabezpieczyć. Stan: 2026-11-21.

## Najpoważniejsze dziury

| # | Zarzut | Dlaczego to realne | Zabezpieczenie (zrobione / do zrobienia) |
|---|---|---|---|
| 1 | **„Kampania” to nasza definicja, nie organizatora.** | Sieć S1 wyznaczają nasze reguły infrastruktury; organizator może liczyć kampanię po narracji albo produkcie. Na ukrytym teście możemy łączyć za dużo (operator) albo za mało (narracja). | ✅ dwa poziomy: kampania (ten sam przekaz) i sieć (operator); ⬜ zapytać mentora o definicję; raportować oba poziomy |
| 2 | **Złoty zbiór ma 10 przypadków, a reguły i wagi ustawialiśmy, patrząc na dane.** | Klasyczne przeuczenie; reguły infrastruktury dostroiliśmy po pierwszym przebiegu (zapisane w DOKUMENT_ZBIORCZY). | ✅ zbiór organizatora tylko do testu; ✅ podział subject-based; ⬜ zamrozić reguły i walidować na urlscan/Meta |
| 3 | **Zestaw stron ≠ operator.** | Badania nad phishingiem grupują strony po zestawach (kitach), np. po użyciu API przeglądarki (97% zgodności z rodzinami kitów), ale kit bywa sprzedawany wielu aktorom. Nomani to dziesiątki tysięcy URL-i z jednego ekosystemu. Nasz ślad `/aio-static/sdk` ma 318 skanów w wielu krajach. | ✅ krawędź wymaga zwykle kilku niezależnych śladów; ⬜ etykieta „zestaw” osobno od „operator”; ⬜ test: czy S1 nie wchłania obcych z urlscan |
| 4 | **Ukryty test może nie mieć HAR i HTML.** | Same zrzuty dziś nic nie łączą (0/4 w teście niepełnego wejścia). | ⬜ CLIP/SigLIP na zrzutach (B2), polski OCR (B1), dopasowanie do tekstu reklam z Meta |
| 5 | **Kampanie żyją godzinami, strony są cloakowane.** | Nomani: kampanie trwają kilka godzin, żeby uniknąć wykrycia. Przy wejściu URL widzimy tylko kształt adresu i infrastrukturę (nie wchodzimy na strony). | ✅ wykrywanie cloakingu w nagranych plikach; ✅ wiek domeny; ⬜ wyszukanie URL w urlscan (bierne) przy analizie nowego materiału |
| 6 | **Dane z Meta są stronnicze.** | Badanie austriackie (ÖIAT dla KommAustria) pokazało, że wyszukiwanie po słowach kluczowych gubi reklamy z wizerunkiem celebrytów, które widać dopiero po koncie; reklamy usunięte tracą treść; dla reklam komercyjnych w UE pola są ograniczone. Nasze 15 tys.+ reklam to głównie reklamy legalne. | ✅ druga runda po stronach-reklamodawcach; ✅ flaga „usunięta przez Metę”; ⬜ etykieta przez domeny linków zgodne z Listą CERT (tak jak Gen Digital: reklama = scam, gdy prowadzi do infrastruktury oszustwa) |
| 7 | **Hipoteza LEACE nie przeszła.** | Na bge-m3 LEACE zbliża wszystkie oszustwa do siebie i zmniejsza odstęp między sieciami (0,214 → 0,158). | ✅ uczciwie opisane jako wynik negatywny; ⬜ nowa hipoteza H2 (oszustwo vs legalne ponad tematami) na negatywach z Meta |
| 8 | **Osoby tylko po nazwisku, bez twarzy.** | Opis wyzwania wymienia wizerunki osób; Nomani używa deepfake'ów wideo. | ⬜ transkrypcja audio nagrań (nazwiska w mowie); ⬜ opcjonalnie mała baza twarzy (B5, decyzja zespołu, licencje modeli) |
| 9 | **Słowniki tematów i ruchów perswazji są ręczne i polskie.** | Stronniczość, słaba przenośność (urlscan ma kopie niemieckie). | ⬜ klasyfikacja zero-shot na bge-m3 (prototypy opisów), porównanie ze słownikiem |
| 10 | **Noisy-OR zakłada niezależność kanałów.** | Tytuł, tekst, szablon DOM i obrazy pochodzą z tej samej strony, więc liczymy ten sam dowód kilka razy. | ⬜ model par uczony na danych (A6) z cechami skorelowanymi; limit wkładu jednego źródła |
| 11 | **Składowe spójne łańcuchują.** | A~B i B~C sklei A z C nawet bez śladu; przy tysiącach materiałów powstanie „wielka sieć”. | ⬜ wymagać wsparcia krawędzi (np. ≥ 2 sąsiadów) albo Leiden z części badawczej; mierzyć rozmiar największej grupy na urlscan |
| 12 | **Mało negatywów.** | Na urlscan mamy 2 negatywy; test „nie doklejaj” jest słaby. | ⬜ legalne reklamy z Meta i prawdziwe portale jako negatywy |
| 13 | **Skala i wydajność.** | O(n²) par; bge-m3 to 2,2 GB w obrazie Dockera. | ⬜ blokowanie kandydatów (C4); decyzja: model w obrazie czy pobierany przy starcie |
| 14 | **Prawo i warunki usług.** | Dane organizatora (zakaz rozpowszechniania), warunki Meta i urlscan, dane osobowe (nazwy płatników, bylines w reklamach). | ✅ wszystko lokalnie i w `.gitignore`; ✅ tylko oficjalne API; ⬜ przegląd warunków Meta i urlscan przed oddaniem; minimalizacja pól |

## Czego nauczyliśmy się od innych (i co z tego bierzemy)

- **ESET, Nomani**: deepfake'i, fałszywe newsy, kampanie trwające godziny, dziesiątki tysięcy URL-i, przypisanie po
  artefaktach w kodzie (komentarze, narzędzia). → Ślady w kodzie stron (komentarze, nazwy skryptów, hashe) to dobry kanał (C1).
- **Badania nad klastrowaniem phishingu** (zachowanie JavaScriptu, odciski kitów, nietypowe nazwy plików, ukryte pola
  formularzy). → Mamy nagrane HAR i HTML: można liczyć hashe skryptów i nazw plików bez odwiedzania stron.
- **Gen Digital / Norton, „Scam Ad Machine”**: 4,5 mln reklam z Meta Ad Transparency API, etykieta „scam”, gdy reklama
  prowadzi do infrastruktury oszustwa. → Ta sama logika etykiet co u nas (infrastruktura etykietuje, treść się uczy).
- **ÖIAT / KommAustria**: słowa kluczowe gubią reklamy celebrytów, potrzebne wyszukiwanie po kontach. → Druga runda po stronach.
- **Which?**: ręczna analiza ponad 6 tys. reklam z Ad Library. → Mała ręczna próbka do audytu naszych etykiet.
- **CSIRT KNF**: 45 985 domen fałszywych inwestycji w 2024 (89,4% głównych kategorii), trafiają na Listę Ostrzeżeń
  CERT/NASK. → Lista CERT jako źródło etykiet i do testu wyprzedzenia (H3).

## Pytania, które może zadać jury (i odpowiedzi)

1. **„Skąd wiecie, że to jedna kampania?”** Pokazujemy przesłanki krawędzi (piksel, domena, rejestracja w odstępie 1 min,
   schemat adresów) i rozróżnienie kampania/sieć. Mówimy, że definicja jest operacyjna i że raportujemy oba poziomy.
2. **„Czy nie przeuczyliście na 10 przypadkach?”** Zbiór organizatora tylko do testu, kalibracja na urlscan i Meta
   z podziałem subject-based i audytem przecieków.
3. **„Co, jeśli dostaniecie tylko zrzut?”** Uczciwie: to najsłabsza modalność; plan: CLIP, polski OCR, dopasowanie
   do reklam z Meta.
4. **„Czemu nie odwiedzacie stron?”** Bezpieczeństwo i etyka; nagrane pliki organizatora wystarczają, a do nowych URL-i
   bierne źródła (DNS, RDAP, crt.sh, urlscan).
5. **„LEACE nie zadziałał, po co o nim mówicie?”** Bo to rzetelny wynik: temat da się usunąć, ale zostaje wspólny „język
   oszustwa”, nie podpis operatora. To wiedza dla NASK (pkt 10 opisu).

## Źródła

- [ESET / The Hacker News: Nomani investment scam surges 62%](https://thehackernews.com/2025/12/nomani-investment-scam-surges-62-using.html)
- [ESET WeLiveSecurity: AI-powered financial scams swamp social media](https://www.welivesecurity.com/en/scams/investors-beware-ai-powered-financial-scams-swamp-social-media/)
- [Characterizing Phishing Pages by JavaScript Capabilities (arXiv 2509.13186)](https://arxiv.org/html/2509.13186v1)
- [EURECOM: fingerprinting in phishing pages](https://www.eurecom.fr/publication/7537/download/sec-publi-7537.pdf)
- [An Analysis of Architectural and Operational Dynamics of Phishkits (arXiv 2608.07451)](https://arxiv.org/pdf/2608.07451)
- [RTR / KommAustria: Betrugsökosystem Werbung](https://www.rtr.at/medien/aktuelles/publikationen/Publikationen/Publikationen_2026/Betrugsoekosystem_Werbung_KommAustria_final_EN.pdf)
- [Gen Digital: The Scam Ad Machine (Meta)](https://www.gendigital.com/blog/insights/research/scam-ad-machine-meta)
- [Which?: Facebook and Instagram failing to protect users from dodgy investment ads](https://www.which.co.uk/news/article/facebook-and-instagram-are-failing-to-protect-users-from-dodgy-investment-ads-which-research-finds-a4WL25H4bOAS)
- [CSIRT KNF: Raport roczny 2024](https://www.knf.gov.pl/knf/pl/komponenty/img/Raport_Roczny_CSIRT_KNF_2024_93226.pdf)

Uwaga: części liczb nie weryfikowaliśmy w oryginałach (np. raport ESET z 2025 r. znamy z omówień); przed pitchem sprawdzić
cytowane liczby w źródłach pierwotnych.
