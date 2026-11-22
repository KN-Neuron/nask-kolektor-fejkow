"""Pochodzenie wyniku: commit, konfiguracja, progi i odcisk danych zapisywane obok każdego raportu ewaluacji (audyt, pkt 23).

Raport bez tych pól nie mówi, czy liczby pochodzą z obecnej wersji silnika. `provenance()` zwraca słownik do dopisania do JSON-a raportu, a `differs()`
pokazuje, czym obecna wersja różni się od zapisanej (inny commit, konfiguracja, próg albo dane).
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def data_fingerprint(*paths: str | Path) -> str:
    """Skrót z nazw, rozmiarów i czasów modyfikacji plików (szybki; nie czyta zawartości dużych zbiorów)."""
    h = hashlib.sha1()
    for p in sorted(map(str, paths)):
        f = Path(p)
        if f.is_file():
            st = f.stat()
            h.update(f"{f.name}|{st.st_size}|{int(st.st_mtime)}".encode())
    return h.hexdigest()[:12]


def provenance(profile: str | None = None, data: list[str | Path] | None = None) -> dict:
    from .api import DEFAULT_CONFIG
    from .bench import load_frozen

    cfg, fr = load_frozen(DEFAULT_CONFIG)
    thresholds = dict(cfg.thresholds)
    if profile:
        from .api import PROFILES

        thresholds.update(PROFILES[profile]())
    return {
        "commit": _git("rev-parse", "--short", "HEAD"),
        "zmiany_nie_zacommitowane": bool(_git("status", "--porcelain", "--", "code/src")),
        "konfiguracja": DEFAULT_CONFIG, "odcisk_konfiguracji": fr.get("fingerprint"),
        "profil": profile, "progi": thresholds,
        "dane": data_fingerprint(*(data or [])),
    }


def differs(saved: dict, now: dict | None = None) -> list[str]:
    now = now or provenance(saved.get("profil"))
    return [f"{k}: zapisano {saved.get(k)!r}, teraz {now.get(k)!r}" for k in ("commit", "odcisk_konfiguracji", "progi") if saved.get(k) != now.get(k)]
