"""Tests for P04-F02: Structured Task Briefs, atomic versioning, conflicts, and secrets."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import HTTPException
from fastapi.testclient import TestClient
from tests.core.conftest import TEST_ADMIN_PASSWORD, TEST_ADMIN_USERNAME
from tests.core.workspace.conftest import login_client, make_workspace_settings

from homeagentp_core.db.connection import db_session
from homeagentp_core.main import create_app
from homeagentp_core.modules.workspace.briefs import create_task_brief
from homeagentp_core.modules.workspace.schemas import TaskBriefCreate


def test_task_brief_versioning_immutability_and_export(tmp_path: Path) -> None:
    settings = make_workspace_settings(tmp_path, db_name="briefs.db")
    app = create_app(settings)
    with TestClient(app) as client:
        csrf = login_client(client, TEST_ADMIN_USERNAME, TEST_ADMIN_PASSWORD)
        task_id = client.post(
            "/api/v1/tasks",
            json={"title": "Implement Phase 04 Gate A", "category": "ai_workspace"},
            headers={"X-CSRF-Token": csrf},
        ).json()["id"]

        v1 = client.post(
            f"/api/v1/workspace/tasks/{task_id}/briefs",
            json={
                "purpose": "Build Task Briefs API",
                "scope": "Backend schemas + SQLite 004",
                "excluded_scope": "No Antigravity CLI invocation",
                "input_references": ["docs/plans/04-gate0-design.md"],
                "acceptance_checks": ["Pytest passes", "Ruff clean"],
                "security_constraints": "Owner-only writes",
                "rollback_plan": "git revert commit",
                "human_status": "ready_for_handoff",
                "expected_latest_version": 0,
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert v1.status_code == 201
        assert v1.json()["version"] == 1

        # Stale expected_latest_version must fail with 409 Conflict
        stale = client.post(
            f"/api/v1/workspace/tasks/{task_id}/briefs",
            json={"purpose": "Stale update", "expected_latest_version": 0},
            headers={"X-CSRF-Token": csrf},
        )
        assert stale.status_code == 409

        # Valid v2 allocation
        v2 = client.post(
            f"/api/v1/workspace/tasks/{task_id}/briefs",
            json={
                "purpose": "Build Task Briefs + Artifacts API",
                "human_status": "handed_off",
                "expected_latest_version": 1,
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert v2.status_code == 201
        assert v2.json()["version"] == 2

        # Historical v1 must remain immutable and intact
        list_resp = client.get(f"/api/v1/workspace/tasks/{task_id}/briefs")
        assert list_resp.status_code == 200
        versions = list_resp.json()
        assert [b["version"] for b in versions] == [2, 1]
        assert versions[1]["purpose"] == "Build Task Briefs API"

        # No PATCH/PUT mutation allowed on historical versions
        assert (
            client.patch(
                f"/api/v1/workspace/tasks/{task_id}/briefs/1",
                json={"purpose": "Mutate"},
                headers={"X-CSRF-Token": csrf},
            ).status_code
            in (404, 405)
        )

        # Deterministic plain-text export for manual Antigravity handoff
        exp = client.get(f"/api/v1/workspace/tasks/{task_id}/briefs/1/export")
        assert exp.status_code == 200
        exp_data = exp.json()
        assert exp_data["handoff_mode"] == "manual_copy_only"
        assert "HomeAgentP Task Brief (Task #" in exp_data["rendered_text"]
        assert "Build Task Briefs API" in exp_data["rendered_text"]
        assert "docs/plans/04-gate0-design.md" in exp_data["rendered_text"]
        assert "- [ ] Pytest passes" in exp_data["rendered_text"]


def test_task_brief_concurrent_version_allocation_and_conflict(tmp_path: Path) -> None:
    settings = make_workspace_settings(tmp_path, db_name="brief_race.db")
    app = create_app(settings)
    with TestClient(app) as client:
        csrf = login_client(client, TEST_ADMIN_USERNAME, TEST_ADMIN_PASSWORD)
        task_id = client.post(
            "/api/v1/tasks",
            json={"title": "Race test task"},
            headers={"X-CSRF-Token": csrf},
        ).json()["id"]

    # Two concurrent callers with expected_latest_version=0: exactly one succeeds, one gets 409
    def _attempt_create(purpose: str, expected: int | None) -> int | str:
        try:
            with db_session(settings.db_path) as conn:
                out = create_task_brief(
                    conn,
                    task_id=task_id,
                    payload=TaskBriefCreate(purpose=purpose, expected_latest_version=expected),
                    actor="admin",
                    ip_address="127.0.0.1",
                )
                return out.version
        except HTTPException as exc:
            return f"http_{exc.status_code}"

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(_attempt_create, "Concurrent A", 0)
        f2 = pool.submit(_attempt_create, "Concurrent B", 0)
        results = sorted([str(f1.result()), str(f2.result())])

    assert results == ["1", "http_409"]

    # Two concurrent callers without expected_latest_version: atomic sequential versions 2 and 3
    with ThreadPoolExecutor(max_workers=2) as pool:
        f3 = pool.submit(_attempt_create, "Concurrent C", None)
        f4 = pool.submit(_attempt_create, "Concurrent D", None)
        seq_results = sorted([int(f3.result()), int(f4.result())])

    assert seq_results == [2, 3]


def test_task_brief_rejects_secrets_with_redacted_errors(tmp_path: Path) -> None:
    settings = make_workspace_settings(tmp_path, db_name="brief_secrets.db")
    app = create_app(settings)
    with TestClient(app) as client:
        csrf = login_client(client, TEST_ADMIN_USERNAME, TEST_ADMIN_PASSWORD)
        task_id = client.post(
            "/api/v1/tasks",
            json={"title": "Secret test task"},
            headers={"X-CSRF-Token": csrf},
        ).json()["id"]

        bad_secrets = [
            ("purpose", "Use token ghp_1234567890abcdefghij1234567890"),
            ("scope", "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc"),
            ("security_constraints", "api_key=super_real_secret_987654321"),
            ("rollback_plan", "https://alice:realpass123@github.com/Tb3c123/HomeAgentP"),
        ]
        for field_name, secret_val in bad_secrets:
            resp = client.post(
                f"/api/v1/workspace/tasks/{task_id}/briefs",
                json={"purpose": "Safe purpose", field_name: secret_val},
                headers={"X-CSRF-Token": csrf},
            )
            assert resp.status_code == 400
            detail = resp.json()["detail"]
            assert field_name in detail
            assert secret_val not in detail


def test_task_brief_rendered_text_secret_and_item_bounds(tmp_path: Path) -> None:
    settings = make_workspace_settings(tmp_path, db_name="brief_bounds.db")
    app = create_app(settings)
    with TestClient(app) as client:
        csrf = login_client(client, TEST_ADMIN_USERNAME, TEST_ADMIN_PASSWORD)

        # Secret embedded in task title must be caught when validating complete rendered_text
        tainted_title = "Task with ghp_1234567890abcdefghij1234567890"
        t_secret = client.post(
            "/api/v1/tasks",
            json={"title": tainted_title},
            headers={"X-CSRF-Token": csrf},
        ).json()["id"]
        resp_rendered = client.post(
            f"/api/v1/workspace/tasks/{t_secret}/briefs",
            json={"purpose": "Clean purpose"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp_rendered.status_code == 400
        assert "rendered_text" in resp_rendered.json()["detail"]
        assert "ghp_" not in resp_rendered.json()["detail"]

        t_ok = client.post(
            "/api/v1/tasks",
            json={"title": "Bounds task"},
            headers={"X-CSRF-Token": csrf},
        ).json()["id"]

        # Oversized single input_reference item (>255 chars) -> 422
        assert (
            client.post(
                f"/api/v1/workspace/tasks/{t_ok}/briefs",
                json={"purpose": "Check bounds", "input_references": ["x" * 256]},
                headers={"X-CSRF-Token": csrf},
            ).status_code
            == 422
        )

        # Oversized serialized input_references (>4096 bytes even with <=20 items of <=255 chars)
        big_refs = [f"{i:02d}_" + ("a" * 240) for i in range(18)]
        assert (
            client.post(
                f"/api/v1/workspace/tasks/{t_ok}/briefs",
                json={"purpose": "Check serialized refs", "input_references": big_refs},
                headers={"X-CSRF-Token": csrf},
            ).status_code
            == 422
        )

        # Oversized serialized acceptance_checks (>8192 bytes even with <=30 items of <=500 chars)
        big_checks = [f"{i:02d}_" + ("b" * 450) for i in range(20)]
        assert (
            client.post(
                f"/api/v1/workspace/tasks/{t_ok}/briefs",
                json={"purpose": "Check serialized checks", "acceptance_checks": big_checks},
                headers={"X-CSRF-Token": csrf},
            ).status_code
            == 422
        )
