"""Tests for P04-F04: Git Provenance links, RBAC, URL validation, and trigger cleanup."""

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
from homeagentp_core.main import create_app


def test_git_provenance_crud_rbac_and_verification_source(tmp_path: Path) -> None:
    settings = make_workspace_settings(tmp_path, db_name="prov.db")
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/api/v1/workspace/provenance").status_code == 401

        csrf = login_client(client, TEST_ADMIN_USERNAME, TEST_ADMIN_PASSWORD)
        task_id = client.post(
            "/api/v1/tasks",
            json={"title": "Provenance task"},
            headers={"X-CSRF-Token": csrf},
        ).json()["id"]
        art_id = client.post(
            "/api/v1/workspace/artifacts",
            json={"slug": "prov-art", "title": "Provenance Artifact", "source_type": "note"},
            headers={"X-CSRF-Token": csrf},
        ).json()["id"]

        # Non-existent entity -> 404
        missing_target = client.post(
            "/api/v1/workspace/provenance",
            json={
                "entity_type": "task",
                "entity_id": 9999,
                "repo_url": "https://github.com/Tb3c123/HomeAgentP",
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert missing_target.status_code == 404

        # Create provenance link for task
        created = client.post(
            "/api/v1/workspace/provenance",
            json={
                "entity_type": "task",
                "entity_id": task_id,
                "repo_url": "https://github.com/Tb3c123/HomeAgentP",
                "branch": "feature/phase-04-workspace-artifacts",
                "commit_sha": "D92315A",
                "pr_url": "https://github.com/Tb3c123/HomeAgentP/pull/4",
                "review_status": "pending",
                "ci_status": "success",
                "ci_url": "https://github.com/Tb3c123/HomeAgentP/actions/runs/44088968720",
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert created.status_code == 201
        link = created.json()
        assert link["verification_source"] == "manual_unverified"
        assert link["commit_sha"] == "d92315a"

        # Create provenance link for artifact
        art_link = client.post(
            "/api/v1/workspace/provenance",
            json={
                "entity_type": "artifact",
                "entity_id": art_id,
                "repo_url": "https://github.com/Tb3c123/HomeAgentP",
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert art_link.status_code == 201

        # Update task provenance link
        updated = client.patch(
            f"/api/v1/workspace/provenance/{link['id']}",
            json={"review_status": "approved", "ci_status": "success"},
            headers={"X-CSRF-Token": csrf},
        )
        assert updated.status_code == 200
        assert updated.json()["review_status"] == "approved"
        assert updated.json()["verification_source"] == "manual_unverified"

        # Verify audit logs recorded create and update
        logs = client.get("/api/v1/audit-logs?limit=20").json()
        actions = {entry["action"] for entry in logs}
        assert "workspace.provenance.create" in actions
        assert "workspace.provenance.update" in actions

    # Viewer can GET provenance, but receives 403 on POST/PATCH even with valid CSRF
    create_viewer_user(settings.db_path, "prov_viewer", "ViewerPass123!")
    with TestClient(app) as v_client:
        v_csrf = login_client(v_client, "prov_viewer", "ViewerPass123!")
        assert (
            v_client.get(
                f"/api/v1/workspace/provenance?entity_type=task&entity_id={task_id}"
            ).status_code
            == 200
        )
        assert (
            v_client.post(
                "/api/v1/workspace/provenance",
                json={
                    "entity_type": "task",
                    "entity_id": task_id,
                    "repo_url": "https://github.com/Tb3c123/HomeAgentP",
                },
                headers={"X-CSRF-Token": v_csrf},
            ).status_code
            == 403
        )
        assert (
            v_client.patch(
                f"/api/v1/workspace/provenance/{link['id']}",
                json={"review_status": "approved"},
                headers={"X-CSRF-Token": v_csrf},
            ).status_code
            == 403
        )


def test_git_provenance_url_validation_and_delete_cleanup(tmp_path: Path) -> None:
    settings = make_workspace_settings(tmp_path, db_name="prov_sec.db")
    app = create_app(settings)
    with TestClient(app) as client:
        csrf = login_client(client, TEST_ADMIN_USERNAME, TEST_ADMIN_PASSWORD)
        task_id = client.post(
            "/api/v1/tasks",
            json={"title": "Cleanup task"},
            headers={"X-CSRF-Token": csrf},
        ).json()["id"]

        for bad_url in (
            "http://github.com/Tb3c123/HomeAgentP",
            "https://evil.example.com/Tb3c123/HomeAgentP",
            "javascript:alert(1)//github.com/a/b",
            "https://user:pass@github.com/Tb3c123/HomeAgentP",
            "https://github.com/onlyowner",
        ):
            resp = client.post(
                "/api/v1/workspace/provenance",
                json={
                    "entity_type": "task",
                    "entity_id": task_id,
                    "repo_url": bad_url,
                },
                headers={"X-CSRF-Token": csrf},
            )
            assert resp.status_code == 400

        ok = client.post(
            "/api/v1/workspace/provenance",
            json={
                "entity_type": "task",
                "entity_id": task_id,
                "repo_url": "https://github.com/Tb3c123/HomeAgentP",
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert ok.status_code == 201

    # Deleting the task must trigger AFTER DELETE cleanup of orphan provenance rows
    with db_session(settings.db_path) as conn:
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        remaining = conn.execute(
            "SELECT COUNT(*) FROM git_provenance_links WHERE entity_type='task' AND entity_id=?",
            (task_id,),
        ).fetchone()[0]
        assert int(remaining) == 0
