"""Tests for authentication, CSRF, F01 audit persistence, and F04 lifespan."""

from __future__ import annotations

from fastapi.testclient import TestClient
from tests.core.conftest import TEST_ADMIN_PASSWORD, TEST_ADMIN_USERNAME

from homeagentp_core.config import Settings
from homeagentp_core.db.connection import db_session


def test_lifespan_initializes_core_state_once(client: TestClient) -> None:
    """Verify F04: initialize_core_state runs exactly once during lifespan startup."""
    assert getattr(client.app.state, "init_count", 0) == 1


def test_health_endpoint_is_public(client: TestClient) -> None:
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "homeagentp-core"
    assert data["schema_version"] == "005_home_assistant_telegram"


def test_private_endpoints_require_authentication(client: TestClient) -> None:
    for path in (
        "/api/v1/overview",
        "/api/v1/settings",
        "/api/v1/projects",
        "/api/v1/tasks",
        "/api/v1/scripts",
        "/api/v1/reports",
        "/api/v1/audit-logs",
        "/api/v1/auth/me",
    ):
        resp = client.get(path)
        assert resp.status_code == 401, f"Expected 401 for unauthenticated GET {path}"


def test_login_failure_records_audit_and_persists_after_401(
    client: TestClient,
    isolated_env: Settings,
) -> None:
    """Verify F01: Failed login raises 401 AFTER committing auth.login_failed to audit_logs."""
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": TEST_ADMIN_USERNAME, "password": "wrong-password"},
    )
    assert resp.status_code == 401

    unknown_resp = client.post(
        "/api/v1/auth/login",
        json={"username": "intruder_user", "password": "wrong-password"},
    )
    assert unknown_resp.status_code == 401

    # Verify directly in SQLite that both auth.login_failed audit rows were committed
    with db_session(isolated_env.db_path) as conn:
        failed_rows = conn.execute(
            "SELECT actor, action, details_json FROM audit_logs "
            "WHERE action = 'auth.login_failed' ORDER BY id ASC"
        ).fetchall()
        assert len(failed_rows) == 2
        actors = [str(r["actor"]) for r in failed_rows]
        assert TEST_ADMIN_USERNAME in actors
        assert "intruder_user" in actors


def test_expired_session_is_deleted_and_committed(
    client: TestClient,
    isolated_env: Settings,
) -> None:
    """Verify expired session cleanup is committed before raising 401."""
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
    )
    assert login_resp.status_code == 200

    # Backdate the session expiration in SQLite
    with db_session(isolated_env.db_path) as conn:
        conn.execute("UPDATE sessions SET expires_at = '2000-01-01T00:00:00+00:00'")

    me_resp = client.get("/api/v1/auth/me")
    assert me_resp.status_code == 401
    assert me_resp.json()["detail"] == "Session expired."

    # Verify the expired session row was actually deleted from SQLite
    with db_session(isolated_env.db_path) as conn:
        remaining = int(conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0])
        assert remaining == 0


def test_login_csrf_and_logout_lifecycle(client: TestClient) -> None:
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
    )
    assert login_resp.status_code == 200
    body = login_resp.json()
    assert body["username"] == TEST_ADMIN_USERNAME
    assert body["role"] == "owner"
    csrf_token = body["csrf_token"]
    assert len(csrf_token) >= 16

    me_resp = client.get("/api/v1/auth/me")
    assert me_resp.status_code == 200
    assert me_resp.json()["username"] == TEST_ADMIN_USERNAME

    no_csrf_resp = client.post(
        "/api/v1/tasks",
        json={"title": "Unauthorized CSRF task", "category": "nas_guardian"},
    )
    assert no_csrf_resp.status_code == 403

    logout_resp = client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert logout_resp.status_code == 200

    after_logout = client.get("/api/v1/overview")
    assert after_logout.status_code == 401
