"""Phase 05 P05-F06: Route contracts, migration 005/006 compatibility, and disabled-mode checks."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from tests.core.conftest import TEST_ADMIN_PASSWORD, TEST_ADMIN_USERNAME
from tests.core.workspace.conftest import login_client, make_workspace_settings

from homeagentp_core.auth.security import hash_password
from homeagentp_core.db.connection import db_session
from homeagentp_core.db.migrator import apply_migrations
from homeagentp_core.main import create_app


def test_migration_005_006_compatibility_and_idempotency(tmp_path: Path) -> None:
    db_path = tmp_path / "compat.db"
    with db_session(db_path) as conn:
        first = apply_migrations(conn)
        assert "005_home_assistant_telegram" in first
        assert "006_phase05_hardening" in first

        second = apply_migrations(conn)
        assert second == []

        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert {
            "ha_entity_states",
            "ha_entity_snapshots",
            "notification_preferences",
            "notification_deliveries",
            "notification_incident_states",
        }.issubset(tables)

        indexes = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
        assert "idx_notification_deliveries_active_unique" in indexes


def test_phase05_api_contracts_disabled_zero_network_and_rbac(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_network(*args: object, **kwargs: object) -> object:
        raise AssertionError("No external network calls allowed when HA and Telegram are disabled")

    monkeypatch.setattr(httpx.Client, "stream", fail_network)

    settings = make_workspace_settings(tmp_path, db_name="p05_contract.db")
    app = create_app(settings)

    with TestClient(app) as client:
        # Unauthenticated requests fail closed (401)
        assert client.get("/api/v1/home-assistant/overview").status_code == 401
        assert client.get("/api/v1/notifications/preferences").status_code == 401
        assert client.get("/api/v1/notifications/deliveries").status_code == 401

        with db_session(settings.db_path) as conn:
            conn.execute(
                """
                INSERT INTO users (username, password_hash, role, is_active, created_at)
                VALUES (?, ?, 'viewer', 1, '2026-11-17T00:00:00Z')
                """,
                ("p05_viewer", hash_password("ViewerPass#12345")),
            )

        # Viewer: read allowed, mutations 403 even with CSRF
        viewer_csrf = login_client(client, "p05_viewer", "ViewerPass#12345")
        ha_ov = client.get("/api/v1/home-assistant/overview")
        assert ha_ov.status_code == 200
        assert ha_ov.json()["enabled"] is False
        assert ha_ov.json()["status"] == "unavailable"

        prefs_get = client.get("/api/v1/notifications/preferences")
        assert prefs_get.status_code == 200
        assert prefs_get.json()["telegram_enabled"] is False
        assert prefs_get.json()["telegram_configured"] is False

        assert (
            client.post(
                "/api/v1/home-assistant/collect",
                headers={"X-CSRF-Token": viewer_csrf},
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/v1/notifications/evaluate",
                headers={"X-CSRF-Token": viewer_csrf},
            ).status_code
            == 403
        )

        # Owner: missing CSRF 403, valid CSRF 200, disabled-mode zero network
        owner_csrf = login_client(client, TEST_ADMIN_USERNAME, TEST_ADMIN_PASSWORD)
        assert client.post("/api/v1/home-assistant/collect").status_code == 403
        assert client.post("/api/v1/notifications/evaluate").status_code == 403

        ha_collect = client.post(
            "/api/v1/home-assistant/collect",
            headers={"X-CSRF-Token": owner_csrf},
        )
        assert ha_collect.status_code == 200
        assert ha_collect.json()["enabled"] is False

        prefs_put = client.put(
            "/api/v1/notifications/preferences",
            json={
                "telegram_enabled": True,
                "min_severity": "critical",
                "notify_on_resolve": False,
                "cooldown_seconds": 300,
                "rate_limit_count": 5,
                "rate_limit_window_seconds": 120,
            },
            headers={"X-CSRF-Token": owner_csrf},
        )
        assert prefs_put.status_code == 200
        assert prefs_put.json()["min_severity"] == "critical"
        assert prefs_put.json()["telegram_configured"] is False

        eval_resp = client.post(
            "/api/v1/notifications/evaluate",
            headers={"X-CSRF-Token": owner_csrf},
        )
        assert eval_resp.status_code == 200
        assert eval_resp.json()["enqueued"] == 0

        deliv_resp = client.get("/api/v1/notifications/deliveries?limit=10&offset=0")
        assert deliv_resp.status_code == 200
        assert deliv_resp.json() == []
