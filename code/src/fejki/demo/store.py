"""Indeks materiałów: budowa ze zbioru przypadków, zapis, odczyt, dokładanie nowych materiałów."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from ..config import ROOT
from .material import Material, load_persons, material_from_folder

INDEX = ROOT / "artifacts" / "demo" / "index.json"


class Index(BaseModel):
    built_at: str
    data_dir: str
    materials: list[Material] = Field(default_factory=list)
    infra: dict = Field(default_factory=dict)  # domena -> InfraRecord (dict), tylko bierne dane

    def by_id(self) -> dict[str, Material]:
        return {m.id: m for m in self.materials}


def case_dirs(data_dir: Path) -> list[Path]:
    """Foldery przypadków. Akceptuje katalog z podfolderami-przypadkami albo katalog z jednym poziomem pośrednim."""
    data_dir = Path(data_dir)
    subs = [p for p in data_dir.iterdir() if p.is_dir() and not p.name.startswith(".")]
    if len(subs) == 1 and all(q.is_dir() for q in subs[0].iterdir() if not q.name.startswith(".")):
        subs = [p for p in subs[0].iterdir() if p.is_dir()]
    return sorted(subs, key=lambda p: (int(p.name) if p.name.isdigit() else 10**9, p.name))


def build(data_dir: Path, ocr: bool = True, progress=None, extra: list[Path] | None = None) -> Index:
    """Indeks z folderu przypadków; `extra` = dodatkowe zbiory referencyjne (np. skany urlscan), ich materiały dostają prefiks `u:`."""
    persons = load_persons()
    dirs = [(d, "") for d in case_dirs(data_dir)]
    for e in extra or []:
        if Path(e).exists():
            dirs += [(d, "u:") for d in case_dirs(Path(e))]
    mats = []
    for k, (d, prefix) in enumerate(dirs):
        if progress:
            progress(k, len(dirs), d.name)
        m = material_from_folder(d, ocr=ocr, persons=persons)
        if prefix:
            m.id = prefix + d.name[:10]
            m.label = f"skan urlscan {d.name[:8]}"
            m.source = "urlscan"
        mats.append(m)
    return Index(built_at=datetime.now(UTC).isoformat(timespec="seconds"), data_dir=str(data_dir), materials=mats)


def collect_infra(idx: Index, materials: list[Material] | None = None) -> list[str]:
    """Bierne dane o domenach docelowych (DNS, ASN, RDAP, crt.sh) z pamięcią podręczną. Zwraca listę błędów."""
    from ..infra.collect import collect_cached

    errs = []
    for m in materials or idx.materials:
        for d in m.landing_domains:
            if d in idx.infra:
                continue
            try:
                rec = collect_cached(d, [u for u in m.urls if d in u][:20])
                idx.infra[d] = rec.model_dump()
                if rec.errors:
                    errs.append(f"{d}: {', '.join(rec.errors)}")
            except Exception as e:  # brak sieci itp.: analiza działa dalej bez tego kanału
                errs.append(f"{d}: {type(e).__name__}")
    return errs


def infra_records(idx: Index) -> dict:
    from ..infra.collect import InfraRecord

    return {d: InfraRecord.model_validate(r) for d, r in idx.infra.items()}


def save(idx: Index, path: Path = INDEX) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(idx.model_dump_json(indent=1), encoding="utf-8")
    return path


def load(path: Path = INDEX) -> Index | None:
    if not path.exists():
        return None
    return Index.model_validate(json.loads(path.read_text(encoding="utf-8")))
