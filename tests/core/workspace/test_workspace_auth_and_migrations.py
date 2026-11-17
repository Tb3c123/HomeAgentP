"""Migration 004, RBAC (owner vs viewer), CSRF, and backward-compatibility tests."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from tests.core.conftest import TEST_ADMIN_PASSWORD, TEST_ADMIN_USERNAME
from tests.core.workspace.conftest import (
    create_viewer_user,
    login_client,
    make_workspace_settings,
)

from homeagentp_core.db.connection import db_session
from homeagentp_core.db.migrator import apply_migrations
from homeagentp_core.main import create_app


def test_migration_004_idempotency_and_restart_persistence(tmp_path: Path) -> None:
    settings = make_workspace_settings(tmp_path, db_name="mig004.db")
    app = create_app(settings)
    with TestClient(app) as client:
        csrf = login_client(client, TEST_ADMIN_USERNAME, TEST_ADMIN_PASSWORD)
        task_resp = client.post(
            "/api/v1/tasks",
            json={
                "title": "Compat task",
                "task_brief_md": "Legacy flat brief",
                "git_branch": "feature/compat",
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert task_resp.status_code == 201
        task_id = task_resp.json()["id"]
        assert task_resp.json()["task_brief_md"] == "Legacy flat brief"

        brief_resp = client.post(
            f"/api/v1/workspace/tasks/{task_id}/briefs",
            json={"purpose": "Persist structured brief across restart"},
            headers={"X-CSRF-Token": csrf},
        )
        assert brief_resp.status_code == 201

    # Re-run migrations explicitly to confirm idempotency
    with db_session(settings.db_path) as conn:
        second_run = apply_migrations(conn)
        assert second_run == []

    # Simulate service restart with a fresh app instance
    restarted_app = create_app(settings)
    with TestClient(restarted_app) as client:
        login_client(client, TEST_ADMIN_USERNAME, TEST_ADMIN_PASSWORD)
        briefs_resp = client.get(f"/api/v1/workspace/tasks/{task_id}/briefs")
        assert briefs_resp.status_code == 200
        assert len(briefs_resp.json()) == 1
        assert briefs_resp.json()[0]["purpose"] == "Persist structured brief across restart"


def test_workspace_auth_csrf_and_owner_viewer_rbac(tmp_path: Path) -> None:
    settings = make_workspace_settings(tmp_path, db_name="rbac.db")
    app = create_app(settings)

    with TestClient(app) as client:
        # Unauthenticated requests must fail with 401
        assert client.get("/api/v1/workspace/tasks/1/briefs").status_code == 401
        assert (
            client.post("/api/v1/workspace/tasks/1/briefs", json={"purpose": "x"}).status_code
            == 401
        )
        assert client.get("/api/v1/workspace/artifacts").status_code == 401
        assert (
            client.post(
                "/api/v1/workspace/artifacts", json={"slug": "a", "title": "A"}
            ).status_code
            == 401
        )

        owner_csrf = login_client(client, TEST_ADMIN_USERNAME, TEST_ADMIN_PASSWORD)
        task_id = client.post(
            "/api/v1/tasks",
            json={"title": "RBAC task"},
            headers={"X-CSRF-Token": owner_csrf},
        ).json()["id"]

        # Missing CSRF on owner write must fail with 403
        no_csrf = client.post(
            f"/api/v1/workspace/tasks/{task_id}/briefs",
            json={"purpose": "No CSRF"},
        )
        assert no_csrf.status_code == 403

        # Owner creates brief v1 and artifact
        assert (
            client.post(
                f"/api/v1/workspace/tasks/{task_id}/briefs",
                json={"purpose": "Owner created brief"},
                headers={"X-CSRF-Token": owner_csrf},
            ).status_code
            == 201
        )
        assert (
            client.post(
                "/api/v1/workspace/artifacts",
                json={"slug": "rbac-note", "title": "RBAC Note", "source_type": "note"},
                headers={"X-CSRF-Token": owner_csrf},
            ).status_code
            == 201
        )

    # Create a viewer account and verify read-only enforcement even WITH valid CSRF
    create_viewer_user(settings.db_path, "viewer_user", "ViewerPass123!")
    with TestClient(app) as viewer_client:
        viewer_csrf = login_client(viewer_client, "viewer_user", "ViewerPass123!")

        assert viewer_client.get(f"/api/v1/workspace/tasks/{task_id}/briefs").status_code == 200
        assert (
            viewer_client.get(
                f"/api/v1/workspace/tasks/{task_id}/briefs/1/export"
            ).status_code
            == 200
        )
        assert viewer_client.get("/api/v1/workspace/artifacts").status_code == 200
        assert viewer_client.get("/api/v1/workspace/artifacts/rbac-note").status_code == 200

        blocked_brief = viewer_client.post(
            f"/api/v1/workspace/tasks/{task_id}/briefs",
            json={"purpose": "Viewer must not write"},
            headers={"X-CSRF-Token": viewer_csrf},
        )
        assert blocked_brief.status_code == 403
        assert "Owner role required" in blocked_brief.json()["detail"]

        blocked_artifact = viewer_client.post(
            "/api/v1/workspace/artifacts",
            json={"slug": "viewer-art", "title": "Viewer Art", "source_type": "note"},
            headers={"X-CSRF-Token": viewer_csrf},
        )
        assert blocked_artifact.status_code == 403
        assert "Owner role required" in blocked_artifact.json()["detail"]
