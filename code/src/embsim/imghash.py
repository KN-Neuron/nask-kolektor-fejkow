"""Bliskie duplikaty obrazów (logo, zdjęcie, zrzut po zmianie rozmiaru lub ponownej kompresji): odcisk percepcyjny dHash, bez modelu i bez uczenia.

`img` w features.py łapie tylko identyczne bajty. Tu porównujemy wygląd: 64-bitowy dHash (znak różnicy sąsiednich pikseli po zmniejszeniu do 9×8);
dwa obrazy to „ten sam obraz”, gdy odległość Hamminga ≤ 6 z 64. To NIE jest wykrywanie logotypów wewnątrz zrzutu (np. logo gazety na
zrzucie całej strony): łączymy obrazy, które same są logo lub zdjęciem użytym w obu materiałach.
"""
from __future__ import annotations

import io

MIN_SIDE, MAX_PER_CASE, MAX_DIST = 48, 200, 6


def dhash(data: bytes) -> int | None:
    try:
        from PIL import Image

        im = Image.open(io.BytesIO(data))
        if min(im.size) < MIN_SIDE:
            return None
        px = list(im.convert("L").resize((9, 8)).getdata())
    except Exception:
        return None
    h = 0
    for r in range(8):
        for c in range(8):
            h = (h << 1) | (px[r * 9 + c] > px[r * 9 + c + 1])
    return h


def hashes_of(blobs: list[tuple[str, bytes]], sha) -> list[list]:
    """[[hash_hex, nazwa, sha], ...] dla obrazów materiału (największe pierwsze)."""
    out, seen = [], set()
    for name, data in sorted(blobs, key=lambda t: -len(t[1]))[:MAX_PER_CASE]:
        k = sha(data)
        if not k or k in seen:
            continue
        seen.add(k)
        if (h := dhash(data)) is not None:
            out.append([f"{h:016x}", name.rsplit("/", 1)[-1].split("?")[0][:60], k])
    return out


def near_pairs(a: list[list], b: list[list], max_dist: int = MAX_DIST) -> list[tuple[str, str, int]]:
    """Pary (nazwa a, nazwa b, odległość) obrazów podobnych, ale o różnych bajtach (identyczne łapie kanał `img`)."""
    out = []
    for ha, na, ka in a or []:
        for hb, nb, kb in b or []:
            if ka != kb and (d := bin(int(ha, 16) ^ int(hb, 16)).count("1")) <= max_dist:
                out.append((na, nb, d))
    return sorted(out, key=lambda t: t[2])
