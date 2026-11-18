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
    NotificationPreferencesOut,
    NotificationSeverity,
    SourceDomain,
)

SEVERITY_RANK: dict[str, int] = {"info": 0, "warning": 1, "critical": 2}


def build_incident_key(source_domain: SourceDomain, alert_key: str, event_type: str) -> str:
    """Build deterministic incident identity for deduplication and cooldown suppression."""
    return f"{source_domain}:{alert_key}:{event_type}"


def build_incident_base_key(source_domain: SourceDomain, alert_key: str) -> str:
    """Build durable base key for triggered/resolved transition tracking."""
    return f"{source_domain}:{alert_key}"


def is_telegram_channel_ready(
    settings: Settings,
    prefs: NotificationPreferencesOut,
) -> tuple[bool, list[str]]:
    """Return whether Telegram is enabled in both runtime & prefs and has a valid destination."""
    chat_ids = [c.strip() for c in settings.telegram_allowed_chat_ids if c.strip()]
    ready = bool(
        settings.telegram_enabled
        and prefs.telegram_enabled
        and settings.telegram_bot_token.strip()
        and chat_ids
    )
    return ready, chat_ids


def _severity_meets_threshold(severity: str, min_severity: str) -> bool:
    return SEVERITY_RANK.get(severity, 0) >= SEVERITY_RANK.get(min_severity, 1)


def _record_triggered_transition(
    conn: sqlite3.Connection,
    incident_base_key: str,
    now_iso: str,
) -> int:
    """Ensure incident state is 'triggered' and return the durable transition sequence."""
    row = conn.execute(
        "SELECT last_state, transition_seq FROM notification_incident_states "
        "WHERE incident_base_key = ?",
        (incident_base_key,),
    ).fetchone()
    if row is None:
        conn.execute(
            """
            INSERT INTO notification_incident_states (
                incident_base_key, last_state, transition_seq, last_transition_at, resolved_notified
            )
            VALUES (?, 'triggered', 1, ?, 0)
            """,
            (incident_base_key, now_iso),
        )
        return 1
    seq = int(row["transition_seq"])
    if row["last_state"] == "resolved":
        seq += 1
        conn.execute(
            """
            UPDATE notification_incident_states
            SET last_state = 'triggered',
                transition_seq = ?,
                last_transition_at = ?,
                resolved_notified = 0
            WHERE incident_base_key = ?
            """,
            (seq, now_iso, incident_base_key),
        )
    return seq


def _consume_resolved_transition(
    conn: sqlite3.Connection,
    incident_base_key: str,
    *,
    notify_on_resolve: bool,
    now_iso: str,
) -> int | None:
    """Transition a previously triggered incident to 'resolved'.

    Returns the transition_seq if a resolved notification should be emitted, else None.
    """
    row = conn.execute(
        "SELECT last_state, transition_seq FROM notification_incident_states "
        "WHERE incident_base_key = ?",
        (incident_base_key,),
    ).fetchone()
    if row is None or row["last_state"] != "triggered":
        return None

    seq = int(row["transition_seq"])
    conn.execute(
        """
        UPDATE notification_incident_states
        SET last_state = 'resolved',
            last_transition_at = ?,
            resolved_notified = ?
        WHERE incident_base_key = ?
        """,
        (now_iso, 1 if notify_on_resolve else 0, incident_base_key),
    )
    return seq if notify_on_resolve else None


