"""Typed records returned by the store."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from circuits_llm.domain import Circuit, Issue

VersionSource = Literal["llm", "manual", "restore"]


class _Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProjectRecord(_Record):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    latest_version: int | None = None


class MessageMeta(_Record):
    endpoint_id: str | None = None
    model: str | None = None
    error: bool = False
    warnings: list[Issue] = Field(default_factory=list[Issue])


class MessageRecord(_Record):
    id: int
    role: Literal["user", "assistant"]
    content: str
    version_number: int | None = None
    meta: MessageMeta = MessageMeta()
    created_at: datetime


class VersionSummary(_Record):
    number: int
    source: VersionSource
    title: str
    created_at: datetime


class VersionRecord(_Record):
    project_id: str
    number: int
    source: VersionSource
    circuit: Circuit
    created_at: datetime
