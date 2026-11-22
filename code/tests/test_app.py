import os

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

from embsim.synth2 import generate


def test_app_single_path_end_to_end(tmp_path, monkeypatch):
    generate(tmp_path / "w", seed=4, n_operators=3, campaigns_per_op=2, variants=3, missing_rate=0.0)
    monkeypatch.setenv("EMBSIM_EMBED", "hash")
    monkeypatch.setenv("EMBSIM_GALLERY", str(tmp_path / "gal.jsonl"))
    monkeypatch.setenv("EMBSIM_DATA", str(tmp_path / "w"))
    root = os.path.dirname(os.path.dirname(__file__))
    at = AppTest.from_file(os.path.join(root, "src", "embsim", "app.py"), default_timeout=120).run()
    assert not at.exception
    assert any("Galeria" in h.value for h in at.sidebar.header)
    at.sidebar.button[0].click().run()                                   # „Dodaj przypadki z folderów”
    assert not at.exception and any("Przyjęto" in s.value for s in at.sidebar.success)
    assert int(at.sidebar.metric[0].value) > 10 and int(at.sidebar.metric[1].value) >= 2   # liczniki aktualne po odświeżeniu
    at.text_area[0].input("Szokujące: znany prezes zdradził sposób na zysk, wpłać 500 zł")   # bez run(): formularz
    [b for b in at.button if b.label == "Analizuj"][0].click().run()
    assert not at.exception
    sub = [s.value for s in at.subheader]
    assert "3. Dopasowanie z przesłankami" in sub and "4. Sieć kampanii i operatorów" in sub
    assert at.success or at.warning or at.info                           # werdykt pokazany


def test_clusters_tab_gallery_and_neo4j_degrades_gracefully(tmp_path, monkeypatch):
    generate(tmp_path / "w", seed=7, n_operators=3, campaigns_per_op=2, variants=3, missing_rate=0.0)
    monkeypatch.setenv("EMBSIM_EMBED", "hash")
    monkeypatch.setenv("EMBSIM_GALLERY", str(tmp_path / "gal.jsonl"))
    monkeypatch.setenv("EMBSIM_DATA", str(tmp_path / "w"))
    root = os.path.dirname(os.path.dirname(__file__))
    at = AppTest.from_file(os.path.join(root, "src", "embsim", "app.py"), default_timeout=120).run()
    assert any("pusta" in i.value for i in at.info)                      # pusta galeria: komunikat, bez wyjątku
    at.sidebar.button[0].click().run()
    assert not at.exception
    assert any(s.value == "Klastry w galerii" for s in at.subheader)
    assert at.selectbox and any("kampanii" in o for o in at.selectbox[-1].options)
    at.radio[0].set_value("Graf Neo4j (twórcy z Mety, sieci NASK)").run()    # bez bazy lub pakietu: komunikat, nie wyjątek
    assert not at.exception


def test_builtin_example_runs_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBSIM_EMBED", "hash")
    monkeypatch.setenv("EMBSIM_GALLERY", str(tmp_path / "gal.jsonl"))
    root = os.path.dirname(os.path.dirname(__file__))
    at = AppTest.from_file(os.path.join(root, "src", "embsim", "app.py"), default_timeout=180).run()
    assert not at.exception
    [b for b in at.button if b.key == "example_wariant"][0].click().run()
    assert not at.exception
    assert int(at.sidebar.metric[0].value) >= 10                          # galeria z przykładu zbudowana
    assert any("Oczekiwany wynik" in i.value for i in at.info)            # opis przykładu z oczekiwanym werdyktem
    assert "3. Dopasowanie z przesłankami" in [s.value for s in at.subheader]
