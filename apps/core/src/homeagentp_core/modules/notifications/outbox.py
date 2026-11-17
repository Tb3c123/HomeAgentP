"""Durable SQLite notification outbox: atomic claim, lease recovery, overflow, and retention."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

from homeagentp_core.logging import redact_text
from homeagentp_core.modules.notifications.schemas import (
    DeliveryStatus,
    NotificationDeliveryOut,
    NotificationSeverity,
    SourceDomain,
)

MAX_OUTBOX_MESSAGE_CHARS = 2000


def _utc_now(now: datetime | None = None) -> datetime:
    return now if now is not None else datetime.now(UTC)


def _row_to_delivery(row: sqlite3.Row) -> NotificationDeliveryOut:
    return NotificationDeliveryOut(
        id=int(row["id"]),
        incident_key=str(row["incident_key"]),
        source_domain=row["source_domain"],
        severity=row["severity"],
        channel=row["channel"],
        destination_masked=str(row["destination_masked"]),
        message_redacted=str(row["message_redacted"]),
        status=row["status"],
        claimed_by=str(row["claimed_by"]),
        lease_expires_at=row["lease_expires_at"],
        attempt_count=int(row["attempt_count"]),
        next_attempt_at=row["next_attempt_at"],
        last_error_redacted=str(row["last_error_redacted"]),
        created_at=str(row["created_at"]),
        sent_at=row["sent_at"],
    )


def enqueue_notification(
    conn: sqlite3.Connection,
    *,
    incident_key: str,
    source_domain: SourceDomain,
    severity: NotificationSeverity,
    destination_masked: str,
    message: str,
    cooldown_seconds: int = 900,
    max_active: int = 100,
    now: datetime | None = None,
) -> NotificationDeliveryOut:
    """Enqueue a redacted notification with cooldown suppression and bounded overflow handling."""
    cleaned_dest = destination_masked.strip()
    if not cleaned_dest or cleaned_dest == "not_configured":
        raise ValueError(
            "Cannot enqueue deliverable notification without an authorized destination."
        )

    current = _utc_now(now)
    now_iso = current.isoformat()
    safe_message = redact_text(message.strip())[:MAX_OUTBOX_MESSAGE_CHARS]
    status: DeliveryStatus = "pending"

    started_tx = False
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
        started_tx = True

    try:
        # 1. Duplicate suppression: active pending/in_flight/failed OR sent within cooldown window
        cooldown_cutoff = (current - timedelta(seconds=cooldown_seconds)).isoformat()
        dup_row = conn.execute(
            """
            SELECT id FROM notification_deliveries
            WHERE incident_key = ?
              AND destination_masked = ?
              AND (
                  status IN ('pending', 'in_flight', 'failed')
                  OR (status = 'sent' AND COALESCE(sent_at, created_at) >= ?)
              )
            ORDER BY id DESC LIMIT 1
            """,
            (incident_key, cleaned_dest, cooldown_cutoff),
        ).fetchone()
        if dup_row is not None:
            status = "suppressed_cooldown"

        # 2. Bounded queue & overflow policy
        if status == "pending":
            active_count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM notification_deliveries "
                    "WHERE status IN ('pending', 'in_flight')"
                ).fetchone()[0]
            )
            if active_count >= max_active:
                if severity == "critical":
                    evict = conn.execute(
                        """
                        SELECT id FROM notification_deliveries
                        WHERE status = 'pending' AND severity IN ('info', 'warning')
                        ORDER BY CASE severity WHEN 'info' THEN 0 ELSE 1 END, id ASC
                        LIMIT 1
                        """
                    ).fetchone()
                    if evict is not None:
                        conn.execute(
                            """
                            UPDATE notification_deliveries
                            SET status = 'suppressed_overflow',
                                last_error_redacted = 'evicted_for_critical_alert'
                            WHERE id = ?
                            """,
                            (int(evict["id"]),),
                        )
                    else:
                        status = "suppressed_overflow"
                else:
                    status = "suppressed_overflow"

        try:
            cur = conn.execute(
                """
                INSERT INTO notification_deliveries (
                    incident_key, source_domain, severity, channel, destination_masked,
                    message_redacted, status, claimed_by, lease_expires_at,
                    attempt_count, next_attempt_at, last_error_redacted, created_at, sent_at
                )
                VALUES (?, ?, ?, 'telegram', ?, ?, ?, '', NULL, 0, ?, '', ?, NULL)
                """,
                (
                    incident_key,
                    source_domain,
                    severity,
                    cleaned_dest,
                    safe_message,
                    status,
                    now_iso if status == "pending" else None,
                    now_iso,
                ),
            )
        except sqlite3.IntegrityError:
            status = "suppressed_cooldown"
            cur = conn.execute(
                """
                INSERT INTO notification_deliveries (
                    incident_key, source_domain, severity, channel, destination_masked,
                    message_redacted, status, claimed_by, lease_expires_at,
                    attempt_count, next_attempt_at, last_error_redacted, created_at, sent_at
                )
                VALUES (
                    ?, ?, ?, 'telegram', ?, ?, 'suppressed_cooldown', '', NULL, 0, NULL, '', ?, NULL
                )
                """,
                (
                    incident_key,
                    source_domain,
                    severity,
                    cleaned_dest,
                    safe_message,
                    now_iso,
                ),
            )

        row = conn.execute(
            "SELECT * FROM notification_deliveries WHERE id = ?",
            (int(cur.lastrowid or 0),),
        ).fetchone()
        if started_tx:
            conn.commit()
    except Exception:
        if started_tx:
            conn.rollback()
        raise

    assert row is not None
    return _row_to_delivery(row)


def recover_expired_leases(
    conn: sqlite3.Connection,
    *,
    max_attempts: int = 3,
    now: datetime | None = None,
) -> int:
    """Reclaim expired in-flight deliveries back to failed or dead_letter."""
    now_iso = _utc_now(now).isoformat()
    dead_cur = conn.execute(
        """
        UPDATE notification_deliveries
        SET status = 'dead_letter',
            claimed_by = '',
            lease_expires_at = NULL,
            last_error_redacted = 'lease_expired_max_attempts'
        WHERE status = 'in_flight'
          AND lease_expires_at IS NOT NULL
          AND lease_expires_at <= ?
          AND attempt_count >= ?
        """,
        (now_iso, max_attempts),
    )
    retry_cur = conn.execute(
        """
        UPDATE notification_deliveries
        SET status = 'failed',
            claimed_by = '',
            lease_expires_at = NULL,
            next_attempt_at = ?,
            last_error_redacted = 'lease_expired_recovered'
        WHERE status = 'in_flight'
          AND lease_expires_at IS NOT NULL
          AND lease_expires_at <= ?
          AND attempt_count < ?
        """,
        (now_iso, now_iso, max_attempts),
    )
    return int(dead_cur.rowcount + retry_cur.rowcount)


def claim_next_delivery(
    conn: sqlite3.Connection,
    *,
    worker_id: str,
    lease_seconds: int = 60,
    max_attempts: int = 3,
    now: datetime | None = None,
) -> NotificationDeliveryOut | None:
    """Atomically claim the highest-priority due delivery with a lease timeout."""
    current = _utc_now(now)
    now_iso = current.isoformat()
    lease_iso = (current + timedelta(seconds=lease_seconds)).isoformat()

    started_tx = False
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
        started_tx = True

    try:
        recover_expired_leases(conn, max_attempts=max_attempts, now=current)
        row = conn.execute(
            """
            UPDATE notification_deliveries
            SET status = 'in_flight',
                claimed_by = ?,
                lease_expires_at = ?,
                attempt_count = attempt_count + 1
            WHERE id = (
                SELECT id FROM notification_deliveries
                WHERE status IN ('pending', 'failed')
                  AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                ORDER BY
                    CASE severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END,
                    id ASC
                LIMIT 1
            )
            RETURNING *
            """,
            (worker_id, lease_iso, now_iso),
        ).fetchone()
        if started_tx:
            conn.commit()
    except Exception:
        if started_tx:
            conn.rollback()
        raise

    return _row_to_delivery(row) if row is not None else None


def complete_delivery(
    conn: sqlite3.Connection,
    delivery_id: int,
    *,
    worker_id: str,
    now: datetime | None = None,
) -> bool:
    """Mark an in-flight delivery as sent if still owned by worker_id."""
    now_iso = _utc_now(now).isoformat()
    cur = conn.execute(
        """
        UPDATE notification_deliveries
        SET status = 'sent',
            claimed_by = '',
            lease_expires_at = NULL,
            sent_at = ?,
            last_error_redacted = ''
        WHERE id = ? AND status = 'in_flight' AND claimed_by = ?
        """,
        (now_iso, delivery_id, worker_id),
    )
    return cur.rowcount > 0


def fail_delivery(
    conn: sqlite3.Connection,
    delivery_id: int,
    *,
    worker_id: str,
    error_message: str,
    retry_delay_seconds: int = 15,
    max_attempts: int = 3,
    permanent: bool = False,
    now: datetime | None = None,
) -> bool:
    """Transition an in-flight delivery to failed (for retry) or dead_letter."""
    current = _utc_now(now)
    next_iso = (current + timedelta(seconds=retry_delay_seconds)).isoformat()
    safe_err = redact_text(error_message)[:300]

    row = conn.execute(
        "SELECT attempt_count FROM notification_deliveries "
        "WHERE id = ? AND status = 'in_flight' AND claimed_by = ?",
        (delivery_id, worker_id),
    ).fetchone()
    if row is None:
        return False

    exhausted = permanent or int(row["attempt_count"]) >= max_attempts
    next_status: DeliveryStatus = "dead_letter" if exhausted else "failed"
    cur = conn.execute(
        """
        UPDATE notification_deliveries
        SET status = ?,
            claimed_by = '',
            lease_expires_at = NULL,
            next_attempt_at = ?,
            last_error_redacted = ?
        WHERE id = ? AND status = 'in_flight' AND claimed_by = ?
        """,
        (
            next_status,
            None if exhausted else next_iso,
            safe_err,
            delivery_id,
            worker_id,
        ),
    )
    return cur.rowcount > 0


def prune_terminal_deliveries(
    conn: sqlite3.Connection,
    *,
    retention_limit: int = 500,
) -> int:
    """Prune old terminal delivery rows only; NEVER prune pending or in_flight deliveries."""
    cur = conn.execute(
        """
        DELETE FROM notification_deliveries
        WHERE status NOT IN ('pending', 'in_flight')
          AND id NOT IN (
              SELECT id FROM notification_deliveries
              WHERE status NOT IN ('pending', 'in_flight')
              ORDER BY id DESC
              LIMIT ?
          )
        """,
        (retention_limit,),
    )
    return int(cur.rowcount)


def list_deliveries(
    conn: sqlite3.Connection,
    *,
    limit: int = 50,
    offset: int = 0,
    status: DeliveryStatus | None = None,
) -> list[NotificationDeliveryOut]:
    rows = conn.execute(
        """
        SELECT * FROM notification_deliveries
        WHERE (? IS NULL OR status = ?)
        ORDER BY id DESC
        LIMIT ? OFFSET ?
        """,
        (status, status, limit, offset),
    ).fetchall()
    return [_row_to_delivery(r) for r in rows]
