"""Background notification evaluation & Telegram delivery worker scheduler (P05-F04)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
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
    fail_delivery,
    prune_terminal_deliveries,
    recover_expired_leases,
)
from homeagentp_core.modules.notifications.preferences import get_notification_preferences
from homeagentp_core.modules.notifications.telegram import TelegramOutboundSender
from homeagentp_core.scheduler import HardenedPeriodicScheduler

MAX_DELIVERY_BATCH_PER_CYCLE = 10


def process_notification_outbox_cycle(
    conn: sqlite3.Connection,
    settings: Settings,
    *,
    sender: TelegramOutboundSender | None = None,
    worker_id: str = "notif-worker",
    max_batch: int = MAX_DELIVERY_BATCH_PER_CYCLE,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Evaluate alerts, recover expired leases, and send a bounded batch of due notifications."""
    current = now if now is not None else datetime.now(UTC)
    eval_res = evaluate_alerts_to_outbox(conn, settings, now=current)
    recovered = recover_expired_leases(
        conn,
        max_attempts=settings.notification_max_attempts,
        now=current,
    )

    prefs = get_notification_preferences(conn, settings)
    ready, chat_ids = is_telegram_channel_ready(settings, prefs)
    if not ready:
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
    target_chat_id = chat_ids[0]
    sent = 0
    failed = 0
    dead_letter = 0
    rate_limited = 0

    for _ in range(max(1, max_batch)):
        window_cutoff = (
            current - timedelta(seconds=prefs.rate_limit_window_seconds)
        ).isoformat()
        sent_in_window = int(
            conn.execute(
                "SELECT COUNT(*) FROM notification_deliveries "
                "WHERE status = 'sent' AND sent_at >= ?",
                (window_cutoff,),
            ).fetchone()[0]
        )

        delivery = claim_next_delivery(
            conn,
            worker_id=worker_id,
            lease_seconds=settings.notification_lease_seconds,
            max_attempts=settings.notification_max_attempts,
            now=current,
        )
        if delivery is None:
            break

        if sent_in_window >= prefs.rate_limit_count:
            conn.execute(
                """
                UPDATE notification_deliveries
                SET status = 'suppressed_rate_limit',
                    claimed_by = '',
                    lease_expires_at = NULL,
                    next_attempt_at = NULL,
                    last_error_redacted = 'rate_limit_exceeded'
                WHERE id = ? AND status = 'in_flight' AND claimed_by = ?
                """,
                (delivery.id, worker_id),
            )
            rate_limited += 1
            continue

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
        with db_session(self._settings.db_path) as conn:
            summary = process_notification_outbox_cycle(
                conn,
                self._settings,
                sender=self._sender,
                worker_id="notif-scheduler-worker",
            )
        return {"snapshot_id": 0, "snapshot": summary}
