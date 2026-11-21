# code/

Metoda i interfejs: `src/embsim/`. Poprzedni silnik (tag `legacy-v1`): `src/fejki/`, zachowany do porównań.

```bash
make install   # z katalogu głównego repozytorium
make test      # testy metody i interfejsu, bez danych
make demo      # interfejs
make eval      # ewaluacja (log na żywo: code/artifacts/stream/live.log)
```

Układ: `src/embsim/{features,score,api,analyze,app}.py` (metoda i interfejs), `{cv,stream_eval,bench,metrics,ext}.py` (ewaluacja),
`synth2.py` (generator syntetyki), `graph/` (Neo4j), `config/embsim/` (zamrożone konfiguracje z progami), `tests/`.
Stare testy (`tests/test_pipeline.py` itd.) potrzebują dodatku `research`: `make test-legacy`.
Opis metody: `../docs/METODYKA.md`, wzór: `../docs/14_WZOR_PODOBIENSTWA.md`, wyniki: `../docs/WYNIKI.md`.
