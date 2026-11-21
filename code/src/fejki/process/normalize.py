"""Text normalization."""
from __future__ import annotations

import re
import unicodedata

_EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF\U0000FE0F\U0000200D\U00002B00-\U00002BFF]+"
)
_URL = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_WS = re.compile(r"\s+")


def normalize(text: str, lower: bool = True, strip_emoji: bool = True, drop_urls: bool = False) -> str:
    t = unicodedata.normalize("NFKC", text or "")
    if strip_emoji:
        t = _EMOJI.sub(" ", t)
    if drop_urls:
        t = _URL.sub(" ", t)
    if lower:
        t = t.lower()
    return _WS.sub(" ", t).strip()


def comment_key(text: str) -> str:
    """Aggressive normalization for comment dedup: lowercase, no emoji, no punctuation."""
    t = normalize(text)
    t = re.sub(r"[^\w\s]", "", t)
    return _WS.sub(" ", t).strip()
