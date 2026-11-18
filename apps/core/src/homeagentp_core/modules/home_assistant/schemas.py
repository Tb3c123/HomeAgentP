"""Pydantic schemas for Phase 05 read-only Home Assistant monitoring."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

HaStatus = Literal["online", "stale", "unavailable", "degraded"]


class HaEntityStateOut(BaseModel):
    entity_id: str
    domain: str
    friendly_name: str
    state: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    status: Literal["online", "stale", "unavailable"]
    last_changed: str | None = None
    collected_at: str


class HaOverviewResponse(BaseModel):
    status: HaStatus
    enabled: bool
    reason: str
    collected_at: str | None = None
    entity_count: int = 0
    entities: list[HaEntityStateOut] = Field(default_factory=list)
    read_only_enforced: bool = True
