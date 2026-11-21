"""Config loading: YAML defaults plus .env secrets."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]


def load_config(path: str | Path | None = None, overrides: dict | None = None) -> dict[str, Any]:
    load_dotenv(ROOT / ".env")
    p = Path(path) if path else ROOT / "config" / "default.yaml"
    with open(p) as f:
        cfg = yaml.safe_load(f)
    for k, v in (overrides or {}).items():
        d = cfg
        parts = k.split(".")
        for part in parts[:-1]:
            d = d.setdefault(part, {})
        d[parts[-1]] = v
    return cfg


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def git_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, stderr=subprocess.DEVNULL, text=True
        ).strip()
    except Exception:
        return "nogit"


def pick_device(pref: str = "auto") -> str:
    if pref != "auto":
        return pref
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def path(rel: str) -> Path:
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    return p
