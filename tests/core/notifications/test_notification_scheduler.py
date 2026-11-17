"""Tests for Phase 05 P05-F04: Notification & HA schedulers, overlap, shutdown, and isolation."""

from __future__ import annotations

import asyncio
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from tests.core.workspace.conftest import make_workspace_settings

from homeagentp_core.config import Settings
from homeagentp_core.db.connection import db_session
from homeagentp_core.main import create_app
from homeagentp_core.modules.home_assistant.collector import get_ha_overview
from homeagentp_core.modules.home_assistant.scheduler import HomeAssistantCollectionScheduler
from homeagentp_core.modules.notifications.outbox import (
    enqueue_notification,
    list_deliveries,
)
from homeagentp_core.modules.notifications.scheduler import (
    NotificationDeliveryScheduler,
    process_notification_outbox_cycle,
)
from homeagentp_core.modules.notifications.telegram import TelegramOutboundSender

FAKE_TOKEN = "123456:AAFakeBotTokenForSchedulerTests_1234567"  # noqa: S105


def _make_sched_settings(tmp_path: Path, **overrides: object) -> Settings:
    base = make_workspace_settings(tmp_path, db_name="sched_test.db")
    data = base.model_dump()
    data.update(overrides)
    return Settings(**data)


def test_outbox_cycle_delivery_rate_limit_429_4xx_and_lease_recovery(tmp_path: Path) -> None:
    settings = _make_sched_settings(
        tmp_path,
        telegram_enabled=True,
        telegram_bot_token=FAKE_TOKEN,
        telegram_allowed_chat_ids=["-100123456789"],
    )
    app = create_app(settings)
    with TestClient(app):
        pass

    t0 = datetime(2026, 11, 17, 15, 0, 0, tzinfo=UTC)
    sent_texts: list[str] = []

    def mock_telegram(request: httpx.Request) -> httpx.Response:
        sent_texts.append(request.content.decode("utf-8"))
        return httpx.Response(200, json={"ok": True, "result": {"message_id": len(sent_texts)}})

    sender = TelegramOutboundSender(
        bot_token=FAKE_TOKEN,
        allowed_chat_ids=["-100123456789"],
        transport=httpx.MockTransport(mock_telegram),
    )

    with db_session(settings.db_path) as conn:
        conn.execute(
            """
            INSERT INTO notification_preferences (
                id, telegram_enabled, min_severity, notify_on_resolve,
                cooldown_seconds, rate_limit_count, rate_limit_window_seconds,
                updated_by, updated_at
            ) VALUES (1, 1, 'warning', 1, 900, 1, 300, 'admin', '2026-11-17T00:00:00Z')
            """
        )
        conn.execute(
            """
            INSERT INTO nas_alerts (
                alert_key, code, severity, category, component, target, message,
                status, first_seen_at, last_seen_at, occurrences
            )
            VALUES (
                'nas_a', 'cpu_high', 'warning', 'cpu', 'cpu', 'host', 'CPU high',
                'active', '2026-11-17T15:00:00Z', '2026-11-17T15:00:00Z', 1
            )
            """
        )
        # First cycle sends nas_a
        res1 = process_notification_outbox_cycle(conn, settings, sender=sender, now=t0)
        assert res1["sent"] == 1
        assert len(sent_texts) == 1

        # Enqueue second alert within rate_limit_count=1 window -> suppressed_rate_limit
        d2 = enqueue_notification(
            conn,
            incident_key="nas:nas_b:t1:triggered",
            source_domain="nas",
            severity="critical",
            destination_masked="***6789",
            message="Disk full",
            now=t0 + timedelta(seconds=10),
        )
        res2 = process_notification_outbox_cycle(
            conn, settings, sender=sender, now=t0 + timedelta(seconds=10)
        )
        assert res2["rate_limited"] == 1
        assert len(sent_texts) == 1
        d2_row = next(r for r in list_deliveries(conn, limit=20) if r.id == d2.id)
        assert d2_row.status == "suppressed_rate_limit"

        # Increase rate limit; test 429 Retry-After then 400 dead_letter
        conn.execute("UPDATE notification_preferences SET rate_limit_count = 10 WHERE id = 1")
        d3 = enqueue_notification(
            conn,
            incident_key="media:radarr:t1:triggered",
            source_domain="media",
            severity="warning",
            destination_masked="***6789",
            message="Radarr down",
            now=t0 + timedelta(seconds=20),
        )
        sender_429 = TelegramOutboundSender(
            bot_token=FAKE_TOKEN,
            allowed_chat_ids=["-100123456789"],
            transport=httpx.MockTransport(
                lambda req: httpx.Response(429, headers={"Retry-After": "60"})
            ),
        )
        res3 = process_notification_outbox_cycle(
            conn, settings, sender=sender_429, now=t0 + timedelta(seconds=20)
        )
        assert res3["failed"] == 1
        d3_row = next(r for r in list_deliveries(conn, limit=20) if r.id == d3.id)
        assert d3_row.status == "failed"

        sender_400 = TelegramOutboundSender(
            bot_token=FAKE_TOKEN,
            allowed_chat_ids=["-100123456789"],
            transport=httpx.MockTransport(lambda req: httpx.Response(400, json={"ok": False})),
        )
        res4 = process_notification_outbox_cycle(
            conn, settings, sender=sender_400, now=t0 + timedelta(seconds=90)
        )
        assert res4["dead_letter"] == 1
        d3_dead = next(r for r in list_deliveries(conn, limit=20) if r.id == d3.id)
        assert d3_dead.status == "dead_letter"


