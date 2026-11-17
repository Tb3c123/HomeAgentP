"""Background notification evaluation & Telegram delivery worker scheduler (P05-F04)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from homeagentp_core.config import Settings
from homeagentp_core.db.connection import db_session
from homeagentp_core.modules.notifications.evaluator import (
    evaluate_alerts_to_outbox,
    is_telegram_channel_ready,
)
from homeagentp_core.modules.notifications.outbox import (
    claim_next_delivery,
    complete_delivery,
    defer_due_non_critical_deliveries,
    fail_delivery,
    prune_terminal_deliveries,
    recover_expired_leases,
)
from homeagentp_core.modules.notifications.preferences import get_notification_preferences
from homeagentp_core.modules.notifications.schemas import NotificationDeliveryOut
from homeagentp_core.modules.notifications.telegram import (
    TelegramConfigError,
    TelegramOutboundSender,
    validate_telegram_chat_id,
)
from homeagentp_core.scheduler import HardenedPeriodicScheduler

MAX_DELIVERY_BATCH_PER_CYCLE = 10


def _compute_window_reset_at(
    oldest_sent_iso: str | None,
    *,
    current: datetime,
    window_seconds: int,
) -> datetime:
    max_reset = current + timedelta(seconds=max(5, window_seconds))
    min_reset = current + timedelta(seconds=5)
    if oldest_sent_iso:
        try:
            oldest_dt = datetime.fromisoformat(oldest_sent_iso)
            if oldest_dt.tzinfo is None:
                oldest_dt = oldest_dt.replace(tzinfo=UTC)
            candidate = oldest_dt + timedelta(seconds=window_seconds + 1)
            return max(min_reset, min(candidate, max_reset))
        except ValueError:
            pass
    return max_reset


def _claim_step(
    conn: sqlite3.Connection,
    *,
    settings: Settings,
    worker_id: str,
    rate_limit_count: int,
    rate_limit_window_seconds: int,
    current: datetime,
) -> tuple[NotificationDeliveryOut | None, int]:
    """Check sliding-window rate limit, defer non-critical if full, and claim next due delivery.

    Critical notifications bypass the non-critical rate limit so they are never silently dropped.
    """
    window_cutoff = (current - timedelta(seconds=rate_limit_window_seconds)).isoformat()
    stat_row = conn.execute(
        "SELECT COUNT(*) AS cnt, MIN(sent_at) AS oldest_sent_at "
        "FROM notification_deliveries "
        "WHERE status = 'sent' AND sent_at >= ?",
        (window_cutoff,),
    ).fetchone()
    sent_in_window = int(stat_row["cnt"]) if stat_row is not None else 0
    is_rate_limited = sent_in_window >= rate_limit_count

    deferred = 0
    if is_rate_limited:
        reset_at = _compute_window_reset_at(
            stat_row["oldest_sent_at"] if stat_row is not None else None,
            current=current,
            window_seconds=rate_limit_window_seconds,
        )
        deferred = defer_due_non_critical_deliveries(
            conn,
            next_attempt_at=reset_at,
            now=current,
        )

    delivery = claim_next_delivery(
        conn,
        worker_id=worker_id,
        lease_seconds=settings.notification_lease_seconds,
        max_attempts=settings.notification_max_attempts,
        critical_only=is_rate_limited,
        now=current,
    )
    return delivery, deferred


def run_notification_outbox_cycle(
    db_path: Path,
    settings: Settings,
    *,
    sender: TelegramOutboundSender | None = None,
    worker_id: str = "notif-worker",
    max_batch: int = MAX_DELIVERY_BATCH_PER_CYCLE,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Execute one outbox cycle using short committed SQLite transactions.

    Guarantees ZERO open SQLite write transactions during outbound Telegram HTTP I/O.
    """
    current = now if now is not None else datetime.now(UTC)

    # Tx 1: Evaluate alerts, recover expired leases, read preferences & validate destination
    with db_session(db_path) as conn:
        eval_res = evaluate_alerts_to_outbox(conn, settings, now=current)
        recovered = recover_expired_leases(
            conn,
            max_attempts=settings.notification_max_attempts,
            now=current,
        )
        prefs = get_notification_preferences(conn, settings)

    ready, chat_ids = is_telegram_channel_ready(settings, prefs)
    if not ready or len(chat_ids) != 1:
        return {
            "status": "disabled",
            "enqueued": eval_res.enqueued,
            "recovered": recovered,
            "sent": 0,
            "failed": 0,
            "dead_letter": 0,
            "rate_limited": 0,
        }

    try:
        target_chat_id = validate_telegram_chat_id(chat_ids[0], chat_ids)
    except TelegramConfigError:
        return {
            "status": "disabled",
            "enqueued": eval_res.enqueued,
            "recovered": recovered,
            "sent": 0,
            "failed": 0,
            "dead_letter": 0,
            "rate_limited": 0,
        }

    active_sender = (
        sender if sender is not None else TelegramOutboundSender.from_settings(settings)
    )
    sent = 0
    failed = 0
    dead_letter = 0
    rate_limited = 0

    for _ in range(max(1, max_batch)):
        # Tx 2: Short committed claim transaction
        with db_session(db_path) as conn:
            delivery, was_rate_limited = _claim_step(
                conn,
                settings=settings,
                worker_id=worker_id,
                rate_limit_count=prefs.rate_limit_count,
                rate_limit_window_seconds=prefs.rate_limit_window_seconds,
                current=current,
            )

        if delivery is None:
            break
        if was_rate_limited:
            rate_limited += 1
            continue

        # Outbound HTTP I/O happens with NO open SQLite connection or write transaction
        result = active_sender.send_message(
            chat_id=target_chat_id,
            text=delivery.message_redacted,
        )

        # Tx 3: Short committed completion/failure transaction
        with db_session(db_path) as conn:
            if result.ok:
                complete_delivery(conn, delivery.id, worker_id=worker_id, now=current)
                sent += 1
            else:
                delay = (
                    result.retry_after_seconds
                    if result.retry_after_seconds is not None
                    else min(300, 15 * (2 ** max(0, delivery.attempt_count - 1)))
                )
                exhausted = result.permanent or (
                    delivery.attempt_count >= settings.notification_max_attempts
                )
                fail_delivery(
                    conn,
                    delivery.id,
                    worker_id=worker_id,
                    error_message=result.error_message,
                    retry_delay_seconds=delay,
                    max_attempts=settings.notification_max_attempts,
                    permanent=result.permanent,
                    now=current,
                )
                if exhausted:
                    dead_letter += 1
                else:
                    failed += 1

    # Tx 4: Short committed terminal retention pruning
    with db_session(db_path) as conn:
        prune_terminal_deliveries(
            conn, retention_limit=settings.notification_history_retention_limit
        )

    return {
        "status": "ok" if failed == 0 and dead_letter == 0 else "degraded",
        "enqueued": eval_res.enqueued,
        "recovered": recovered,
        "sent": sent,
        "failed": failed,
        "dead_letter": dead_letter,
        "rate_limited": rate_limited,
    }


