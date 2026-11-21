"""Wczytanie jednego przypadku (folderu) do postaci: teksty + obrazy. Bez wyciągania cech."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from bs4 import BeautifulSoup

IMG_EXT = {".png", ".jpg", ".jpeg", ".webp"}
MAX_TEXT_CHARS = 6000


@dataclass
class Material:
    id: str
    texts: list[str] = field(default_factory=list)
    images: list[Path] = field(default_factory=list)


def html_text(path: Path) -> str:
    soup = BeautifulSoup(path.read_bytes(), "lxml")
    for t in soup(["script", "style", "noscript", "svg"]):
        t.decompose()
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    body = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    return f"{title}\n{body}"[:MAX_TEXT_CHARS].strip()


def info_text(path: Path) -> str:
    d = json.loads(path.read_text())
    return "\n".join(str(d[k]) for k in ("title", "description", "uploader", "channel") if d.get(k))


def _walk(root: Path):
    """Pliki przypadku, bez katalogów `*_files` (zasoby zapisanej strony)."""
    for p in sorted(root.iterdir()):
        if p.is_dir():
            if not p.name.endswith("_files"):
                yield from _walk(p)
        else:
            yield p


def load_case(root: Path) -> Material:
    m = Material(id=root.name)
    for p in _walk(root):
        ext = p.suffix.lower()
        if ext in IMG_EXT:
            m.images.append(p)
        elif ext in {".html", ".htm"}:
            if t := html_text(p):
                m.texts.append(t)
        elif p.name.endswith(".info.json"):
            if t := info_text(p):
                m.texts.append(t)
    return m


def load_cases(root: Path) -> list[Material]:
    return [load_case(d) for d in sorted(root.iterdir(), key=lambda d: (len(d.name), d.name)) if d.is_dir()]
