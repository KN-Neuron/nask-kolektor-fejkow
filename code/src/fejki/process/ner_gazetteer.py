"""Closed-list public-person mentions in text (the only 'identity' path; no faces)."""
from __future__ import annotations

import re
from pathlib import Path

from rapidfuzz import fuzz


def load_gazetteer(path: str | Path) -> list[str]:
    return [l.strip() for l in Path(path).read_text().splitlines() if l.strip() and not l.startswith("#")]


def _stem(w: str) -> str:
    """Crude Polish inflection handling: trim the last 2 chars of long words."""
    w = w.lower()
    return w[:-2] if len(w) > 5 else w[:-1] if len(w) > 3 else w


def find_entities(text: str, names: list[str], threshold: int = 88) -> list[str]:
    words = re.findall(r"\w+", text)
    found: list[str] = []
    for name in names:
        parts = name.split()
        n = len(parts)
        target = " ".join(_stem(p) for p in parts)
        for i in range(len(words) - n + 1):
            cand = " ".join(_stem(w) for w in words[i : i + n])
            if fuzz.ratio(cand, target) >= threshold:
                found.append(name)
                break
    return found
