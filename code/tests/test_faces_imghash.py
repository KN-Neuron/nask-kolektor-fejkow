import io

import numpy as np
import pytest
from PIL import Image

from embsim import faces, imghash
from embsim.api import Gallery, case_from_text


def picture(seed: int, size=(200, 160)) -> Image.Image:
    rng = np.random.default_rng(seed)
    base = rng.integers(0, 255, (8, 10, 3), dtype=np.uint8)
    return Image.fromarray(base).resize(size, Image.BILINEAR)


def encode(im: Image.Image, fmt="PNG", **kw) -> bytes:
    b = io.BytesIO()
    im.save(b, fmt, **kw)
    return b.getvalue()


def test_dhash_survives_resize_and_recompression_but_not_other_images():
    im = picture(1)
    a = [[f"{imghash.dhash(encode(im)):016x}", "logo.png", "k1"]]
    b = [[f"{imghash.dhash(encode(im.resize((100, 80)), 'JPEG', quality=60)):016x}", "logo_small.jpg", "k2"]]
    other = [[f"{imghash.dhash(encode(picture(2))):016x}", "inne.png", "k3"]]
    assert imghash.near_pairs(a, b)[0][:2] == ("logo.png", "logo_small.jpg")
    assert imghash.near_pairs(a, other) == []
    assert imghash.near_pairs(a, [[a[0][0], "ten_sam_plik", "k1"]]) == []          # identyczne bajty łapie kanał img, nie ten


def test_tiny_images_have_no_hash():
    assert imghash.dhash(encode(picture(3, (20, 20)))) is None


def test_best_match_threshold_and_empty_inputs():
    v = np.zeros(128); v[0] = 1.0
    w = np.zeros(128); w[0], w[1] = 0.6, 0.8                                         # kosinus 0,6
    z = np.zeros(128); z[1] = 1.0                                                    # kosinus 0
    assert faces.best_match([v.tolist()], [w.tolist()]) == pytest.approx(0.6)
    assert faces.best_match([v.tolist()], [z.tolist()]) is None
    assert faces.best_match([], [v.tolist()]) is None and faces.best_match(None, None) is None


@pytest.mark.skipif(not faces.available(), reason="brak modeli twarzy (python -m embsim.faces --download)")
def test_no_faces_on_plain_image():
    assert faces.face_embeddings(encode(picture(4, (300, 300)))) == []


def test_face_and_near_duplicate_image_become_reasons_outside_the_score():
    from embsim.analyze import top_reasons

    emb = lambda texts: np.eye(len(texts), 96)
    g = Gallery(embed_fn=emb, thresholds={"campaign": 0.9, "operator": 0.9})
    face = [(np.eye(128)[0]).tolist()]
    a = case_from_text("A", "Pierwsza oferta numer jeden", kit={"/a/b"})
    a.meta["faces"] = face
    a.meta["dhash"] = [["0123456789abcdef", "logo.png", "k1"]]
    g.add(a)
    q = case_from_text("Q", "Zupełnie inny tekst o czymś innym", kit={"/x/y"})
    q.meta["faces"] = face
    q.meta["dhash"] = [["0123456789abcdee", "logo_mini.png", "k2"]]
    m = g.query(q, 3).matches[0]
    assert "face" in m.extra_shared and "dhash" in m.extra_shared
    assert any("wizerunek" in r for r in top_reasons(m, 3))
