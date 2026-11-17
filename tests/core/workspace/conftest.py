"""Shared helpers for Phase 04 Workspace test suites."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from tests.core.conftest import TEST_ADMIN_PASSWORD, TEST_ADMIN_USERNAME, TEST_SECRET_KEY

from homeagentp_core.auth.security import hash_password
from homeagentp_core.config import Settings
from homeagentp_core.db.connection import db_session


def make_workspace_settings(tmp_path: Path, db_name: str = "workspace.db") -> Settings:
    scripts_dir = tmp_path / "scripts"
    reports_dir = tmp_path / "reports"
    scripts_dir.mkdir(exist_ok=True)
    reports_dir.mkdir(exist_ok=True)
    return Settings(
        env="testing",
        db_path=tmp_path / db_name,
        secret_key=TEST_SECRET_KEY,
        admin_username=TEST_ADMIN_USERNAME,
        admin_password=TEST_ADMIN_PASSWORD,
        scripts_dir=scripts_dir,
        reports_dir=reports_dir,
        seed_examples=False,
    )


def create_viewer_user(db_path: Path, username: str, password: str) -> None:
    with db_session(db_path) as conn:
        conn.execute(
            """
            INSERT INTO users (username, password_hash, role, is_active, created_at)
            VALUES (?, ?, 'viewer', 1, ?)
            """,
            (username, hash_password(password), datetime.now(UTC).isoformat()),
        )


def login_client(client: TestClient, username: str, password: str) -> str:
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200
    return str(resp.json()["csrf_token"])
