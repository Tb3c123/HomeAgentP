"""Tests for Phase 05 P05-F02: Notification preferences, evaluator, and durable outbox."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from tests.core.conftest import TEST_ADMIN_PASSWORD, TEST_ADMIN_USERNAME
from tests.core.workspace.conftest import login_client, make_workspace_settings

from homeagentp_core.auth.security import hash_password
from homeagentp_core.db.connection import db_session
from homeagentp_core.main import create_app
from homeagentp_core.modules.notifications.evaluator import evaluate_alerts_to_outbox
from homeagentp_core.modules.notifications.outbox import (
    claim_next_delivery,
    complete_delivery,
    enqueue_notification,
    fail_delivery,
    list_deliveries,
    prune_terminal_deliveries,
    recover_expired_leases,
)


def test_outbox_dedup_concurrent_enqueue_claim_lease_overflow_and_retention(
    tmp_path: Path,
) -> None:
    settings = make_workspace_settings(tmp_path, db_name="outbox.db")
    app = create_app(settings)
    with TestClient(app):
        pass

    base_now = datetime(2026, 11, 17, 12, 0, 0, tzinfo=UTC)

    with db_session(settings.db_path) as conn:
        # 1. Duplicate suppression within cooldown
        d1 = enqueue_notification(
            conn,
            incident_key="nas:disk_high:triggered",
            source_domain="nas",
            severity="warning",
            destination_masked="***6789",
            message="Disk /mnt/disk1 at 90% token=should_be_redacted",
            cooldown_seconds=900,
            now=base_now,
        )
        assert d1.status == "pending"
        assert "should_be_redacted" not in d1.message_redacted

        d_dup = enqueue_notification(
            conn,
            incident_key="nas:disk_high:triggered",
            source_domain="nas",
            severity="warning",
            destination_masked="***6789",
            message="Duplicate alert",
            cooldown_seconds=900,
            now=base_now + timedelta(seconds=60),
        )
        assert d_dup.status == "suppressed_cooldown"

        # 2. Priority ordering (critical claimed before warning) & atomic claim
        d_crit = enqueue_notification(
            conn,
            incident_key="nas:mount_missing:triggered",
            source_domain="nas",
            severity="critical",
            destination_masked="***6789",
            message="Mount /mnt/disk2 missing",
            cooldown_seconds=900,
            now=base_now,
        )
        assert d_crit.status == "pending"

        claimed1 = claim_next_delivery(conn, worker_id="worker-a", lease_seconds=30, now=base_now)
        assert claimed1 is not None
        assert claimed1.id == d_crit.id
        assert claimed1.status == "in_flight"
        assert claimed1.claimed_by == "worker-a"

        # 3. Interrupted worker lease recovery
        after_lease = base_now + timedelta(seconds=45)
        recovered = recover_expired_leases(conn, max_attempts=3, now=after_lease)
        assert recovered == 1

        reclaimed = claim_next_delivery(
            conn, worker_id="worker-b", lease_seconds=30, now=after_lease
        )
        assert reclaimed is not None
        assert reclaimed.id == d_crit.id
        assert reclaimed.attempt_count == 2
        assert complete_delivery(conn, reclaimed.id, worker_id="worker-b", now=after_lease)

        # Complete remaining pending item (d1) and verify permanent failure -> dead_letter
        claimed2 = claim_next_delivery(
            conn, worker_id="worker-b", lease_seconds=30, now=after_lease
        )
        assert claimed2 is not None and claimed2.id == d1.id
        assert fail_delivery(
            conn,
            claimed2.id,
            worker_id="worker-b",
            error_message="HTTP 400 bad chat_id bot123456:AAH_SecretToken_123456789012345",
            permanent=True,
            now=after_lease,
        )
        all_rows = list_deliveries(conn, limit=50)
        d1_row = next(r for r in all_rows if r.id == d1.id)
        assert d1_row.status == "dead_letter"
        assert "AAH_SecretToken" not in d1_row.last_error_redacted

        # 4. Bounded queue overflow: fill queue to max_active=2, then critical evicts info
        enqueue_notification(
            conn,
            incident_key="media:info_1:triggered",
            source_domain="media",
            severity="info",
            destination_masked="***6789",
            message="Info 1",
            max_active=2,
            now=after_lease,
        )
        enqueue_notification(
            conn,
            incident_key="media:warn_1:triggered",
            source_domain="media",
            severity="warning",
            destination_masked="***6789",
            message="Warn 1",
            max_active=2,
            now=after_lease,
        )
        crit_ov = enqueue_notification(
            conn,
            incident_key="nas:crit_ov:triggered",
            source_domain="nas",
            severity="critical",
            destination_masked="***6789",
            message="Critical alert",
            max_active=2,
            now=after_lease,
        )
        assert crit_ov.status == "pending"

        # 5. Retention safety: NEVER prune pending or in_flight rows
        pruned = prune_terminal_deliveries(conn, retention_limit=1)
        assert pruned >= 1
        pending_remaining = list_deliveries(conn, status="pending", limit=50)
        assert len(pending_remaining) == 2

    # 6. Concurrent enqueue stress check (no SQLite lock errors / lost rows)
    def _worker(idx: int) -> str:
        with db_session(settings.db_path) as c:
            res = enqueue_notification(
                c,
                incident_key=f"concurrent:key_{idx}:triggered",
                source_domain="system",
                severity="info",
                destination_masked="***6789",
                message=f"Concurrent {idx}",
                max_active=100,
            )
            return res.status

    with ThreadPoolExecutor(max_workers=6) as pool:
        statuses = list(pool.map(_worker, range(12)))
    assert all(s == "pending" for s in statuses)


def test_notification_preferences_evaluator_rbac_and_csrf(tmp_path: Path) -> None:
    base = make_workspace_settings(tmp_path, db_name="notif_api.db")
    data = base.model_dump()
    data.update(
        {
            "telegram_enabled": True,
            "telegram_bot_token": "123456:AAFakeBotTokenForTestsOnly_1234567890",
            "telegram_allowed_chat_ids": ["-100123456789"],
        }
    )
    settings = type(base)(**data)
    app = create_app(settings)
    with TestClient(app) as client:
        with db_session(settings.db_path) as conn:
            conn.execute(
                """
                INSERT INTO users (username, password_hash, role, is_active, created_at)
                VALUES (?, ?, 'viewer', 1, '2026-11-17T00:00:00Z')
                """,
                ("notif_viewer", hash_password("ViewerPass#12345")),
            )
            conn.execute(
                """
                INSERT INTO nas_alerts (
                    alert_key, code, severity, category, component, target, message,
                    status, first_seen_at, last_seen_at, occurrences
                )
                VALUES (
                    'nas_cpu', 'cpu_high', 'warning', 'cpu', 'cpu', 'host', 'CPU high',
                    'active', '2026-11-17T00:00:00Z', '2026-11-17T00:00:00Z', 1
                )
                """
            )

        viewer_csrf = login_client(client, "notif_viewer", "ViewerPass#12345")
        assert client.get("/api/v1/notifications/preferences").status_code == 200
        assert (
            client.put(
                "/api/v1/notifications/preferences",
                json={"telegram_enabled": True, "min_severity": "critical"},
                headers={"X-CSRF-Token": viewer_csrf},
            ).status_code
            == 403
        )

        owner_csrf = login_client(client, TEST_ADMIN_USERNAME, TEST_ADMIN_PASSWORD)
        # Missing CSRF rejected
        assert (
            client.put(
                "/api/v1/notifications/preferences",
                json={"telegram_enabled": True, "min_severity": "warning"},
            ).status_code
            == 403
        )
        upd = client.put(
            "/api/v1/notifications/preferences",
            json={"telegram_enabled": True, "min_severity": "warning", "cooldown_seconds": 600},
            headers={"X-CSRF-Token": owner_csrf},
        )
        assert upd.status_code == 200
        assert upd.json()["cooldown_seconds"] == 600

        with db_session(settings.db_path) as conn:
            ev1 = evaluate_alerts_to_outbox(conn, settings)
            ev2 = evaluate_alerts_to_outbox(conn, settings)
            assert ev1.enqueued == 1
            assert ev2.suppressed_cooldown == 1

        deliv = client.get("/api/v1/notifications/deliveries")
        assert deliv.status_code == 200
        assert len(deliv.json()) == 2


def test_disabled_or_unconfigured_telegram_never_enqueues_pending(tmp_path: Path) -> None:
    import pytest

    base = make_workspace_settings(tmp_path, db_name="notif_disabled.db")
    app = create_app(base)
    with TestClient(app):
        pass

    with db_session(base.db_path) as conn:
        conn.execute(
            """
            INSERT INTO nas_alerts (
                alert_key, code, severity, category, component, target, message,
                status, first_seen_at, last_seen_at, occurrences
            )
            VALUES (
                'nas_disk', 'disk_high', 'critical', 'disk', 'disk', '/mnt/disk1', 'Disk full',
                'active', '2026-11-17T00:00:00Z', '2026-11-17T00:00:00Z', 1
            )
            """
        )
        # Enable preference in DB, but runtime telegram_enabled=False and no chat_ids
        conn.execute(
            """
            INSERT INTO notification_preferences (
                id, telegram_enabled, min_severity, notify_on_resolve,
                cooldown_seconds, rate_limit_count, rate_limit_window_seconds,
                updated_by, updated_at
            ) VALUES (1, 1, 'warning', 1, 900, 10, 300, 'admin', '2026-11-17T00:00:00Z')
            """
        )

        ev_runtime_off = evaluate_alerts_to_outbox(conn, base)
        assert ev_runtime_off.enqueued == 0
        assert ev_runtime_off.skipped_disabled == 1
        assert list_deliveries(conn, status="pending", limit=20) == []

        # Runtime enabled, but missing destination chat IDs
        data = base.model_dump()
        data.update(
            {
                "telegram_enabled": True,
                "telegram_bot_token": "123:ABC",
                "telegram_allowed_chat_ids": [],
            }
        )
        no_dest_settings = type(base)(**data)
        ev_no_dest = evaluate_alerts_to_outbox(conn, no_dest_settings)
        assert ev_no_dest.enqueued == 0
        assert ev_no_dest.skipped_disabled == 1
        assert list_deliveries(conn, limit=20) == []

        # Direct enqueue without valid destination fails closed
        with pytest.raises(ValueError, match="authorized destination"):
            enqueue_notification(
                conn,
                incident_key="nas:nas_disk:t1:triggered",
                source_domain="nas",
                severity="critical",
                destination_masked="not_configured",
                message="Should fail",
            )


def test_failed_delivery_suppresses_duplicates_and_concurrent_eval_is_atomic(
    tmp_path: Path,
) -> None:
    base = make_workspace_settings(tmp_path, db_name="notif_failed_dedup.db")
    data = base.model_dump()
    data.update(
        {
            "telegram_enabled": True,
            "telegram_bot_token": "123456:AAFakeBotTokenForTestsOnly_1234567890",
            "telegram_allowed_chat_ids": ["-100123456789"],
        }
    )
    settings = type(base)(**data)
    app = create_app(settings)
    with TestClient(app):
        pass

    base_now = datetime(2026, 11, 17, 13, 0, 0, tzinfo=UTC)
    with db_session(settings.db_path) as conn:
        d1 = enqueue_notification(
            conn,
            incident_key="nas:disk1:t1:triggered",
            source_domain="nas",
            severity="warning",
            destination_masked="***6789",
            message="Disk warning",
            cooldown_seconds=60,
            now=base_now,
        )
        claimed = claim_next_delivery(conn, worker_id="w1", lease_seconds=30, now=base_now)
        assert claimed is not None and claimed.id == d1.id
        assert fail_delivery(
            conn,
            d1.id,
            worker_id="w1",
            error_message="HTTP 503 temporary",
            retry_delay_seconds=30,
            max_attempts=3,
            now=base_now,
        )

        # Retryable 'failed' delivery must suppress new duplicate even after cooldown window
        dup = enqueue_notification(
            conn,
            incident_key="nas:disk1:t1:triggered",
            source_domain="nas",
            severity="warning",
            destination_masked="***6789",
            message="Disk warning again",
            cooldown_seconds=60,
            now=base_now + timedelta(seconds=120),
        )
        assert dup.status == "suppressed_cooldown"

        # Suppressed audit record must NOT be claimable as sendable delivery
        claimed_after = claim_next_delivery(
            conn,
            worker_id="w2",
            lease_seconds=30,
            now=base_now + timedelta(seconds=120),
        )
        assert claimed_after is not None and claimed_after.id == d1.id
        assert complete_delivery(
            conn, d1.id, worker_id="w2", now=base_now + timedelta(seconds=120)
        )
        assert (
            claim_next_delivery(
                conn,
                worker_id="w2",
                lease_seconds=30,
                now=base_now + timedelta(seconds=121),
            )
            is None
        )

    # Concurrent duplicate enqueue for same incident+destination -> exactly 1 pending
    def _race(_: int) -> str:
        with db_session(settings.db_path) as c:
            res = enqueue_notification(
                c,
                incident_key="media:sonarr_down:t1:triggered",
                source_domain="media",
                severity="critical",
                destination_masked="***6789",
                message="Sonarr down",
                cooldown_seconds=900,
                now=base_now,
            )
            return res.status

    with ThreadPoolExecutor(max_workers=6) as pool:
        race_statuses = list(pool.map(_race, range(8)))
    assert race_statuses.count("pending") == 1
    assert race_statuses.count("suppressed_cooldown") == 7


def test_triggered_resolved_lifecycle_and_restart_idempotency(tmp_path: Path) -> None:
    base = make_workspace_settings(tmp_path, db_name="notif_lifecycle.db")
    data = base.model_dump()
    data.update(
        {
            "telegram_enabled": True,
            "telegram_bot_token": "123456:AAFakeBotTokenForTestsOnly_1234567890",
            "telegram_allowed_chat_ids": ["-100123456789"],
        }
    )
    settings = type(base)(**data)
    app = create_app(settings)
    with TestClient(app):
        pass

    t0 = datetime(2026, 11, 17, 14, 0, 0, tzinfo=UTC)
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
        conn.execute(
            """
            INSERT INTO nas_alerts (
                alert_key, code, severity, category, component, target, message,
                status, first_seen_at, last_seen_at, occurrences
            )
            VALUES (
                'nas_ram', 'ram_high', 'warning', 'ram', 'ram', 'host', 'RAM high',
                'active', '2026-11-17T14:00:00Z', '2026-11-17T14:00:00Z', 1
            )
            """
        )
        ev1 = evaluate_alerts_to_outbox(conn, settings, now=t0)
        assert ev1.enqueued == 1

        # Resolve alert -> emits exactly one resolved notification
        conn.execute(
            "UPDATE nas_alerts SET status = 'resolved', resolved_at = ? "
            "WHERE alert_key = 'nas_ram'",
            ((t0 + timedelta(minutes=1)).isoformat(),),
        )
        ev2 = evaluate_alerts_to_outbox(conn, settings, now=t0 + timedelta(minutes=1))
        assert ev2.enqueued == 1

    # Simulate restart / new connection and repeated polling while resolved -> 0 new notifications
    with db_session(settings.db_path) as conn:
        ev3 = evaluate_alerts_to_outbox(conn, settings, now=t0 + timedelta(minutes=2))
        ev4 = evaluate_alerts_to_outbox(conn, settings, now=t0 + timedelta(minutes=30))
        assert ev3.enqueued == 0
        assert ev4.enqueued == 0

        # Re-trigger same alert -> new transition sequence t2:triggered
        conn.execute(
            "UPDATE nas_alerts SET status = 'active', resolved_at = NULL "
            "WHERE alert_key = 'nas_ram'"
        )
        ev5 = evaluate_alerts_to_outbox(conn, settings, now=t0 + timedelta(minutes=31))
        assert ev5.enqueued == 1

        # Disable notify_on_resolve and resolve -> 0 resolved notifications
        conn.execute("UPDATE notification_preferences SET notify_on_resolve = 0 WHERE id = 1")
        conn.execute(
            "UPDATE nas_alerts SET status = 'resolved', resolved_at = ? "
            "WHERE alert_key = 'nas_ram'",
            ((t0 + timedelta(minutes=32)).isoformat(),),
        )
        ev6 = evaluate_alerts_to_outbox(conn, settings, now=t0 + timedelta(minutes=32))
        assert ev6.enqueued == 0

        all_pending = list_deliveries(conn, status="pending", limit=20)
        keys = [d.incident_key for d in all_pending]
        assert "nas:nas_ram:t1:triggered" in keys
        assert "nas:nas_ram:t1:resolved" in keys
        assert "nas:nas_ram:t2:triggered" in keys
        assert "nas:nas_ram:t2:resolved" not in keys
