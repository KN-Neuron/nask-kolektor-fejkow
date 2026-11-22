"""Wizerunki osób: wykrywanie twarzy i ich osadzenia (bez uczenia po naszej stronie). Nazwiska tylko z bazy znanych osób (niżej).

Detektor YuNet i rozpoznawanie SFace z OpenCV Zoo (ONNX, Apache-2.0, razem ok. 39 MB; `code/models/`, pobieranie: `python -m embsim.faces --download`).
Bez bazy nie rozpoznajemy, KTO to jest: porównujemy, czy ta sama twarz występuje w dwóch materiałach. Osadzenie twarzy to 128 liczb; dwie twarze uznajemy
za tę samą osobę, gdy kosinus ≥ 0,45 (autorzy SFace podają 0,363 dla zdjęć dobrej jakości, my zostawiamy margines na zrzuty).
Twarz na zrzucie to ślad, nie dowód: ta sama osoba występuje też na legalnych stronach. Zmierzyliśmy kanał `face` jako składnik wzoru
(score.py, waga w konfiguracji): na teście formatów NASK nie poprawił wyników (B 8/13 → 7/13, A i C bez zmian), więc jest przesłanką w
wyjaśnieniu decyzji (Match.extra_shared), a nie częścią wyniku.

Baza znanych osób (opcjonalna, KNOWN_FILE): osadzenia twarzy osób, których wizerunki oszuści podszywają (prezesi, dziennikarze,
politycy), liczone z folderu zdjęć referencyjnych `osoby/<Imię Nazwisko>/*.jpg` (`python -m embsim.faces --known /ścieżka/osoby`).
Wtedy umiemy też powiedzieć, KTO jest na materiale, i połączyć dwa materiały z RÓŻNYMI zdjęciami tej samej osoby (każde podobne do
wzorca, choć do siebie nawzajem mniej). W pliku są tylko liczby (128 na zdjęcie) i nazwiska, bez samych zdjęć.
Dopasowanie do bazy: najbliższa osoba, gdy kosinus ≥ KNOWN_MATCH i wyprzedza drugą osobę o KNOWN_MARGIN (inaczej nie nazywamy nikogo).
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

import numpy as np

MODELS = Path(__file__).resolve().parents[2] / "models"
DETECTOR = MODELS / "face_detection_yunet_2023mar.onnx"
RECOGNIZER = MODELS / "face_recognition_sface_2021dec.onnx"
URLS = {DETECTOR: "https://huggingface.co/opencv/face_detection_yunet/resolve/main/face_detection_yunet_2023mar.onnx",
        RECOGNIZER: "https://huggingface.co/opencv/face_recognition_sface/resolve/main/face_recognition_sface_2021dec.onnx"}
SAME_PERSON = 0.45           # kosinus: ta sama osoba. Autorzy SFace podają 0,363 dla zdjęć dobrej jakości; na zrzutach ekranu bierzemy margines
MIN_SCORE, MIN_SIDE, MAX_IMAGES, MAX_SIDE = 0.9, 40, 8, 1280

KNOWN_FILE = Path(__file__).resolve().parents[2] / "config" / "embsim" / "znane_osoby.json"
KNOWN_MATCH, KNOWN_MARGIN = 0.45, 0.05

_models = None
_known: dict | None = None


def available() -> bool:
    return DETECTOR.exists() and RECOGNIZER.exists()


def download() -> None:
    MODELS.mkdir(parents=True, exist_ok=True)
    for path, url in URLS.items():
        if not path.exists():
            urllib.request.urlretrieve(url, path)


def _load():
    global _models
    if _models is None:
        import cv2

        _models = (cv2.FaceDetectorYN.create(str(DETECTOR), "", (320, 320), MIN_SCORE, 0.3, 50), cv2.FaceRecognizerSF.create(str(RECOGNIZER), ""))
    return _models


def face_embeddings(data: bytes) -> list[list[float]]:
    """Osadzenia (128 liczb, znormalizowane) twarzy widocznych na obrazie; pusta lista, gdy brak twarzy albo modeli."""
    if not available():
        return []
    try:
        import cv2
    except ImportError:
        return []

    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return []
    h, w = img.shape[:2]
    if max(h, w) > MAX_SIDE:                                  # duże zrzuty zmniejszamy: szybciej i bez utraty twarzy
        k = MAX_SIDE / max(h, w)
        img = cv2.resize(img, (int(w * k), int(h * k)))
        h, w = img.shape[:2]
    det, rec = _load()
    det.setInputSize((w, h))
    _, found = det.detect(img)
    out = []
    for f in (found if found is not None else []):
        if min(f[2], f[3]) < MIN_SIDE:
            continue
        v = rec.feature(rec.alignCrop(img, f)).ravel().astype(np.float64)
        out.append([round(float(x), 5) for x in v / (np.linalg.norm(v) or 1.0)])
    return out


def faces_of(images: list[tuple[str, bytes]]) -> list[list[float]]:
    """Twarze z największych obrazów materiału (do MAX_IMAGES), bez powtórzeń tego samego obrazu."""
    out: list[list[float]] = []
    seen = set()
    for _, data in sorted(images, key=lambda t: -len(t[1]))[:MAX_IMAGES]:
        if hash(data) in seen:
            continue
        seen.add(hash(data))
        out.extend(face_embeddings(data))
    return out


def best_match(a: list[list[float]], b: list[list[float]]) -> float | None:
    """Największy kosinus między twarzami z a i b, jeśli co najmniej jedna para jest „tą samą osobą”; inaczej None."""
    if not a or not b:
        return None
    m = float((np.asarray(a) @ np.asarray(b).T).max())
    return m if m >= SAME_PERSON else None


def build_known(root: Path, out: Path = KNOWN_FILE) -> dict[str, int]:
    """Baza znanych osób z folderu `root/<Imię Nazwisko>/*.{jpg,png,webp}`. Zwraca liczbę przyjętych zdjęć na osobę.

    Zdjęcia z wolnych repozytoriów bywają grupowe (osoba obok kogoś innego), więc nie bierzemy „największej twarzy” na ślepo: wzorzec
    osoby to średnia twarzy ze zdjęć, na których jest tylko jedna twarz, a z każdego zdjęcia bierzemy twarz najbliższą wzorcowi i tylko
    wtedy, gdy jest „tą samą osobą” (SAME_PERSON). Zdjęcia bez zgodnej twarzy odrzucamy. Opcjonalny `root/zrodla.json` (pliki, licencje,
    adresy; i-ty wpis opisuje plik `i.*`) przepisujemy do bazy dla przyjętych zdjęć.
    """
    import cv2

    people: dict[str, list[list[float]]] = {}
    used: dict[str, list[str]] = {}
    for d in sorted(p for p in Path(root).iterdir() if p.is_dir()):
        per_img = []
        for f in sorted(d.iterdir()):
            img = cv2.imread(str(f)) if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp") else None
            ok, buf = cv2.imencode(".png", img) if img is not None else (False, None)
            if ok and (embs := face_embeddings(buf.tobytes())):
                per_img.append((f.stem, np.asarray(embs)))
        anchors = [e[0] for _, e in per_img if len(e) == 1]
        if not anchors:
            continue
        c = np.mean(anchors, axis=0)
        c /= np.linalg.norm(c) or 1.0
        keep = [(stem, e[int(np.argmax(e @ c))]) for stem, e in per_img if float((e @ c).max()) >= SAME_PERSON]
        if keep:
            people[d.name] = [[round(float(x), 5) for x in v] for _, v in keep]
            used[d.name] = [stem for stem, _ in keep]
    src = Path(root) / "zrodla.json"
    meta = json.loads(src.read_text(encoding="utf-8")) if src.exists() else {}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"model": RECOGNIZER.name, "osoby": people, "źródła": {k: [m for i, m in enumerate(meta.get(k, [])) if str(i) in used[k]] for k in people}},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    global _known
    _known = None
    return {k: len(v) for k, v in people.items()}


def known() -> dict[str, np.ndarray]:
    """Nazwisko -> macierz osadzeń zdjęć referencyjnych; {} bez pliku bazy."""
    global _known
    if _known is None:
        try:
            raw = json.loads(KNOWN_FILE.read_text(encoding="utf-8")).get("osoby", {})
            _known = {k: np.asarray(v, dtype=np.float64) for k, v in raw.items() if v}
        except (OSError, ValueError):
            _known = {}
    return _known


def identify(faces: list[list[float]] | None, base: dict[str, np.ndarray] | None = None) -> dict[str, float]:
    """Znane osoby na materiale: nazwisko -> najlepszy kosinus. Osoba tylko z wyraźnym zapasem nad drugą (KNOWN_MARGIN)."""
    base = known() if base is None else base
    if not faces or not base:
        return {}
    F = np.asarray(faces, dtype=np.float64)
    names = list(base)
    S = np.stack([(F @ base[n].T).max(axis=1) for n in names], axis=1)     # twarz × osoba: najlepsze zdjęcie wzorcowe
    out: dict[str, float] = {}
    for row in S:
        order = np.argsort(-row)
        top = row[order[0]]
        second = row[order[1]] if len(order) > 1 else -1.0
        if top >= KNOWN_MATCH and top - second >= KNOWN_MARGIN:
            n = names[order[0]]
            out[n] = max(out.get(n, 0.0), round(float(top), 3))
    return out


if __name__ == "__main__":
    if "--known" in sys.argv:
        print(build_known(Path(sys.argv[sys.argv.index("--known") + 1])), "->", KNOWN_FILE)
    elif "--download" in sys.argv:
        download()
        print("modele w", MODELS)
    else:
        print("dostępne:", available())
