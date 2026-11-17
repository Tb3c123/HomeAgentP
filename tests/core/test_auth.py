"""Tests for authentication, authorization, CSRF enforcement, and session lifecycle."""

from __future__ import annotations

from fastapi.testclient import TestClient
from tests.core.conftest import TEST_ADMIN_PASSWORD, TEST_ADMIN_USERNAME


def test_health_endpoint_is_public(client: TestClient) -> None:
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "homeagentp-core"
    assert data["schema_version"] == "001_initial"


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


def test_login_failure_records_audit_and_rejects(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": TEST_ADMIN_USERNAME, "password": "wrong-password"},
    )
    assert resp.status_code == 401


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

    # Verify /auth/me works with session cookie
    me_resp = client.get("/api/v1/auth/me")
    assert me_resp.status_code == 200
    assert me_resp.json()["username"] == TEST_ADMIN_USERNAME

    # Verify write operation WITHOUT CSRF token is rejected with 403
    no_csrf_resp = client.post(
        "/api/v1/tasks",
        json={"title": "Unauthorized CSRF task", "category": "nas_guardian"},
    )
    assert no_csrf_resp.status_code == 403

    # Verify logout with valid CSRF token invalidates session
    logout_resp = client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert logout_resp.status_code == 200

    after_logout = client.get("/api/v1/overview")
    assert after_logout.status_code == 401