def test_notification_scheduler_overlap_timeout_and_bounded_shutdown(tmp_path: Path) -> None:
    async def _run() -> None:
        settings = _make_sched_settings(
            tmp_path,
            telegram_enabled=True,
            telegram_bot_token=FAKE_TOKEN,
            telegram_allowed_chat_ids=["-100123456789"],
            notification_scheduler_enabled=True,
            notification_cycle_timeout_seconds=1.0,
        )
        app = create_app(settings)
        with TestClient(app):
            pass

        with db_session(settings.db_path) as conn:
            conn.execute(
                """
                INSERT INTO notification_preferences (
                    id, telegram_enabled, min_severity, notify_on_resolve,
                    cooldown_seconds, rate_limit_count, rate_limit_window_seconds,
                    updated_by, updated_at
                ) VALUES (1, 1, 'warning', 1, 900, 10, 300, 'admin', '2026-11-17T00:00:00Z')
                """
            )
            enqueue_notification(
                conn,
                incident_key="nas:slow_test:t1:triggered",
                source_domain="nas",
                severity="warning",
                destination_masked="***6789",
                message="Slow test",
            )

        entered = threading.Event()
        release = threading.Event()

        def slow_handler(request: httpx.Request) -> httpx.Response:
            entered.set()
            release.wait(timeout=3.0)
            return httpx.Response(200, json={"ok": True})

        sender = TelegramOutboundSender(
            bot_token=FAKE_TOKEN,
            allowed_chat_ids=["-100123456789"],
            transport=httpx.MockTransport(slow_handler),
        )
        scheduler = NotificationDeliveryScheduler(
            settings,
            sender=sender,
            shutdown_timeout_seconds=0.05,
        )
        # Override timeout to 0.1s for fast test
        scheduler._timeout_seconds = lambda: 0.1  # type: ignore[method-assign]

        # First run times out while worker thread is blocked
        res1 = await scheduler.run_once()
        assert res1 is None
        assert scheduler.last_status == "timeout"
        assert entered.is_set()

        # Second run detects busy worker thread and skips without overlapping
        res2 = await scheduler.run_once()
        assert res2 is None
        assert scheduler.skipped_overlap_count == 1
        assert scheduler.last_status == "skipped_worker_busy"

        # Bounded shutdown reports stopping_worker_hung while blocked
        stop_summary = await scheduler.stop(wait_timeout=0.05)
        assert stop_summary["last_status"] == "stopping_worker_hung"

        release.set()
        await asyncio.sleep(0.15)
        assert not scheduler._worker_lock.locked()

    asyncio.run(_run())


