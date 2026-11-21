"""Domain and contact artifact extraction."""
from __future__ import annotations

import re

import tldextract

from ..schema import Artifact

_TLD = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)  # bundled snapshot, no network

PHONE = re.compile(r"(?<![\d])(?:\+?48)?[\s-]?\d{3}[\s-]?\d{3}[\s-]?\d{3}(?![\d])")
TELEGRAM = re.compile(r"t\.me/[A-Za-z0-9_]{4,}", re.IGNORECASE)
WHATSAPP = re.compile(r"wa\.me/\d+", re.IGNORECASE)
SHORTENERS = ("bit.ly", "tinyurl.com", "cutt.ly", "t.ly", "is.gd", "rebrand.ly", "shorturl.at", "tiny.cc")
URL = re.compile(r"(?:https?://|www\.)[^\s<>\"')]+", re.IGNORECASE)
BARE_DOMAIN = re.compile(r"\b((?:[a-z0-9-]+\.)+(?:[a-z]{2,}))\b(?:/[^\s]*)?", re.IGNORECASE)
RESERVED = {"example", "test", "invalid", "localhost"}


def registered_domain(host: str) -> str | None:
    host = host.strip().lower().strip(".")
    if not host or "." not in host:
        return None
    ext = _TLD(host)
    if ext.domain and ext.suffix:
        return f"{ext.domain}.{ext.suffix}"
    parts = host.split(".")  # reserved TLDs (.example, .test) not in the public suffix list
    if parts[-1] in RESERVED and len(parts) >= 2:
        return ".".join(parts[-2:])
    return None


def extract_domains(*texts: str | None) -> list[str]:
    out: list[str] = []
    for t in texts:
        if not t:
            continue
        for m in URL.finditer(t):
            host = re.sub(r"^(?:https?://)", "", m.group(0), flags=re.IGNORECASE).split("/")[0].split("?")[0].split(":")[0]
            d = registered_domain(host)
            if d:
                out.append(d)
        for m in BARE_DOMAIN.finditer(t):
            d = registered_domain(m.group(1))
            if d:
                out.append(d)
    seen: dict[str, None] = {}
    for d in out:
        seen.setdefault(d, None)
    return list(seen)


def extract_artifacts(*texts: str | None) -> list[Artifact]:
    arts: dict[tuple[str, str], Artifact] = {}
    for t in texts:
        if not t:
            continue
        for m in TELEGRAM.finditer(t):
            arts[("telegram", m.group(0).lower())] = Artifact(kind="telegram", value=m.group(0).lower())
        for m in WHATSAPP.finditer(t):
            arts[("whatsapp", m.group(0).lower())] = Artifact(kind="whatsapp", value=m.group(0).lower())
        for m in URL.finditer(t):
            u = m.group(0).rstrip(".,;")
            host = re.sub(r"^(?:https?://)", "", u, flags=re.IGNORECASE).split("/")[0].lower()
            kind = "shortlink" if host in SHORTENERS else "url"
            arts[(kind, u.lower())] = Artifact(kind=kind, value=u.lower())
        for sh in SHORTENERS:
            for m in re.finditer(r"(?<![\w.])" + re.escape(sh) + r"/[A-Za-z0-9_-]+", t, re.IGNORECASE):
                arts[("shortlink", m.group(0).lower())] = Artifact(kind="shortlink", value=m.group(0).lower())
        for m in PHONE.finditer(t):
            digits = re.sub(r"\D", "", m.group(0))
            if len(digits) in (9, 11):
                arts[("phone", digits[-9:])] = Artifact(kind="phone", value=digits[-9:])
    return list(arts.values())
