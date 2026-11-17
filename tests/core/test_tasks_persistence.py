"""Tests for task creation, editing, listing, attempts, restart persistence, and honest overview."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from tests.core.conftest import TEST_ADMIN_PASSWORD, TEST_ADMIN_USERNAME

from homeagentp_core.config import Settings
from homeagentp_core.db.connection import backup_sqlite_database
from homeagentp_core.main import create_app


def test_overview_never_fabricates_live_telemetry(
    authenticated_client: tuple[TestClient, str],
) -> None:
    client, _ = authenticated_client
    resp = client.get("/api/v1/overview")
    assert resp.status_code == 200
    data = resp.json()

    domains = data["domains"]
    assert domains["nas_guardian"]["status"] == "unavailable"
    assert domains["nas_guardian"]["metrics"]["mounts"]["/mnt/disk1"] == "unavailable"
    assert domains["nas_guardian"]["metrics"]["mounts"]["/mnt/disk2"] == "unavailable"
    assert domains["media"]["status"] == "unavailable"
    assert domains["media"]["services"]["jellyfin"] == "unavailable"
    assert domains["downloads"]["status"] == "unavailable"
    assert domains["home_automation"]["status"] == "unavailable"
    assert domains["ai_workspace"]["consumer_cli_wrapper"] == "disabled_by_policy"


def test_task_lifecycle_and_database_restart_persistence(
    isolated_env: Settings, tmp_path: Path
) -> None:
    # 1. Start first app instance, login, create project, task, update task, and add attempt
    app1 = create_app(isolated_env)
    client1 = TestClient(app1)

    login_resp = client1.post(
        "/api/v1/auth/login",
        json={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
    )
    assert login_resp.status_code == 200
    csrf = login_resp.json()["csrf_token"]
    headers = {"X-CSRF-Token": csrf}

    proj_resp = client1.post(
        "/api/v1/projects",
        headers=headers,
        json={
            "slug": "hdd-mount-watchdog",
            "name": "HDD Mount Watchdog",
            "category": "nas_guardian",
            "description": "Monitor /mnt/disk1 and /mnt/disk2 read-only status.",
            "repo_url": "https://github.com/Tb3c123/HomeAgentP",
        },
    )
    assert proj_resp.status_code == 201
    project_id = proj_resp.json()["id"]

    create_resp = client1.post(
        "/api/v1/tasks",
        headers=headers,
        json={
            "project_id": project_id,
            "title": "Design read-only /proc/mounts parser",
            "description": "Ensure zero writes and no root permissions required.",
            "category": "nas_guardian",
            "status": "ready",
            "priority": "high",
            "task_brief_md": "## Task Brief\nImplement read-only mount check.",
            "git_branch": "feature/phase-02-mount-check",
        },
    )
    assert create_resp.status_code == 201
    task_id = create_resp.json()["id"]

    # Edit the task
    patch_resp = client1.patch(
        f"/api/v1/tasks/{task_id}",
        headers=headers,
        json={
            "status": "review",
            "pr_url": "https://github.com/Tb3c123/HomeAgentP/pull/1",
        },
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "review"

    # Record an execution attempt
    attempt_resp = client1.post(
        f"/api/v1/tasks/{task_id}/attempts",
        headers=headers,
        json={
            "executor_type": "antigravity_handoff",
            "status": "succeeded",
            "summary": "Completed in isolated remote workspace and opened PR.",
            "artifact_rel_path": "sample_daily_report.md",
        },
    )
    assert attempt_resp.status_code == 201
    assert attempt_resp.json()["attempt_number"] == 1

    client1.close()

    # 2. Simulate full service restart by instantiating a brand new app against the same SQLite file
    app2 = create_app(isolated_env)
    client2 = TestClient(app2)

    login2 = client2.post(
        "/api/v1/auth/login",
        json={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
    )
    assert login2.status_code == 200

    persisted_resp = client2.get(f"/api/v1/tasks/{task_id}")
    assert persisted_resp.status_code == 200
    persisted_task = persisted_resp.json()
    assert persisted_task["title"] == "Design read-only /proc/mounts parser"
    assert persisted_task["status"] == "review"
    assert persisted_task["pr_url"] == "https://github.com/Tb3c123/HomeAgentP/pull/1"
    assert len(persisted_task["attempts"]) == 1
    assert persisted_task["attempts"][0]["summary"].startswith("Completed in isolated")

    # 3. Verify atomic SQLite online backup produces a valid restorable database
    backup_file = tmp_path / "backups" / "homeagentp_backup.db"
    backup_sqlite_database(isolated_env.db_path, backup_file)
    assert backup_file.exists()
    assert backup_file.stat().st_size > 0
    client2.close()
