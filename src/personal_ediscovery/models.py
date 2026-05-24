"""Pydantic models for personal-ediscovery."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Collection(BaseModel):
    name: str
    root: str
    adapter: str
    created_at: datetime = Field(default_factory=datetime.now)
    consent_token: str


class SourceItem(BaseModel):
    source_ref: str
    title: str | None = None
    modified_at: datetime | None = None
    body: str
    meta: dict[str, Any] = Field(default_factory=dict)


class Document(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    collection: str
    source_ref: str
    title: str | None = None
    modified_at: datetime | None = None
    body: str
    meta: dict[str, Any] = Field(default_factory=dict)


class Hit(BaseModel):
    id: UUID
    collection: str
    title: str | None
    snippet: str
    source_ref: str
    score: float
