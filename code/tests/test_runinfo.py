from embsim import runinfo


def test_provenance_has_commit_config_thresholds_and_data_fingerprint(tmp_path):
    f = tmp_path / "d.jsonl"
    f.write_text("{}")
    p = runinfo.provenance("meta", [f])
    assert {"commit", "konfiguracja", "odcisk_konfiguracji", "progi", "dane", "profil"} <= set(p)
    assert p["progi"]["campaign"] == 0.5 and p["profil"] == "meta"
    assert runinfo.provenance("meta", [f])["dane"] == p["dane"]                      # ten sam plik, ten sam odcisk
    f.write_text("{} {}")
    assert runinfo.provenance("meta", [f])["dane"] != p["dane"]                      # zmieniony plik, inny odcisk


def test_differs_reports_changed_threshold_and_commit():
    now = runinfo.provenance("strony")
    old = {**now, "commit": "abc1234", "progi": {"campaign": 0.9, "operator": 0.25}}
    msgs = runinfo.differs(old, now)
    assert any(m.startswith("commit") for m in msgs) and any(m.startswith("progi") for m in msgs)
    assert runinfo.differs(now, now) == []
