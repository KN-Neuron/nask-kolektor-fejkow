"""Wizerunki osób: wykrywanie twarzy i ich osadzenia (bez uczenia po naszej stronie, bez nazw osób).

Detektor YuNet i rozpoznawanie SFace z OpenCV Zoo (ONNX, Apache-2.0, razem ok. 39 MB; `code/models/`, pobieranie: `python -m embsim.faces --download`).
Nie rozpoznajemy, KTO to jest: porównujemy, czy ta sama twarz występuje w dwóch materiałach. Osadzenie twarzy to 128 liczb; dwie twarze uznajemy
za tę samą osobę, gdy kosinus ≥ 0,45 (autorzy SFace podają 0,363 dla zdjęć dobrej jakości, my zostawiamy margines na zrzuty).
Twarz na zrzucie to ślad, nie dowód: ta sama osoba występuje też na legalnych stronach. Zmierzyliśmy kanał `face` jako składnik wzoru
(score.py, waga w konfiguracji): na teście formatów NASK nie poprawił wyników (B 8/13 → 7/13, A i C bez zmian), więc jest przesłanką w
wyjaśnieniu decyzji (Match.extra_shared), a nie częścią wyniku.
"""
from __future__ import annotations

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

_models = None


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


if __name__ == "__main__":
    if "--download" in sys.argv:
        download()
        print("modele w", MODELS)
    else:
        print("dostępne:", available())
