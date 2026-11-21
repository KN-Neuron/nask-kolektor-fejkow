# 14. Wzór podobieństwa (jedno wyrażenie, bez uczenia)

Podobieństwo dwóch materiałów `a` i `b` jest **jednym wyrażeniem z wagami ustalonymi z góry**. Nie ma tu wytrenowanego modelu ani uczenia
kontrastowego (mentor: to „strzelba na komara”). Jedyne liczby dobrane na danych z etykietami to **dwa progi decyzyjne**. Opis dotyczy
konfiguracji domyślnej `v3_mixed_pca` (`code/config/embsim/`), kod: `code/src/embsim/score.py`.

## 1. Kanały

| kanał | co porównuje | typ |
|---|---|---|
| `text` | embedding tekstu (domyślnie MiniLM, wielojęzyczny) | semantyczny |
| `text_lex` | TF-IDF n-gramów znaków (3–5) | leksykalny |
| `kit` | prefiksy katalogów zasobów strony (z HAR) | ślady |
| `scheme` | zestaw nazw parametrów adresu (z HAR) | ślady |
| `host` | domeny rejestrowalne z ruchu (z HAR) | ślady |
| `pixel` | identyfikatory pikseli i tagów (z HTML) | ślady |

Wszystkie wagi są równe: `w_c = 1` (nie uczone). Kanał bez danych u którejkolwiek strony nie liczy się do wyniku.

## 2. Wzór główny (poziom kampanii)

Niech `C` to wszystkie kanały, `D(a,b)` kanały, w których **oba** materiały mają dane, a `P(a,b) ⊆ D(a,b)` kanały policzone (kanały
semantyczne z danymi oraz kanały śladów, w których istnieje **wspólny ślad**):

```
S̄(a,b) = Σ_{c∈P} w_c · s_c(a,b)  /  Σ_{c∈P} w_c            (średnia ważona po kanałach policzonych)
e(a,b) = Σ_{c∈D} w_c  /  Σ_{c∈C} w_c                       (ile dowodu w ogóle dało się porównać)
λ      = min(1, e / e_ref)
S(a,b) = max(0,  1 − (1 − S̄) / λ )                         (im mniej danych, tym wyższy S̄ jest potrzebny)
```

Decyzja: `S ≥ t_kampanii` ⇒ ta sama kampania.

## 3. Składniki `s_c ∈ [0,1]`

**Kanały semantyczny i leksykalny** (z korektą względem typowego podobieństwa w korpusie):

```
s_text     = clip( (cos(ũ_a, ũ_b) − μ) / (1 − μ), 0, 1 ),   ũ = normalizacja( (u − m) − ((u − m)·p) p )
s_text_lex = clip( (cos(t_a, t_b) − μ_L) / (1 − μ_L), 0, 1 ), t = wektor TF-IDF znaków
```

`u` to embedding, `m` średnia wektorów korpusu, `p` pierwsza główna składowa korpusu (opcjonalna korekta anizotropii „all-but-the-top”),
`μ`, `μ_L` mediany kosinusów par w korpusie.

**Kanały śladów** (miara „nakładania”: tylko dowody dodatnie, bez kary za różnice, bo zrzuty tej samej kampanii nie są identyczne):

```
s_c = 1 − exp( − Σ_{x ∈ A_c ∩ B_c} idf_c(x) ),     idf_c(x) = ln( (N + 1) / (df_c(x) + 0.5) )
```

Ślad pospolity (`df` bliskie `N`, np. trackery Facebooka) ma `idf ≈ 0`, więc prawie nic nie waży; rzadki wspólny ślad waży dużo.

## 4. Poziom operatora (ta sama infrastruktura)

Tylko kanały śladów (`w_text = w_text_lex = 0`), miara „zawierania” bez rozcieńczania przez wielkość zbiorów, bez korekty λ:

```
s_c = ( I / min(W_a, W_b) ) · ( 1 − exp(−I) ),   I = Σ_{x∈A∩B} idf(x),   W_a = Σ_{x∈A} idf(x)
S_op = Σ w_c s_c / Σ w_c po kanałach z danymi    (dla `host` i `pixel` brak wspólnego śladu = kanał milczy)
```

Decyzja: `S_op ≥ t_operatora` ⇒ ten sam operator.

## 5. Skąd biorą się liczby

| wielkość | wartość | skąd |
|---|---|---|
| wagi `w_c` | 1 | z góry, nie uczone |
| `μ`, `μ_L`, `m`, `p`, `idf`, `N` | z korpusu | statystyki tekstów i śladów, **bez etykiet** |
| `e_ref` | 0,67 | mediana dostępności dowodu na zbiorach dev (bez etykiet w definicji) |
| `t_kampanii`, `t_operatora` | 0,95 i 0,25 | **jedyne liczby dobierane z etykietami**, na dev (plateau ARI) |

Decyzja trójstanowa dla nowego materiału: `S ≥ t_kampanii` → znana kampania; w przeciwnym razie `S_op ≥ t_operatora` → znany operator,
nowa kampania; w przeciwnym razie nowy wzorzec.

## 6. Co jest uzasadnione danymi (ewaluacja N-LNSO, 80 światów syntetycznych)

Każdy świat jest testowy dokładnie raz; progi i wybór dostrajane w światach treningowych; 95% przedziały bootstrapem po światach;
Wilcoxon z korektą Holma. Różnice względem konfiguracji domyślnej (dodatnie = domyślna lepsza), ARI kampanii:

| zmiana względem domyślnej | Δ ARI kampanii [95% CI] | p (Holm) |
|---|---|---|
| wersja v1 (Jaccard, średnia, bez leksyki) | +0,114 [+0,097, +0,131] | < 0,0001 |
| wersja v1 z leksyką i korektą | +0,052 [+0,038, +0,065] | < 0,0001 |
| zawieranie zamiast nakładania w kampanii | +0,018 [+0,006, +0,030] | 0,018 |
| **bez kanału leksykalnego** | **+0,027 [+0,021, +0,035]** | < 0,0001 |
| bez korekty PCA | +0,003 [+0,000, +0,006] | 0,14 (nieistotne) |

Błędne łączenie nowych wzorców: 0,148 domyślnie wobec 0,326 (v1 z leksyką) i 0,462 (v1).

**Uwagi uczciwości:**
- Korekta PCA nie jest poparta przez syntetykę (wybór zagnieżdżony pominął ją w 15 z 15 foldów); jej uzasadnieniem są wyniki na prawdziwych
  tekstach z Mety (zob. ewaluacja strumieniowa).
- Poziom operatora: miara „zawierania” jest nieznacznie gorsza od Jaccarda z v1 (Δ ARI operatora −0,019 [−0,030, −0,008], p = 0,0006).
  Do rozważenia przy następnej iteracji, z nowym zagnieżdżonym wyborem.
- Syntetyka jest pisana przez nas pod te cechy. Dowody na prawdziwych danych: `code/src/embsim/stream_eval.py`.

## 7. Czego świadomie nie robimy

Nie trenujemy modelu ani nie stosujemy uczenia kontrastowego. Opcjonalna głowa kontrastowa (`embsim/metric.py`) jest pozostawiona jako
dodatek na koniec prezentacji („można potrenować”), ale nie wchodzi do wyniku.
