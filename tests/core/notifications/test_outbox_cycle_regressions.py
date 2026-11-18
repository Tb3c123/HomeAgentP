"""Regression tests for run_notification_outbox_cycle (PR #5 Review Cases A-H)."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from tests.core.workspace.conftest import make_workspace_settings

from homeagentp_core.config import Settings
from homeagentp_core.db.connection import db_session
from homeagentp_core.main import create_app
from homeagentp_core.modules.notifications.outbox import (
    enqueue_notification,
    list_deliveries,
)
from homeagentp_core.modules.notifications.scheduler import (
    run_notification_outbox_cycle,
)
from homeagentp_core.modules.notifications.telegram import TelegramOutboundSender

FAKE_TOKEN = "123456:AAFakeBotTokenForRegressionTests_123456"  # noqa: S105


def _setup_outbox_db(tmp_path: Path, db_name: str, *, rate_limit_count: int = 1) -> Settings:
    base = make_workspace_settings(tmp_path, db_name=db_name)
    data = base.model_dump()
    data.update(
        {
            "telegram_enabled": True,
            "telegram_bot_token": FAKE_TOKEN,
            "telegram_allowed_chat_ids": ["-100123456789"],
            "notification_max_attempts": 3,
            "notification_lease_seconds": 30,
        }
    )
    settings = Settings(**data)
    with TestClient(create_app(settings)):
        pass
    with db_session(settings.db_path) as conn:
        conn.execute(
            """
            INSERT INTO notification_preferences (
                id, telegram_enabled, min_severity, notify_on_resolve,
                cooldown_seconds, rate_limit_count, rate_limit_window_seconds,
                updated_by, updated_at
            ) VALUES (1, 1, 'warning', 1, 900, ?, 300, 'admin', '2026-11-17T00:00:00Z')
            """,
            (rate_limit_count,),
        )
    return settings


def test_case_a_critical_sent_when_rate_limit_full_and_non_critical_deferred(
    tmp_path: Path,
) -> None:
    """Regression for PR #5 blocker: critical item must NOT be stranded in_flight."""
    settings = _setup_outbox_db(tmp_path, "case_a.db", rate_limit_count=1)
    t0 = datetime(2026, 11, 17, 18, 0, 0, tzinfo=UTC)
    sent_payloads: list[str] = []

    sender = TelegramOutboundSender(
        bot_token=FAKE_TOKEN,
        allowed_chat_ids=["-100123456789"],
        transport=httpx.MockTransport(
            lambda req: (
                sent_payloads.append(req.content.decode("utf-8"))
                or httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})
            )
        ),
    )

    with db_session(settings.db_path) as conn:
        # Saturate rate limit with 1 prior sent delivery in window
        conn.execute(
            """
            INSERT INTO notification_deliveries (
                incident_key, source_domain, severity, channel, destination_masked,
                message_redacted, status, claimed_by, lease_expires_at,
                attempt_count, next_attempt_at, last_error_redacted, created_at, sent_at
            ) VALUES (
                'nas:prior:t1:triggered', 'nas', 'warning', 'telegram', '***6789',
                'Prior', 'sent', '', NULL, 1, NULL, '', ?, ?
            )
            """,
            (t0.isoformat(), t0.isoformat()),
        )
        warn_d = enqueue_notification(
            conn,
            incident_key="nas:warn_1:t1:triggered",
            source_domain="nas",
            severity="warning",
            destination_masked="***6789",
            message="Warning alert",
            now=t0 + timedelta(seconds=5),
        )
        crit_d = enqueue_notification(
            conn,
            incident_key="nas:crit_1:t1:triggered",
            source_domain="nas",
            severity="critical",
            destination_masked="***6789",
            message="Critical alert",
            now=t0 + timedelta(seconds=5),
        )

    res = run_notification_outbox_cycle(
        settings.db_path, settings, sender=sender, now=t0 + timedelta(seconds=5)
    )
    assert res["rate_limited"] == 1
    assert res["sent"] == 1
    assert len(sent_payloads) == 1
    assert "Critical alert" in sent_payloads[0]

    with db_session(settings.db_path) as conn:
        rows = {r.id: r for r in list_deliveries(conn, limit=20)}
        assert rows[crit_d.id].status == "sent"
        assert rows[crit_d.id].claimed_by == ""
        assert rows[warn_d.id].status == "pending"
        assert rows[warn_d.id].attempt_count == 0
        assert rows[warn_d.id].next_attempt_at is not None


