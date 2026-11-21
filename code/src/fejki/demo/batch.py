"""Wsadowa analiza nowego zbioru (np. ukryty zbiór testowy organizatora): folder lub zip → decyzja dla każdego materiału.

Obsługiwane układy wejścia (odporność na różnice w formacie):
- folder z podfolderami-przypadkami (jak `DANE.zip`), także z jednym poziomem pośrednim (`do_udostepnienia/<nr>/...`);
- płaski folder z plikami (każdy plik HTML/HAR/zrzut/wideo/`info.json` to osobny materiał; pliki o tej samej nazwie bazowej
  (np. `x.html` + `x.har` + `x.png`) łączymy w jeden materiał);
- archiwum `.zip` (rozpakowywane bezpiecznie, nazwy UTF-8 bez flagi naprawiane).

Wynik: tabela „materiał → decyzja → kampania → sieć → wynik → przesłanki” i propozycje NOWYCH kampanii (grupy nowych
materiałów, które pasują do siebie, a nie pasują do znanych).
"""
from __future__ import annotations

import re
import shutil
import tempfile
import zipfile
from pathlib import Path

import pandas as pd

from .material import HTML_EXT, IMG_EXT, VID_EXT, Material, build_material, is_har, load_persons, material_from_folder
from .similar import CONTENT_RELATIONS, all_pairs, campaigns, match
from .store import Index, case_dirs

KNOWN_EXT = HTML_EXT | IMG_EXT | VID_EXT | {".har", ".json", ".txt"}


def extract_zip(path: Path, dest: Path) -> Path:
    """Bezpieczne rozpakowanie (bez wyjścia poza `dest`), z naprawą nazw UTF-8 zapisanych bez flagi."""
    dest = dest.resolve()
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            name = info.filename
            if not (info.flag_bits & 0x800):
                try:
                    name = name.encode("cp437").decode("utf-8")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    pass
            target = (dest / name).resolve()
            if not str(target).startswith(str(dest)):
                continue  # ścieżka wychodząca poza katalog docelowy
            if name.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
    return dest


def _stem_key(p: Path) -> str:
    s = re.sub(r"\.info$", "", p.stem, flags=re.I)
    return re.sub(r"[\s_\-]*\(\d+\)$", "", s).lower()


def discover(path: Path) -> list[tuple[str, list[Path]]]:
    """Lista (identyfikator, pliki) dla folderu lub zipa, niezależnie od układu."""
    path = Path(path)
    if path.is_file() and path.suffix.lower() == ".zip":
        tmp = Path(tempfile.mkdtemp(prefix="fejki_zip_"))
        path = extract_zip(path, tmp)
    dirs = case_dirs(path) if path.is_dir() else []
    if dirs:
        return [(d.name, [f for f in d.rglob("*") if f.is_file()]) for d in dirs]
    files = [f for f in path.rglob("*") if f.is_file() and f.suffix.lower() in KNOWN_EXT and not f.name.startswith(".")]
    groups: dict[str, list[Path]] = {}
    for f in files:
        groups.setdefault(_stem_key(f), []).append(f)
    return [(k, v) for k, v in sorted(groups.items())]


def materials_from(path: Path, ocr: bool = True, progress=None) -> list[Material]:
    persons = load_persons()
    items = discover(path)
    out = []
    for k, (mid, files) in enumerate(items):
        if progress:
            progress(k, len(items), mid)
        base = files[0].parent if files else None
        folder = Path(path) / mid
        if folder.is_dir() and len(files) > 1 and all(f.is_relative_to(folder) for f in files):
            out.append(material_from_folder(folder, ocr=ocr, persons=persons))
        else:
            out.append(build_material(mid, f"nowy {mid}", "folder", files=files, ocr=ocr, persons=persons, base=base))
    return out


def analyze(idx: Index, new: list[Material], thr: float = 0.7, maybe: float = 0.4, infra: dict | None = None,
            semantic: bool = False) -> tuple[pd.DataFrame, list[dict]]:
    """Każdy nowy materiał dopasowuje do znanego zbioru; nieprzypisane grupuje w propozycje nowych kampanii."""
    known = idx.materials
    pairs = all_pairs(known, infra, semantic)
    camps, nets = campaigns(known, pairs, thr, "kampania"), campaigns(known, pairs, thr, "sieć")
    rows, unassigned = [], []
    for m in new:
        base = [k for k in known if k.id != m.id]
        r = match(m, base, camps, nets, thr, maybe, infra, semantic)
        top = r.ranking[0] if r.ranking else None
        assigned = r.decision.startswith("przypisano")
        rows.append({
            "materiał": m.id, "decyzja": r.decision, "kampania": r.best_campaign or "", "sieć": (top or {}).get("network") or "",
            "najlepszy wynik": r.best_score, "przez materiał": (top or {}).get("via", ""), "relacja": (top or {}).get("relation", ""),
            "przesłanki": " | ".join((top or {}).get("evidence", [])[:4]), "braki": "; ".join(m.missing),
            "domeny": ", ".join(m.landing_domains), "tytuł": (m.titles or [""])[0][:90],
        })
        if not assigned:
            unassigned.append(m)
    proposals = []
    if len(unassigned) > 1:
        up = all_pairs(unassigned, infra, semantic)
        for k, c in enumerate(campaigns(unassigned, up, thr, "kampania")):
            if len(c.members) > 1:
                proposals.append({"id": f"N{k + 1}", "materiały": c.members, "nazwa": c.name,
                                  "przesłanki": [e.reason for p in up if p.a in c.members and p.b in c.members and p.score >= thr
                                                 and p.relation in CONTENT_RELATIONS for e in p.evidence[:3]][:6]})
    df = pd.DataFrame(rows)
    nid = {mid: p["id"] for p in proposals for mid in p["materiały"]}
    if not df.empty:
        df["nowa kampania (propozycja)"] = df["materiał"].map(nid).fillna("")
    return df, proposals
