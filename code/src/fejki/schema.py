"""Pydantic schemas: one `Ad` schema for all sources (real, synthetic, file)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Source = Literal["meta", "google", "synthetic_campaign", "synthetic_control", "synthetic_background", "file"]


class Artifact(BaseModel):
    kind: Literal["phone", "telegram", "whatsapp", "shortlink", "url"]
    value: str


class Ad(BaseModel):
    ad_id: str
    source: Source
    first_seen_at: datetime
    delivery_start: datetime | None = None
    delivery_stop: datetime | None = None
    page_id: str | None = None
    page_name: str | None = None
    body: str = ""
    title: str | None = None
    description: str | None = None
    link_caption: str | None = None
    lang: str | None = None
    text_norm: str = ""
    domains: list[str] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    named_entities: list[str] = Field(default_factory=list)
    removed_after_seen: bool = False
    truth_campaign: str | None = None
    truth_topic: str | None = None
    truth_template: str | None = None
    meta: dict = Field(default_factory=dict)

    def full_text(self) -> str:
        return " ".join(x for x in [self.title, self.body, self.description] if x)

    @property
    def t(self) -> datetime:
        return self.delivery_start or self.first_seen_at


class Comment(BaseModel):
    comment_id: str
    ad_id: str | None = None
    source: Literal["synthetic", "youtube", "file"]
    author_hash: str
    text: str
    ts: datetime
    artifacts: list[Artifact] = Field(default_factory=list)
    truth_campaign: str | None = None


class CampaignSpec(BaseModel):
    campaign_id: str
    template_id: str
    schema_moves: list[str]
    topics: list[str]
    names: list[str]
    n_variants: int
    paraphrase_level: Literal[0, 1, 2]
    domains: list[str]
    advertisers: list[str]
    start: datetime
    burst_profile: Literal["spike", "ramp", "pulse"]
    cloaking_decoys: int = 0
    split: Literal["dev", "test"] = "test"