def test_case_b_and_c_and_e_rate_limit_states_and_empty_queue(tmp_path: Path) -> None:
    """Case B (rate-limit full, non-critical only), Case C (not full), Case E (empty queue)."""
    settings = _setup_outbox_db(tmp_path, "case_bce.db", rate_limit_count=1)
    t0 = datetime(2026, 11, 17, 18, 10, 0, tzinfo=UTC)
    calls = 0

    def handler(req: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"ok": True, "result": {"message_id": calls}})

    sender = TelegramOutboundSender(
        bot_token=FAKE_TOKEN,
        allowed_chat_ids=["-100123456789"],
        transport=httpx.MockTransport(handler),
    )

    # Case E: empty queue -> clean no-op
    res_empty = run_notification_outbox_cycle(settings.db_path, settings, sender=sender, now=t0)
    assert res_empty == {
        "status": "ok",
        "enqueued": 0,
        "recovered": 0,
        "sent": 0,
        "failed": 0,
        "dead_letter": 0,
        "rate_limited": 0,
    }
    assert calls == 0

    # Case C: rate limit not full -> normal delivery succeeds
    with db_session(settings.db_path) as conn:
        d1 = enqueue_notification(
            conn,
            incident_key="nas:c1:t1:triggered",
            source_domain="nas",
            severity="warning",
            destination_masked="***6789",
            message="Normal delivery",
            now=t0,
        )
    res_c = run_notification_outbox_cycle(settings.db_path, settings, sender=sender, now=t0)
    assert res_c["sent"] == 1
    assert calls == 1

    # Case B: rate limit now full, only non-critical pending -> deferred without attempt_count++
    with db_session(settings.db_path) as conn:
        d2 = enqueue_notification(
            conn,
            incident_key="nas:b1:t1:triggered",
            source_domain="nas",
            severity="warning",
            destination_masked="***6789",
            message="Deferred warning",
            now=t0 + timedelta(seconds=10),
        )
    res_b = run_notification_outbox_cycle(
        settings.db_path, settings, sender=sender, now=t0 + timedelta(seconds=10)
    )
    assert res_b["sent"] == 0
    assert res_b["rate_limited"] == 1
    assert calls == 1
    with db_session(settings.db_path) as conn:
        rows = {r.id: r for r in list_deliveries(conn, limit=20)}
        assert rows[d1.id].status == "sent"
        assert rows[d2.id].status == "pending"
        assert rows[d2.id].attempt_count == 0
        assert rows[d2.id].next_attempt_at is not None
        assert rows[d2.id].next_attempt_at > (t0 + timedelta(seconds=10)).isoformat()


