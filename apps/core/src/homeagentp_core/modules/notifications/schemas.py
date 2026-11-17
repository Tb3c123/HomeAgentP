"""Pydantic schemas for Phase 05 notification preferences and durable outbox."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

NotificationSeverity = Literal["info", "warning", "critical"]
DeliveryStatus = Literal[
    "pending",
    "in_flight",
    "sent",
    "suppressed_cooldown",
    "suppressed_rate_limit",
    "suppressed_overflow",
    "failed",
    "dead_letter",
]
SourceDomain = Literal["nas", "media", "home_assistant", "system"]


class NotificationPreferencesOut(BaseModel):
    telegram_enabled: bool
    min_severity: NotificationSeverity
    notify_on_resolve: bool
    cooldown_seconds: int
    rate_limit_count: int
    rate_limit_window_seconds: int
    destination_count: int = 0
    telegram_configured: bool = False
    updated_by: str
    updated_at: str


class NotificationPreferencesUpdate(BaseModel):
    telegram_enabled: bool
    min_severity: NotificationSeverity = "warning"
    notify_on_resolve: bool = True
    cooldown_seconds: int = Field(default=900, ge=0, le=86400)
    rate_limit_count: int = Field(default=10, ge=1, le=200)
    rate_limit_window_seconds: int = Field(default=300, ge=10, le=86400)


class NotificationDeliveryOut(BaseModel):
    id: int
    incident_key: str
    source_domain: SourceDomain
    severity: NotificationSeverity
    channel: Literal["telegram"]
    destination_masked: str
    message_redacted: str
    status: DeliveryStatus
    claimed_by: str
    lease_expires_at: str | None = None
    attempt_count: int
    next_attempt_at: str | None = None
    last_error_redacted: str
    created_at: str
    sent_at: str | None = None


class NotificationEvaluateOut(BaseModel):
    enqueued: int
    suppressed_cooldown: int
    suppressed_overflow: int
