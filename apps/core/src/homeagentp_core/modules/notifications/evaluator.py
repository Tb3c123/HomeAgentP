"""Alert evaluation bridge reading NAS, Media, and HA alerts into the durable outbox (P05-F02)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from homeagentp_core.config import Settings
from homeagentp_core.modules.notifications.outbox import (
    enqueue_notification,
    prune_terminal_deliveries,
)
from homeagentp_core.modules.notifications.preferences import (
    get_notification_preferences,
    mask_chat_id,
)
from homeagentp_core.modules.notifications.schemas import (
    NotificationEvaluateOut,
    NotificationSeverity,
    SourceDomain,
)

SEVERITY_RANK: dict[str, int] = {"info": 0, "warning": 1, "critical": 2}


def build_incident_key(source_domain: SourceDomain, alert_key: str, event_type: str) -> str:
    """Build deterministic incident identity for deduplication and cooldown suppression."""
    return f"{source_domain}:{alert_key}:{event_type}"


def _severity_meets_threshold(severity: str, min_severity: str) -> bool:
    return SEVERITY_RANK.get(severity, 0) >= SEVERITY_RANK.get(min_severity, 1)


def evaluate_alerts_to_outbox(
    conn: sqlite3.Connection,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> NotificationEvaluateOut:
    """Evaluate active NAS, Media, and HA alerts against preferences and enqueue into outbox."""
    prefs = get_notification_preferences(conn, settings)
    chat_ids = [c.strip() for c in settings.telegram_allowed_chat_ids if c.strip()]
    dest_masked = mask_chat_id(chat_ids[0]) if chat_ids else "not_configured"

    candidates: list[tuple[SourceDomain, str, NotificationSeverity, str, str]] = []

    for row in conn.execute(
        "SELECT alert_key, severity, message, status "
        "FROM nas_alerts WHERE status = 'active' ORDER BY id ASC"
    ).fetchall():
        candidates.append(
            (
                "nas",
                str(row["alert_key"]),
                row["severity"],
                "triggered",
                f"[NAS {str(row['severity']).upper()}] {row['message']}",
            )
        )

    for row in conn.execute(
        "SELECT alert_key, severity, service, message, status "
        "FROM media_alerts WHERE status = 'active' ORDER BY id ASC"
    ).fetchall():
        candidates.append(
            (
                "media",
                str(row["alert_key"]),
                row["severity"],
                "triggered",
                f"[Media:{row['service']} {str(row['severity']).upper()}] {row['message']}",
            )
        )

    if settings.ha_enabled:
        for row in conn.execute(
            "SELECT entity_id, friendly_name, status "
            "FROM ha_entity_states WHERE status IN ('unavailable', 'stale') ORDER BY entity_id ASC"
        ).fetchall():
            candidates.append(
                (
                    "home_assistant",
                    f"ha:{row['entity_id']}:{row['status']}",
                    "warning",
                    "triggered",
                    f"[Home Assistant WARNING] {row['friendly_name']} "
                    f"({row['entity_id']}) is {row['status']}.",
                )
            )

    enqueued = 0
    suppressed_cooldown = 0
    suppressed_overflow = 0

    for source_domain, alert_key, severity, event_type, msg in candidates:
        if not _severity_meets_threshold(severity, prefs.min_severity):
            continue
        incident_key = build_incident_key(source_domain, alert_key, event_type)
        delivery = enqueue_notification(
            conn,
            incident_key=incident_key,
            source_domain=source_domain,
            severity=severity,
            destination_masked=dest_masked,
            message=msg,
            cooldown_seconds=prefs.cooldown_seconds,
            max_active=settings.notification_outbox_max_active,
            now=now or datetime.now(UTC),
        )
        if delivery.status == "pending":
            enqueued += 1
        elif delivery.status == "suppressed_cooldown":
            suppressed_cooldown += 1
        elif delivery.status == "suppressed_overflow":
            suppressed_overflow += 1

    prune_terminal_deliveries(conn, retention_limit=settings.notification_history_retention_limit)
    return NotificationEvaluateOut(
        enqueued=enqueued,
        suppressed_cooldown=suppressed_cooldown,
        suppressed_overflow=suppressed_overflow,
    )
