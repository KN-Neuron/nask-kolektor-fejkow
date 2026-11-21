"""Schemat perswazji i LEACE na atrapie enkodera (bez pobierania modelu)."""
from __future__ import annotations

import numpy as np

from fejki.demo import template
from fejki.demo.material import Material
from fejki.demo.persuasion import dna, moves, shared_moves


def test_moves_detect_polish_without_diacritics():
    m = moves("SZOKUJĄCE nagranie usunięto! Zostało tylko 3 miejsca. Wpłać zaledwie 1000 zł i zarabiaj dziennie.")
    assert m["szokujacy_news"] > 0 and m["presja_czasu"] > 0 and m["niska_bariera"] > 0 and m["obietnica_zysku"] > 0
    ocr = moves("szokujace nagranie usunieto zostalo tylko 3 miejsca")  # OCR bez polskich znaków
    assert ocr["szokujacy_news"] > 0 and ocr["presja_czasu"] > 0
    assert abs(dna("zysk zysk sekret").sum() - 1) < 1e-9
    assert "obietnica zysku" in shared_moves({"obietnica_zysku": 5}, {"obietnica_zysku": 3})


def _mat(mid, text):
    return Material(id=mid, label=mid, source="tekst", text=text, titles=[])


def test_leace_removes_topic_direction(monkeypatch):
    """Atrapa: wymiar 0 = temat (zdrowie/inwestycje), wymiar 1 = schemat (operator A/B), reszta szum.
    Przed LEACE dominuje temat; po LEACE materiały tego samego schematu są bliżej niż różnych."""
    rng = np.random.default_rng(0)

    def fake_encode(texts, model=None):
        X = []
        for t in texts:
            v = rng.normal(0, 0.05, 16)
            v[0] = 3.0 if "suplement" in t else -3.0          # temat (słownik: zdrowie vs inwestycje)
            v[1] = 1.0 if "SCHEMAT_A" in t else -1.0          # schemat perswazji
            X.append(v / np.linalg.norm(v))
        return np.vstack(X)

    monkeypatch.setattr(template, "encode", fake_encode)
    body = lambda topic, s: " ".join([f"To jest zdanie numer {k} o {topic} {s} z dodatkowym tekstem, żeby fragment był długi."  # noqa: E731
                                      for k in range(12)])
    mats = [_mat("a1", body("suplement lekarz", "SCHEMAT_A")), _mat("a2", body("inwestycj zysk akcj", "SCHEMAT_A")),
            _mat("b1", body("suplement lekarz", "SCHEMAT_B")), _mat("b2", body("inwestycj zysk akcj", "SCHEMAT_B"))]
    sp = template.TemplateSpace(mats, encoder="bge-m3")
    assert sp.rank >= 1
    raw = sp.sim("a1", "a2", "surowe") - sp.sim("a1", "b1", "surowe")
    leace = sp.sim("a1", "a2") - sp.sim("a1", "b1")
    assert raw < 0 < leace  # przed: bliżej ten sam temat; po: bliżej ten sam schemat
    rows = template.separation(sp, {"a1": "A", "a2": "A", "b1": "B", "b2": "B"},
                               {"a1": "zdrowie", "a2": "inwestycje", "b1": "zdrowie", "b2": "inwestycje"})
    by = {r["wariant"]: r for r in rows}
    assert by["LEACE (bez tematu)"]["odstęp (ta sama − różne)"] > by["surowe"]["odstęp (ta sama − różne)"]
    assert set(template.project_2d(sp, "surowe")) == {"a1", "a2", "b1", "b2"}
