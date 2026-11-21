"""Enrich an Ad: normalized text (infra-free), domains, artifacts, named entities."""
from __future__ import annotations

import re
from functools import lru_cache

from ..config import ROOT
from ..schema import Ad
from .extract import BARE_DOMAIN, URL, extract_artifacts, extract_domains, registered_domain
from .ner_gazetteer import find_entities, load_gazetteer
from .normalize import normalize


@lru_cache(maxsize=1)
def _gaz() -> tuple[str, ...]:
    p = ROOT / "config" / "gazetteer.txt"
    return tuple(load_gazetteer(p)) if p.exists() else ()


def strip_infra(text: str) -> str:
    t = URL.sub(" ", text)

    def sub(m):
        return " " if registered_domain(m.group(1)) else m.group(0)

    return BARE_DOMAIN.sub(sub, t)


def enrich(ad: Ad, cfg: dict) -> Ad:
    raw = ad.full_text()
    tcfg = cfg.get("text", {})
    ad.text_norm = normalize(strip_infra(raw), tcfg.get("normalize_lower", True), tcfg.get("strip_emoji", True))
    ad.text_norm = re.sub(r"\s+([.,!?:])", r"\1", ad.text_norm)
    ad.domains = extract_domains(ad.link_caption, ad.title, ad.body, ad.description)
    ad.artifacts = extract_artifacts(ad.body, ad.description, ad.link_caption)
    ad.named_entities = find_entities(raw, list(_gaz()))
    return ad
