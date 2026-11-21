"""File adapter: JSONL with Ad-shaped records; tolerant to missing optional fields."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from ..schema import Ad


def read_jsonl(path: str | Path) -> list[Ad]:
    ads = []
    for i, line in enumerate(Path(path).read_text().splitlines()):
        if not line.strip():
            continue
        d = json.loads(line)
        d.setdefault("ad_id", f"file:{Path(path).stem}-{i}")
        d.setdefault("source", "file")
        d.setdefault("first_seen_at", datetime.now(UTC).isoformat())
        ads.append(Ad.model_validate(d))
    return ads
