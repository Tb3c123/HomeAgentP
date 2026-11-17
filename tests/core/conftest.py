"""Shared Pytest fixtures for HomeAgentP Core tests."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from homeagentp_core.config import Settings
from homeagentp_core.main import create_app

TEST_SECRET_KEY = "test_secret_key_for_isolated_pytest_suite_32b"  # noqa: S105
TEST_ADMIN_USERNAME = "nas_owner"
TEST_ADMIN_PASSWORD = "StrongTestPassword!2026"  # noqa: S105


@pytest.fixture
def isolated_env(tmp_path: Path) -> Settings:
    """Create isolated directories, sample scripts/reports, and SQLite DB path in tmp_path."""
    scripts_dir = tmp_path / "scripts"
    reports_dir = tmp_path / "reports"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    script_content = "#!/usr/bin/env bash\necho 'Read-only NAS disk check'\ndf -h\n"
    script_file = scripts_dir / "disk_usage_report.sh"
    script_file.write_text(script_content, encoding="utf-8")
    script_sha256 = hashlib.sha256(script_content.encode("utf-8")).hexdigest()

    manifest = {
        "version": "1.0",
        "execution_policy": "disabled_in_phase_01",
        "scripts": [
            {
                "slug": "disk-usage-report",
                "name": "NAS Disk Usage Snapshot",
                "description": "Inspect filesystem usage safely.",
                "rel_path": "disk_usage_report.sh",
                "sha256": script_sha256,
                "review_status": "allowlisted",
                "category": "nas_guardian",
            }
        ],
    }
    (scripts_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    report_content = "# Daily NAS Report\n\nAll mounts verified in staging.\n"
    (reports_dir / "sample_daily_report.md").write_text(report_content, encoding="utf-8")

    return Settings(
        env="testing",
        db_path=tmp_path / "test_homeagentp.db",
        secret_key=TEST_SECRET_KEY,
        admin_username=TEST_ADMIN_USERNAME,
        admin_password=TEST_ADMIN_PASSWORD,
        scripts_dir=scripts_dir,
        reports_dir=reports_dir,
        seed_examples=True,
    )


@pytest.fixture
def client(isolated_env: Settings) -> Iterator[TestClient]:
    """Return a FastAPI TestClient entered via context manager so lifespan runs once (F04)."""
    app = create_app(isolated_env)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def authenticated_client(client: TestClient) -> tuple[TestClient, str]:
    """Authenticate as admin and return (client, csrf_token)."""
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
    )
    assert resp.status_code == 200
    csrf_token = str(resp.json()["csrf_token"])
    return client, csrf_token
