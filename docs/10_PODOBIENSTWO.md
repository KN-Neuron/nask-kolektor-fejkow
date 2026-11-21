# 10. Jak oceniamy podobieństwo (kluczowe dla jury)

## Krok po kroku

1. **Cechy materiału** (`demo/material.py`): tekst, osoby, produkt, reklamodawca, domeny, przekierowania, schemat adresów,
   identyfikatory reklam i pikseli, obrazy (pHash), szablon strony, opcjonalnie infrastruktura domen.
2. **Dowody dla pary** (`demo/similar.py:evidence`): każdy kanał zwraca dowody `(kanał, waga 0–1, opis)`.

| Dowód | Waga | Dlaczego taka |
|---|---|---|
| ten sam identyfikator reklamy Meta | 0,95 | praktycznie jednoznaczny |
| ten sam piksel Meta / ta sama domena docelowa | 0,9 | jedno konto reklamowe / jedna strona |
| niemal identyczny tekst (TF-IDF ≥ 0,9) | 0,9 | duplikat treści |
| ten sam wzorzec ścieżki | 0,7 | ten sam zestaw strony |
| ten sam produkt / reklamodawca | 0,7–0,75 | ten sam przekaz |
| te same obrazy (pHash) | 0,6–0,7 | wspólne materiały |
| schemat parametrów adresu (TDS) | 0,6 | ten sam system kierowania ruchu |
| szablon strony (klasy HTML) | do 0,6 | wspólny szablon |
| osoba publiczna | 0,3 (limit 0,5) | ta sama twarz bywa w wielu kampaniach |
| tematyka | 0,1 | prawie nic nie znaczy |

   Cechy pospolite tracą wagę (×2/liczba materiałów z cechą).
3. **Łączenie**: noisy-OR w kanale, potem między kanałami: `wynik = 1 − Π(1 − p_kanał)`. Jeden słaby ślad nie wystarczy,
   kilka niezależnych się sumuje.
4. **Relacja**: duplikat / wariant tego samego przekazu / wspólna infrastruktura (operator) / podobieństwo treści.
5. **Progi**: ≥ 0,7 powiązanie, 0,4–0,7 „do weryfikacji”, niżej brak. Kampania = składowe spójne duplikatów i wariantów;
   sieć = wszystkie krawędzie ≥ progu.
6. **Przesłanki**: każda krawędź ma listę dowodów w języku analityka (interpretowalność, 15% oceny).

## Jak mierzymy, czy to działa

B-cubed (kampania i sieć), liczba doklejonych negatywów, trafność przypisania nowego materiału, pomiń-jeden, niepełne
wejście, audyt przecieków (szczegóły: README, docs/07).

## Słabości i plan

- wagi ręczne → **model par** (regresja logistyczna) uczony na urlscan i Mecie z podziałem subject-based; próg pod zero
  doklejonych negatywów; wkład kanału nadal widoczny jako przesłanka;
- noisy-OR zakłada niezależność kanałów (tytuł, tekst, szablon są skorelowane) → model par to uwzględni;
- składowe spójne mogą łańcuchować → wymóg wsparcia krawędzi albo Leiden.
