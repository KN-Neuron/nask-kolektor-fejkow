PY ?= code/.venv/bin/python
DATA ?= $(PWD)/data/dane/do_udostępnienia
UNIT = tests/test_api.py tests/test_analyze.py tests/test_app.py tests/test_score_lex.py tests/test_embsim.py tests/test_embsim_metrics.py \
       tests/test_ext.py tests/test_subjects.py tests/test_synth2.py tests/test_cv.py tests/test_stream_eval.py \
       tests/test_exact_img.py tests/test_infra_embsim.py

.PHONY: install test test-legacy demo smoke eval watch docker-build docker-run

install:            ## venv i zależności (ok. 2 min)
	cd code && python3 -m venv .venv && .venv/bin/pip install -q -e ".[dev]"

test:               ## testy metody i interfejsu (bez danych)
	cd code && PYTHONPATH=src ../$(PY) -m pytest -q $(UNIT)

test-legacy:        ## testy poprzedniego silnika (wymagają dodatku research)
	cd code && .venv/bin/pip install -q -e ".[research]" && PYTHONPATH=src ../$(PY) -m pytest -q tests --ignore-glob='tests/test_embsim*' $(addprefix --ignore=,$(UNIT))

demo:               ## interfejs na http://localhost:8501
	cd code && PYTHONPATH=src ../$(PY) -m streamlit run src/embsim/app.py

smoke:              ## dymny test CLI: dwa podobne teksty, drugi powinien dostać znaną kampanię
	cd code && rm -f /tmp/embsim_smoke.jsonl && \
	PYTHONPATH=src ../$(PY) -m embsim.cli add "Szokujące: prezes zdradził sposób na zysk. Wpłać 500 zł i obserwuj." --text --id a --gallery /tmp/embsim_smoke.jsonl 2>/dev/null && \
	PYTHONPATH=src ../$(PY) -m embsim.cli add "Szokujące: prezes zdradził sposób na zysk. Wpłać 700 zł i obserwuj." --text --id b --gallery /tmp/embsim_smoke.jsonl 2>/dev/null

watch:              ## planista: INBOX=folder (podfoldery przypadków, JSONL reklam), URLS=plik z adresami, EVERY=minuty (0 = raz)
	cd code && PYTHONPATH=src ../$(PY) -m embsim.watch $(if $(INBOX),--inbox "$(INBOX)") $(if $(URLS),--urls "$(URLS)") \
	  $(if $(KEYWORDS),--meta-keywords "$(KEYWORDS)") --every-min $(or $(EVERY),0)

eval:               ## pełna ewaluacja: N-LNSO na światach syntetycznych i strumień po czasie na Mecie (log: code/artifacts/stream/live.log)
	cd code && PYTHONUNBUFFERED=1 PYTHONPATH=src ../$(PY) -u -m embsim.cv --worlds 80 && PYTHONUNBUFFERED=1 PYTHONPATH=src ../$(PY) -u -m embsim.stream_eval

docker-build:
	docker build -t kolekcjoner-fejkow code

docker-run:         ## DATA=/ścieżka/do/folderu/z/przypadkami (opcjonalnie)
	docker run --rm -p 8501:8501 -v "$(DATA):/data:ro" kolekcjoner-fejkow