def evaluate_alerts_to_outbox(
    conn: sqlite3.Connection,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> NotificationEvaluateOut:
    """Evaluate NAS, Media, and HA alerts against preferences and enqueue into outbox."""
    current = now if now is not None else datetime.now(UTC)
    now_iso = current.isoformat()
    prefs = get_notification_preferences(conn, settings)
    ready, chat_ids = is_telegram_channel_ready(settings, prefs)

    active_candidates: list[tuple[SourceDomain, str, NotificationSeverity, str]] = []
    resolved_candidates: list[tuple[SourceDomain, str, str]] = []

    for row in conn.execute(
        "SELECT alert_key, severity, message, status FROM nas_alerts ORDER BY id ASC"
    ).fetchall():
        if row["status"] == "active":
            active_candidates.append(
                (
                    "nas",
                    str(row["alert_key"]),
                    row["severity"],
                    f"[NAS {str(row['severity']).upper()}] {row['message']}",
                )
            )
        elif row["status"] == "resolved":
            resolved_candidates.append(
                ("nas", str(row["alert_key"]), f"[NAS RESOLVED] {row['message']}")
            )

    for row in conn.execute(
        "SELECT alert_key, severity, service, message, status FROM media_alerts ORDER BY id ASC"
    ).fetchall():
        if row["status"] == "active":
            active_candidates.append(
                (
                    "media",
                    str(row["alert_key"]),
                    row["severity"],
                    f"[Media:{row['service']} {str(row['severity']).upper()}] {row['message']}",
                )
            )
        elif row["status"] == "resolved":
            resolved_candidates.append(
                (
                    "media",
                    str(row["alert_key"]),
                    f"[Media:{row['service']} RESOLVED] {row['message']}",
                )
            )

    if settings.ha_enabled:
        for row in conn.execute(
            "SELECT entity_id, friendly_name, status FROM ha_entity_states ORDER BY entity_id ASC"
        ).fetchall():
            entity_key = f"ha:{row['entity_id']}"
            if row["status"] in ("unavailable", "stale"):
                active_candidates.append(
                    (
                        "home_assistant",
                        entity_key,
                        "warning",
                        f"[Home Assistant WARNING] {row['friendly_name']} "
                        f"({row['entity_id']}) is {row['status']}.",
                    )
                )
            elif row["status"] == "online":
                resolved_candidates.append(
                    (
                        "home_assistant",
                        entity_key,
                        f"[Home Assistant RESOLVED] {row['friendly_name']} "
                        f"({row['entity_id']}) is back online.",
                    )
                )

    if not ready:
        return NotificationEvaluateOut(
            enqueued=0,
            suppressed_cooldown=0,
            suppressed_overflow=0,
            skipped_disabled=len(active_candidates),
        )

    dest_masked = mask_chat_id(chat_ids[0])
    enqueued = 0
    suppressed_cooldown = 0
    suppressed_overflow = 0

    for source_domain, alert_key, severity, msg in active_candidates:
        if not _severity_meets_threshold(severity, prefs.min_severity):
            continue
        base_key = build_incident_base_key(source_domain, alert_key)
        seq = _record_triggered_transition(conn, base_key, now_iso)
        incident_key = build_incident_key(source_domain, alert_key, f"t{seq}:triggered")
        delivery = enqueue_notification(
            conn,
            incident_key=incident_key,
            source_domain=source_domain,
            severity=severity,
            destination_masked=dest_masked,
            message=msg,
            cooldown_seconds=prefs.cooldown_seconds,
            max_active=settings.notification_outbox_max_active,
            now=current,
        )
        if delivery.status == "pending":
            enqueued += 1
        elif delivery.status == "suppressed_cooldown":
            suppressed_cooldown += 1
        elif delivery.status == "suppressed_overflow":
            suppressed_overflow += 1

    for source_domain, alert_key, msg in resolved_candidates:
        base_key = build_incident_base_key(source_domain, alert_key)
        resolved_seq = _consume_resolved_transition(
            conn,
            base_key,
            notify_on_resolve=prefs.notify_on_resolve,
            now_iso=now_iso,
        )
        if resolved_seq is None:
            continue
        incident_key = build_incident_key(source_domain, alert_key, f"t{resolved_seq}:resolved")
        delivery = enqueue_notification(
            conn,
            incident_key=incident_key,
            source_domain=source_domain,
            severity="info",
            destination_masked=dest_masked,
            message=msg,
            cooldown_seconds=prefs.cooldown_seconds,
            max_active=settings.notification_outbox_max_active,
            now=current,
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
        skipped_disabled=0,
    )