def test_ha_scheduler_persists_unavailable_and_isolates_failures(tmp_path: Path) -> None:
    async def _run() -> None:
        settings = _make_sched_settings(
            tmp_path,
            ha_enabled=True,
            ha_scheduler_enabled=True,
            ha_allowed_entities=["sensor.ups_load"],
        )
        app = create_app(settings)
        with TestClient(app):
            pass

        calls = 0

        def flaky_collector(_: Settings) -> dict[str, object]:
            nonlocal calls
            calls += 1
            now_iso = datetime.now(UTC).isoformat()
            if calls == 1:
                return {
                    "status": "online",
                    "enabled": True,
                    "reason": "ok",
                    "collected_at": now_iso,
                    "entities": [
                        {
                            "entity_id": "sensor.ups_load",
                            "domain": "sensor",
                            "friendly_name": "UPS Load",
                            "state": "15",
                            "attributes": {},
                            "status": "online",
                            "last_changed": None,
                            "collected_at": now_iso,
                        }
                    ],
                }
            return {
                "status": "unavailable",
                "enabled": True,
                "reason": "HA connection refused",
                "collected_at": now_iso,
                "entities": [],
            }

        ha_sched = HomeAssistantCollectionScheduler(settings, collector_fn=flaky_collector)
        await ha_sched.run_once(force_persist=True)
        with db_session(settings.db_path) as conn:
            assert get_ha_overview(conn, settings).status == "online"

        # Second cycle fails -> immediately persists unavailable, clearing stale online state
        await ha_sched.run_once(force_persist=False)
        with db_session(settings.db_path) as conn:
            ov = get_ha_overview(conn, settings)
            assert ov.status == "unavailable"
            assert all(e.status == "unavailable" for e in ov.entities)
        await ha_sched.stop()

    asyncio.run(_run())


def test_sqlite_remains_writable_during_blocking_telegram_http(tmp_path: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    from homeagentp_core.modules.notifications.scheduler import run_notification_outbox_cycle

    settings = _make_sched_settings(
        tmp_path,
        telegram_enabled=True,
        telegram_bot_token=FAKE_TOKEN,
        telegram_allowed_chat_ids=["-100123456789"],
    )
    app = create_app(settings)
    with TestClient(app):
        pass

    with db_session(settings.db_path) as conn:
        conn.execute(
            """
            INSERT INTO notification_preferences (
                id, telegram_enabled, min_severity, notify_on_resolve,
                cooldown_seconds, rate_limit_count, rate_limit_window_seconds,
                updated_by, updated_at
            ) VALUES (1, 1, 'warning', 1, 900, 10, 300, 'admin', '2026-11-17T00:00:00Z')
            """
        )
        d1 = enqueue_notification(
            conn,
            incident_key="nas:concurrent_http:t1:triggered",
            source_domain="nas",
            severity="warning",
            destination_masked="***6789",
            message="Concurrent HTTP test",
        )

    entered = threading.Event()
    release = threading.Event()

    def blocking_http(request: httpx.Request) -> httpx.Response:
        entered.set()
        assert release.wait(timeout=5.0)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 101}})

    sender = TelegramOutboundSender(
        bot_token=FAKE_TOKEN,
        allowed_chat_ids=["-100123456789"],
        transport=httpx.MockTransport(blocking_http),
    )

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            run_notification_outbox_cycle,
            settings.db_path,
            settings,
            sender=sender,
            worker_id="tx-test-worker",
        )
        assert entered.wait(timeout=5.0)

        # Independent second SQLite connection must see committed 'in_flight' AND be able to write
        with db_session(settings.db_path) as conn2:
            row = conn2.execute(
                "SELECT status, claimed_by FROM notification_deliveries WHERE id = ?",
                (d1.id,),
            ).fetchone()
            assert row is not None
            assert row["status"] == "in_flight"
            assert row["claimed_by"] == "tx-test-worker"

            conn2.execute(
                """
                INSERT INTO nas_alerts (
                    alert_key, code, severity, category, component, target, message,
                    status, first_seen_at, last_seen_at, occurrences
                )
                VALUES (
                    'concurrent_write', 'disk_warn', 'warning', 'disk', 'disk', '/mnt/d1', 'ok',
                    'active', '2026-11-17T00:00:00Z', '2026-11-17T00:00:00Z', 1
                )
                """
            )

        release.set()
        res = future.result(timeout=5.0)
        assert res["sent"] == 1

    with db_session(settings.db_path) as conn3:
        final_row = conn3.execute(
            "SELECT status FROM notification_deliveries WHERE id = ?",
            (d1.id,),
        ).fetchone()
        assert final_row is not None and final_row["status"] == "sent"
