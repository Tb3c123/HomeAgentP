"""Notification preferences persistence with audit logging (P05-F02)."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from homeagentp_core.config import Settings
from homeagentp_core.modules.notifications.schemas import (
    NotificationPreferencesOut,
    NotificationPreferencesUpdate,
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def mask_chat_id(chat_id: str) -> str:
    """Return a masked representation of a Telegram chat ID (never expose full ID in history)."""
    cleaned = chat_id.strip()
    if len(cleaned) <= 4:
        return "***"
    return f"***{cleaned[-4:]}"


def get_notification_preferences(
    conn: sqlite3.Connection,
    settings: Settings,
) -> NotificationPreferencesOut:
    row = conn.execute("SELECT * FROM notification_preferences WHERE id = 1").fetchone()
    dest_count = len([c for c in settings.telegram_allowed_chat_ids if c.strip()])
    tg_configured = bool(
        settings.telegram_enabled and settings.telegram_bot_token.strip() and dest_count > 0
    )
    if row is None:
        return NotificationPreferencesOut(
            telegram_enabled=False,
            min_severity="warning",
            notify_on_resolve=True,
            cooldown_seconds=900,
            rate_limit_count=10,
            rate_limit_window_seconds=300,
            destination_count=dest_count,
            telegram_configured=tg_configured,
            updated_by="system",
            updated_at="",
        )
    return NotificationPreferencesOut(
        telegram_enabled=bool(row["telegram_enabled"]),
        min_severity=row["min_severity"],
        notify_on_resolve=bool(row["notify_on_resolve"]),
        cooldown_seconds=int(row["cooldown_seconds"]),
        rate_limit_count=int(row["rate_limit_count"]),
        rate_limit_window_seconds=int(row["rate_limit_window_seconds"]),
        destination_count=dest_count,
        telegram_configured=tg_configured,
        updated_by=str(row["updated_by"]),
        updated_at=str(row["updated_at"]),
    )


def update_notification_preferences(
    conn: sqlite3.Connection,
    settings: Settings,
    *,
    payload: NotificationPreferencesUpdate,
    actor: str,
    ip_address: str,
) -> NotificationPreferencesOut:
    now_iso = _utc_now_iso()
    conn.execute(
        """
        INSERT INTO notification_preferences (
            id, telegram_enabled, min_severity, notify_on_resolve,
            cooldown_seconds, rate_limit_count, rate_limit_window_seconds,
            updated_by, updated_at
        )
        VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            telegram_enabled = excluded.telegram_enabled,
            min_severity = excluded.min_severity,
            notify_on_resolve = excluded.notify_on_resolve,
            cooldown_seconds = excluded.cooldown_seconds,
            rate_limit_count = excluded.rate_limit_count,
            rate_limit_window_seconds = excluded.rate_limit_window_seconds,
            updated_by = excluded.updated_by,
            updated_at = excluded.updated_at
        """,
        (
            1 if payload.telegram_enabled else 0,
            payload.min_severity,
            1 if payload.notify_on_resolve else 0,
            payload.cooldown_seconds,
            payload.rate_limit_count,
            payload.rate_limit_window_seconds,
            actor,
            now_iso,
        ),
    )
    conn.execute(
        """
        INSERT INTO audit_logs (
            actor, action, target_type, target_id, details_json, ip_address, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            actor,
            "notifications.preferences_updated",
            "notification_preferences",
            "1",
            json.dumps(
                {
                    "telegram_enabled": payload.telegram_enabled,
                    "min_severity": payload.min_severity,
                    "cooldown_seconds": payload.cooldown_seconds,
                },
                ensure_ascii=False,
            ),
            ip_address,
            now_iso,
        ),
    )
    return get_notification_preferences(conn, settings)