def process_notification_outbox_cycle(
    conn: sqlite3.Connection,
    settings: Settings,
    *,
    sender: TelegramOutboundSender | None = None,
    worker_id: str = "notif-worker",
    max_batch: int = MAX_DELIVERY_BATCH_PER_CYCLE,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Evaluate alerts, recover expired leases, and send a bounded batch using short commits."""
    current = now if now is not None else datetime.now(UTC)
    eval_res = evaluate_alerts_to_outbox(conn, settings, now=current)
    recovered = recover_expired_leases(
        conn,
        max_attempts=settings.notification_max_attempts,
        now=current,
    )
    prefs = get_notification_preferences(conn, settings)
    conn.commit()

    ready, chat_ids = is_telegram_channel_ready(settings, prefs)
    if not ready or len(chat_ids) != 1:
        return {
            "status": "disabled",
            "enqueued": eval_res.enqueued,
            "recovered": recovered,
            "sent": 0,
            "failed": 0,
            "dead_letter": 0,
            "rate_limited": 0,
        }

    try:
        target_chat_id = validate_telegram_chat_id(chat_ids[0], chat_ids)
    except TelegramConfigError:
        return {
            "status": "disabled",
            "enqueued": eval_res.enqueued,
            "recovered": recovered,
            "sent": 0,
            "failed": 0,
            "dead_letter": 0,
            "rate_limited": 0,
        }

    active_sender = (
        sender if sender is not None else TelegramOutboundSender.from_settings(settings)
    )
    sent = 0
    failed = 0
    dead_letter = 0
    rate_limited = 0

    for _ in range(max(1, max_batch)):
        delivery, deferred_now = _claim_step(
            conn,
            settings=settings,
            worker_id=worker_id,
            rate_limit_count=prefs.rate_limit_count,
            rate_limit_window_seconds=prefs.rate_limit_window_seconds,
            current=current,
        )
        conn.commit()
        rate_limited += deferred_now

        if delivery is None:
            break

        # No open transaction during outbound HTTP
        result = active_sender.send_message(
            chat_id=target_chat_id,
            text=delivery.message_redacted,
        )
        if result.ok:
            complete_delivery(conn, delivery.id, worker_id=worker_id, now=current)
            sent += 1
        else:
            delay = (
                result.retry_after_seconds
                if result.retry_after_seconds is not None
                else min(300, 15 * (2 ** max(0, delivery.attempt_count - 1)))
            )
            exhausted = result.permanent or (
                delivery.attempt_count >= settings.notification_max_attempts
            )
            fail_delivery(
                conn,
                delivery.id,
                worker_id=worker_id,
                error_message=result.error_message,
                retry_delay_seconds=delay,
                max_attempts=settings.notification_max_attempts,
                permanent=result.permanent,
                now=current,
            )
            if exhausted:
                dead_letter += 1
            else:
                failed += 1
        conn.commit()

    prune_terminal_deliveries(
        conn, retention_limit=settings.notification_history_retention_limit
    )
    conn.commit()
    return {
        "status": "ok" if failed == 0 and dead_letter == 0 else "degraded",
        "enqueued": eval_res.enqueued,
        "recovered": recovered,
        "sent": sent,
        "failed": failed,
        "dead_letter": dead_letter,
        "rate_limited": rate_limited,
    }


class NotificationDeliveryScheduler(HardenedPeriodicScheduler):
    """Non-overlapping background scheduler for outbox evaluation and Telegram delivery."""

    def __init__(
        self,
        settings: Settings,
        *,
        sender: TelegramOutboundSender | None = None,
        shutdown_timeout_seconds: float = 2.0,
    ) -> None:
        self._settings = settings
        self._sender = sender
        super().__init__(
            worker_name_prefix="notif-delivery-worker",
            task_name="notif-delivery-scheduler",
            shutdown_timeout_seconds=shutdown_timeout_seconds,
        )

    def _is_enabled(self) -> bool:
        return bool(
            self._settings.notification_scheduler_enabled and self._settings.telegram_enabled
        )

    def _interval_seconds(self) -> int:
        return self._settings.notification_poll_interval_seconds

    def _timeout_seconds(self) -> float:
        return self._settings.notification_cycle_timeout_seconds

    def _min_persist_interval_seconds(self) -> int:
        return 0

    def _extract_status(self, snapshot: dict[str, Any]) -> str:
        return str(snapshot.get("status", "ok"))

    def _execute_sync(self, *, force_persist: bool = False) -> dict[str, Any]:
        summary = run_notification_outbox_cycle(
            self._settings.db_path,
            self._settings,
            sender=self._sender,
            worker_id="notif-scheduler-worker",
        )
        return {"snapshot_id": 0, "snapshot": summary}
