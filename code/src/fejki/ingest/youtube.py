"""YouTube Data API v3 commentThreads adapter (official API, quota). Author ids are hashed immediately."""
from __future__ import annotations

import hashlib
import hmac
from datetime import datetime

import httpx

from ..config import env
from ..process.extract import extract_artifacts
from ..schema import Comment


def hash_author(author_id: str, salt: str | None = None) -> str:
    salt = salt if salt is not None else env("HASH_SALT")
    return hmac.new(salt.encode(), author_id.encode(), hashlib.sha256).hexdigest()[:24]


def fetch_comments(video_id: str, max_results: int = 100) -> list[Comment]:
    key = env("YOUTUBE_API_KEY")
    if not key:
        raise RuntimeError("YOUTUBE_API_KEY not set")
    r = httpx.get("https://www.googleapis.com/youtube/v3/commentThreads", timeout=30,
                  params={"part": "snippet", "videoId": video_id, "maxResults": max_results, "key": key})
    r.raise_for_status()
    out = []
    for it in r.json().get("items", []):
        s = it["snippet"]["topLevelComment"]["snippet"]
        txt = s.get("textDisplay", "")
        out.append(Comment(comment_id=f"youtube:{it['id']}", ad_id=f"youtube:{video_id}", source="youtube",
                           author_hash=hash_author(s.get("authorChannelId", {}).get("value", s.get("authorDisplayName", ""))),
                           text=txt, ts=datetime.fromisoformat(s["publishedAt"].replace("Z", "+00:00")),
                           artifacts=extract_artifacts(txt)))
    return out
