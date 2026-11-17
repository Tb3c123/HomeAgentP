"""Tests for task lifecycle, restart persistence, F03 backup/restore, and migration atomicity."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tests.core.conftest import TEST_ADMIN_PASSWORD, TEST_ADMIN_USERNAME

from homeagentp_core.config import Settings
from homeagentp_core.db.connection import (
    BackupError,
    backup_sqlite_database,
    create_connection,
    restore_sqlite_database,
    verify_sqlite_integrity,
)
from homeagentp_core.db.migrator import apply_migrations
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
    app1 = create_app(isolated_env)
    with TestClient(app1) as client1:
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

    # Simulate full service restart with a brand new app instance against the same SQLite file
    app2 = create_app(isolated_env)
    with TestClient(app2) as client2:
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


def test_backup_interruption_never_publishes_incomplete_file_and_restore_roundtrip(
    isolated_env: Settings, tmp_path: Path
) -> None:
    """Verify F03: Interrupted backup cleans up temp files and preserves target backup."""
    app = create_app(isolated_env)
    with TestClient(app) as client:
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
        )
        csrf = login_resp.json()["csrf_token"]
        create_resp = client.post(
            "/api/v1/tasks",
            headers={"X-CSRF-Token": csrf},
            json={
                "title": "Task preserved in atomic backup",
                "category": "security",
                "status": "done",
                "priority": "critical",
            },
        )
        assert create_resp.status_code == 201
        preserved_task_id = create_resp.json()["id"]

    backups_dir = tmp_path / "backups"
    target_backup = backups_dir / "homeagentp_backup.db"

    def abort_mid_backup(status: int, remaining: int, total: int) -> None:
        raise RuntimeError("Simulated disk or I/O interruption during backup")

    # 1. Interrupted backup when no prior backup exists -> target_backup must NOT exist
    with pytest.raises(BackupError, match="aborted cleanly"):
        backup_sqlite_database(
            isolated_env.db_path,
            target_backup,
            progress=abort_mid_backup,
        )
    assert not target_backup.exists()
    assert list(backups_dir.glob("*.tmp")) == []

    # 2. Successful atomic backup -> verified integrity
    backup_sqlite_database(isolated_env.db_path, target_backup)
    assert target_backup.exists()
    verify_sqlite_integrity(target_backup)
    original_bytes = target_backup.read_bytes()

    # 3. Subsequent interrupted backup -> existing valid backup must NOT be overwritten
    with pytest.raises(BackupError, match="aborted cleanly"):
        backup_sqlite_database(
            isolated_env.db_path,
            target_backup,
            progress=abort_mid_backup,
        )
    assert target_backup.read_bytes() == original_bytes
    assert list(backups_dir.glob("*.tmp")) == []

    # 4. Restore into an isolated DB path and boot a fresh app to verify full state recovery
    restored_db_path = tmp_path / "restored" / "homeagentp_restored.db"
    restore_sqlite_database(target_backup, restored_db_path)
    verify_sqlite_integrity(restored_db_path)

    restored_settings = isolated_env.model_copy(update={"db_path": restored_db_path})
    restored_app = create_app(restored_settings)
    with TestClient(restored_app) as restored_client:
        login_restored = restored_client.post(
            "/api/v1/auth/login",
            json={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
        )
        assert login_restored.status_code == 200
        task_resp = restored_client.get(f"/api/v1/tasks/{preserved_task_id}")
        assert task_resp.status_code == 200
        assert task_resp.json()["title"] == "Task preserved in atomic backup"


def test_migration_atomicity_rolls_back_partial_ddl_on_failure(tmp_path: Path) -> None:
    """Verify Item 6: Multi-statement migration failure rolls back all DDL in that file."""
    mig_dir = tmp_path / "migrations"
    mig_dir.mkdir()
    (mig_dir / "001_ok.sql").write_text(
        "CREATE TABLE baseline_items (id INTEGER PRIMARY KEY, name TEXT NOT NULL);",
        encoding="utf-8",
    )
    (mig_dir / "002_broken.sql").write_text(
        """
        CREATE TABLE partial_should_rollback (id INTEGER PRIMARY KEY);
        INSERT INTO non_existent_table_xyz VALUES (1);
        """,
        encoding="utf-8",
    )

    conn = create_connection(tmp_path / "atomic_mig.db")
    try:
        with pytest.raises(sqlite3.OperationalError):
            apply_migrations(conn, mig_dir)

        # 001_ok must be committed, but 002_broken and partial_should_rollback must be rolled back
        versions = [
            str(r["version"])
            for r in conn.execute("SELECT version FROM schema_migrations").fetchall()
        ]
        assert versions == ["001_ok"]

        tables = {
            str(r[0])
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert "baseline_items" in tables
        assert "partial_should_rollback" not in tables
    finally:
        conn.close()
