"""Podział subject-based: brak przecieków między treningiem a testem (sztuczne dane)."""
from __future__ import annotations

from fejki.demo.splits import audit, fold_sets, group_kfold, subjects
from test_demo import PIXEL, STORY, _case


def test_subjects_group_everything_that_shares_a_trace(tmp_path):
    a = _case(tmp_path, "1", "Wiem, kto strzelał: zamach", STORY, "alpha-news.live", pixel=PIXEL)
    b = _case(tmp_path, "2", "Inny tytuł strony", "Zupełnie inny tekst o kardiologu i suplementach na ciśnienie.",
              "beta-health.live", pixel=PIXEL, kit="/inny/zestaw")  # tylko wspólny piksel
    c = _case(tmp_path, "3", "Kasyno bonus", "Odbierz bonus 5000 zł w kasynie.", "casino-x.xyz",
              query="utm_source=fb", kit="/casino/static")
    s = subjects([a, b, c])
    assert s["1"] == s["2"] and s["1"].startswith("P")  # wspólny piksel = ten sam podmiot
    assert s["3"] == "solo:3"
    split = group_kfold(s, k=2)
    train, test = fold_sets(split, split.folds[s["1"]])
    assert {"1", "2"} <= test and "3" in test  # podmiot w całości + solowe zawsze w teście
    mats = {m.id: m for m in (a, b, c)}
    other = 1 - split.folds[s["1"]]
    tr, te = fold_sets(split, other)
    assert not audit([mats[x] for x in tr], [mats[x] for x in te])  # czysty podział


def test_audit_catches_naive_split(tmp_path):
    a = _case(tmp_path, "1", "Wiem, kto strzelał: zamach", STORY, "alpha-news.live", pixel=PIXEL)
    b = _case(tmp_path, "2", "Wiem, kto strzelał: zamach", STORY, "beta-news.live", pixel=PIXEL)
    rules = {lk.rule for lk in audit([a], [b])}
    assert {"piksel Meta", "ten sam tytuł", "niemal identyczny tekst"} <= rules
