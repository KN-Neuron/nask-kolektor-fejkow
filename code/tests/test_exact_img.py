"""Kanał dokładnych obrazów, filtr pospolitych usług, reguła identycznych obrazów i ocena wielu materiałów naraz."""
import base64
import io
import json
import zipfile

import numpy as np
from PIL import Image

from embsim import analyze as A
from embsim.api import Gallery, case_from_folder, demo_thresholds, with_exact_channels
from embsim.bench import load_frozen
from embsim.features import load_case


def _png(seed: int) -> bytes:
    rng = np.random.default_rng(seed)
    b = io.BytesIO()
    Image.fromarray(rng.integers(0, 255, (40, 40, 3), dtype=np.uint8)).save(b, "PNG")
    assert len(b.getvalue()) >= 2048
    return b.getvalue()


def _har(urls_imgs):
    return json.dumps({"log": {"entries": [
        {"request": {"url": u}, "response": {"content": {"mimeType": "image/png", "encoding": "base64",
                                                         "text": base64.b64encode(d).decode()} if d else {}}}
        for u, d in urls_imgs]}})


def _case(root, name, html, har=None, files=None):
    d = root / name
    d.mkdir(parents=True)
    (d / "p.html").write_text(f"<html><body>{html}</body></html>", encoding="utf-8")
    if har:
        (d / "p.har").write_text(_har(har), encoding="utf-8")
    for fn, data in (files or {}).items():
        (d / fn).parent.mkdir(parents=True, exist_ok=True)
        (d / fn).write_bytes(data)
    return d


def test_img_from_har_and_saved_assets_match(tmp_path):
    img = _png(1)
    a = _case(tmp_path, "a", "x", har=[("https://evil.test/a/b/hero.png", img)])
    b = _case(tmp_path, "b", "y", files={"p_files/hero.png": img})
    ca, cb = load_case(a), load_case(b)
    assert ca.sets["img"] == cb.sets["img"] and len(ca.sets["img"]) == 1
    assert ca.meta["img_names"][next(iter(ca.sets["img"]))] == "hero.png"


def test_tiny_images_ignored(tmp_path):
    b = io.BytesIO()
    Image.new("RGB", (4, 4)).save(b, "PNG")
    d = _case(tmp_path, "a", "x", files={"icon.png": b.getvalue()})
    assert "img" not in load_case(d).sets


def test_common_hosts_dropped_only_in_demo_path(tmp_path):
    d = _case(tmp_path, "a", "x", har=[("https://fonts.gstatic.com/s/inter/v1/x.woff2", None),
                                       ("https://evil.test/kit/lp/a.js?utm_id=1", None)])
    assert "gstatic.com" in load_case(d).sets["host"]                    # ewaluacja: bez zmian
    c = case_from_folder(d)
    assert c.sets["host"] == {"evil.test"} and "/s/inter" not in c.sets["kit"]


def test_exact_channel_keeps_scores_without_images():
    cfg, _ = load_frozen("v3_mixed_pca")
    new = with_exact_channels(cfg)
    assert "img" in new.weights_campaign and "img" in new.rotating and "img" not in cfg.weights_campaign
    n_old, n_new = len(cfg.weights_campaign), len(new.weights_campaign)
    assert abs(new.e_ref["campaign"] - cfg.e_ref["campaign"] * n_old / n_new) < 1e-12


def test_identical_images_mean_same_campaign_but_shared_network_icon_does_not(tmp_path):
    icon, h1, h2, shot = _png(2), _png(3), _png(4), _png(5)
    g = Gallery(embed_fn=A.hash_embed, thresholds=demo_thresholds())
    g.add(case_from_folder(_case(tmp_path, "k1", "lokata zysk prezes", files={"a_files/i.png": icon, "a_files/h.png": h1,
                                                                                   "zrzut.png": shot})))
    g.add(case_from_folder(_case(tmp_path, "k2", "kryptowaluty bitcoin", files={"a_files/i.png": icon, "a_files/h.png": h2})))
    dup = A.case_from_inputs([("zrzut.png", shot)], ocr=False)[0]                 # ten sam zrzut drugi raz
    d = g.query(dup)
    assert d.verdict == "znana_kampania" and d.exact_of == "k1" and "identyczny" in d.explain()
    only_icon = A.case_from_inputs([("i.png", icon)], ocr=False)[0]                # ikona wspólna dla dwóch kampanii
    assert g.query(only_icon).exact_of is None


def test_assess_zip_links_new_materials_among_themselves(tmp_path):
    img, img2 = _png(6), _png(7)                                                   # kompletny zestaw 2 obrazów (jedno wspólne zdjęcie to zasób, nie dowód)
    src = tmp_path / "src" / "zbior"
    _case(src, "n1", "nowa kampania alfa", files={"x_files/h.png": img, "x_files/g.png": img2})
    _case(src, "n2", "nowa kampania alfa wariant", files={"x_files/h.png": img, "x_files/g.png": img2})
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for f in src.rglob("*"):
            if f.is_file():
                z.write(f, f.relative_to(tmp_path / "src"))
    root = A.extract_zip(buf.getvalue(), tmp_path / "out")
    assert sorted(p.name for p in A.case_dirs(root)) == ["n1", "n2"]
    g = Gallery(embed_fn=A.hash_embed, thresholds=demo_thresholds())
    rows, gg = A.assess_folder(g, root)
    assert len(g) == 0 and len(gg) == 2                                            # domyślnie na kopii
    assert rows[1]["werdykt"] == "Znana kampania" and rows[1]["kampania"] == rows[0]["kampania"]


def test_zip_slip_rejected(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("../evil.txt", "x")
    try:
        A.extract_zip(buf.getvalue(), tmp_path / "out")
    except ValueError:
        return
    raise AssertionError("ścieżka poza katalogiem nie została odrzucona")


def test_jury_summary_by_criteria():
    import pandas as pd

    from embsim import jury as J

    ra = pd.DataFrame([
        {"oczekiwane": "kampania", "wynik": "kampania", "ocena": "OK", "_grupa": True, "_powody": 2},
        {"oczekiwane": "kampania", "wynik": "sieć", "ocena": "częściowo (dobra grupa, inny poziom)", "_grupa": True, "_powody": 1},
        {"oczekiwane": "nowy", "wynik": "nowy", "ocena": "OK", "_grupa": False, "_powody": 0},
        {"oczekiwane": "nowy", "wynik": "kampania", "ocena": "BŁĄD: połączono obce", "_grupa": False, "_powody": 1}])
    rows = {(r["miara"]): r["wynik"] for r in J.summary(ra, None, None)}
    assert rows["trafione na poziomie kampanii"].startswith("1/2")
    assert rows["precyzja decyzji „znana kampania”"].startswith("1/2")        # 2 decyzje „kampania”, jedna właściwa
    assert rows["obce materiały zostawione jako „nowy wzorzec”"].startswith("1/2")
    assert rows["decyzje połączeniowe z podanymi przesłankami"].startswith("3/3")
    assert J.summary(None, None, None) == []