def test_case_d_and_f_429_backoff_timeout_and_dead_letter(tmp_path: Path) -> None:
    """Case D (HTTP 429 Retry-After, no busy loop) & Case F (timeout -> failed/dead_letter)."""
    settings = _setup_outbox_db(tmp_path, "case_df.db", rate_limit_count=10)
    t0 = datetime(2026, 11, 17, 18, 20, 0, tzinfo=UTC)

    with db_session(settings.db_path) as conn:
        d_429 = enqueue_notification(
            conn,
            incident_key="media:d429:t1:triggered",
            source_domain="media",
            severity="warning",
            destination_masked="***6789",
            message="429 test",
            now=t0,
        )

    sender_429 = TelegramOutboundSender(
        bot_token=FAKE_TOKEN,
        allowed_chat_ids=["-100123456789"],
        transport=httpx.MockTransport(
            lambda req: httpx.Response(429, headers={"Retry-After": "45"})
        ),
    )
    res_429 = run_notification_outbox_cycle(settings.db_path, settings, sender=sender_429, now=t0)
    assert res_429["failed"] == 1

    # Immediate poll 10s later must NOT retry before Retry-After expires
    res_wait = run_notification_outbox_cycle(
        settings.db_path, settings, sender=sender_429, now=t0 + timedelta(seconds=10)
    )
    assert res_wait["failed"] == 0 and res_wait["sent"] == 0

    with db_session(settings.db_path) as conn:
        row_429 = next(r for r in list_deliveries(conn, limit=20) if r.id == d_429.id)
        assert row_429.status == "failed"
        assert row_429.attempt_count == 1
        assert row_429.next_attempt_at == (t0 + timedelta(seconds=45)).isoformat()

    # Case F: Timeout retries up to max_attempts=3 then dead_letter
    def timeout_handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=req)

    sender_to = TelegramOutboundSender(
        bot_token=FAKE_TOKEN,
        allowed_chat_ids=["-100123456789"],
        transport=httpx.MockTransport(timeout_handler),
    )
    # Attempt 2 (at t0 + 50s) -> failed
    res_to2 = run_notification_outbox_cycle(
        settings.db_path, settings, sender=sender_to, now=t0 + timedelta(seconds=50)
    )
    assert res_to2["failed"] == 1
    # Attempt 3 (at t0 + 200s) -> dead_letter
    res_to3 = run_notification_outbox_cycle(
        settings.db_path, settings, sender=sender_to, now=t0 + timedelta(seconds=200)
    )
    assert res_to3["dead_letter"] == 1
    with db_session(settings.db_path) as conn:
        row_dead = next(r for r in list_deliveries(conn, limit=20) if r.id == d_429.id)
        assert row_dead.status == "dead_letter"
        assert row_dead.attempt_count == 3


def test_case_g_and_h_no_open_tx_during_http_and_critical_lease_recovery(
    tmp_path: Path,
) -> None:
    """Case G (SQLite writable during HTTP) & Case H (expired lease recovery for critical)."""
    settings = _setup_outbox_db(tmp_path, "case_gh.db", rate_limit_count=10)
    t0 = datetime(2026, 11, 17, 18, 30, 0, tzinfo=UTC)

    # Case H: Simulate crashed worker leaving a critical delivery in_flight with expired lease
    with db_session(settings.db_path) as conn:
        conn.execute(
            """
            INSERT INTO notification_deliveries (
                incident_key, source_domain, severity, channel, destination_masked,
                message_redacted, status, claimed_by, lease_expires_at,
                attempt_count, next_attempt_at, last_error_redacted, created_at, sent_at
            ) VALUES (
                'nas:crash_crit:t1:triggered', 'nas', 'critical', 'telegram', '***6789',
                'Recovered critical', 'in_flight', 'dead-worker', ?, 1, NULL, '', ?, NULL
            )
            """,
            ((t0 - timedelta(seconds=10)).isoformat(), (t0 - timedelta(seconds=60)).isoformat()),
        )

    entered = threading.Event()
    release = threading.Event()

    def blocking_ok(req: httpx.Request) -> httpx.Response:
        entered.set()
        assert release.wait(timeout=5.0)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 99}})

    sender = TelegramOutboundSender(
        bot_token=FAKE_TOKEN,
        allowed_chat_ids=["-100123456789"],
        transport=httpx.MockTransport(blocking_ok),
    )

    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(
            run_notification_outbox_cycle,
            settings.db_path,
            settings,
            sender=sender,
            worker_id="recovery-worker",
            now=t0,
        )
        assert entered.wait(timeout=5.0)
        # Case G: Second SQLite connection writes freely while HTTP is blocked
        with db_session(settings.db_path) as conn2:
            conn2.execute(
                "UPDATE notification_preferences SET cooldown_seconds = 600 WHERE id = 1"
            )
        release.set()
        res = fut.result(timeout=5.0)

    assert res["recovered"] == 1
    assert res["sent"] == 1
    with db_session(settings.db_path) as conn:
        rows = list_deliveries(conn, limit=10)
        assert rows[0].incident_key == "nas:crash_crit:t1:triggered"
        assert rows[0].status == "sent"
        assert rows[0].attempt_count == 2
