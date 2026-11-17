"""Tests for P04-F03: Workspace Artifacts & Knowledge Metadata + safe_reader security."""

from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi.testclient import TestClient
from tests.core.conftest import TEST_ADMIN_PASSWORD, TEST_ADMIN_USERNAME
from tests.core.workspace.conftest import login_client, make_workspace_settings

from homeagentp_core.main import create_app


def test_workspace_artifact_revisions_filtering_and_safe_preview(tmp_path: Path) -> None:
    settings = make_workspace_settings(tmp_path, db_name="artifacts.db")
    report_v1 = settings.reports_dir / "phase03-summary.md"
    report_v1.write_text("# Phase 03 Summary v1\nAll checks green.\n", encoding="utf-8")
    expected_sha_v1 = hashlib.sha256(report_v1.read_bytes()).hexdigest()

    app = create_app(settings)
    with TestClient(app) as client:
        csrf = login_client(client, TEST_ADMIN_USERNAME, TEST_ADMIN_PASSWORD)
        proj_id = client.post(
            "/api/v1/projects",
            json={
                "slug": "homeagentp-core",
                "name": "HomeAgentP Core",
                "category": "ai_workspace",
            },
            headers={"X-CSRF-Token": csrf},
        ).json()["id"]
        task_id = client.post(
            "/api/v1/tasks",
            json={"project_id": proj_id, "title": "Publish staging report"},
            headers={"X-CSRF-Token": csrf},
        ).json()["id"]

        r1 = client.post(
            "/api/v1/workspace/artifacts",
            json={
                "slug": "phase03-staging-summary",
                "version": "1.0.0",
                "title": "Phase 03 Staging Summary",
                "kind": "artifact",
                "source_type": "allowlisted_report",
                "rel_path": "phase03-summary.md",
                "expected_sha256": expected_sha_v1,
                "summary": "Initial staging verification",
                "tags": ["phase-03", "staging"],
                "project_id": proj_id,
                "task_id": task_id,
                "expected_latest_revision": 0,
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert r1.status_code == 201
        assert r1.json()["revision"] == 1
        assert r1.json()["sha256"] == expected_sha_v1

        # Duplicate version string on same slug must fail with 409
        dup_ver = client.post(
            "/api/v1/workspace/artifacts",
            json={
                "slug": "phase03-staging-summary",
                "version": "1.0.0",
                "title": "Duplicate",
                "source_type": "note",
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert dup_ver.status_code == 409

        # Register immutable revision 2 (note)
        r2 = client.post(
            "/api/v1/workspace/artifacts",
            json={
                "slug": "phase03-staging-summary",
                "version": "1.1.0",
                "title": "Phase 03 Staging Summary (Updated)",
                "kind": "knowledge",
                "source_type": "note",
                "summary": "Follow-up notes",
                "tags": ["phase-03", "knowledge"],
                "project_id": proj_id,
                "task_id": task_id,
                "expected_latest_revision": 1,
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert r2.status_code == 201
        assert r2.json()["revision"] == 2

        # List defaults to latest revision only
        listed = client.get("/api/v1/workspace/artifacts?tag=phase-03").json()
        assert len(listed) == 1
        assert listed[0]["revision"] == 2

        # include_history=true returns both revisions
        all_hist = client.get("/api/v1/workspace/artifacts?include_history=true").json()
        assert len(all_hist) == 2

        # Versions endpoint lists all historical revisions
        vers = client.get("/api/v1/workspace/artifacts/phase03-staging-summary/versions").json()
        assert [v["revision"] for v in vers] == [2, 1]

        # Preview historical revision 1 verifies SHA-256 and returns content
        rev1_detail = client.get(
            "/api/v1/workspace/artifacts/phase03-staging-summary?revision=1"
        )
        assert rev1_detail.status_code == 200
        assert rev1_detail.json()["checksum_verified"] is True
        assert "All checks green." in rev1_detail.json()["content"]

        # Tamper with file on disk -> preview of revision 1 must fail closed with 403
        report_v1.write_text("# Tampered content\n", encoding="utf-8")
        tampered = client.get(
            "/api/v1/workspace/artifacts/phase03-staging-summary?revision=1"
        )
        assert tampered.status_code == 403


def test_workspace_artifact_security_traversal_symlink_size_and_urls(tmp_path: Path) -> None:
    settings = make_workspace_settings(tmp_path, db_name="art_sec.db")
    outside = tmp_path / "outside.txt"
    outside.write_text("SECRET_OUTSIDE", encoding="utf-8")
    symlink_file = settings.scripts_dir / "escape.sh"
    symlink_file.symlink_to(outside)

    oversized = settings.reports_dir / "huge.log"
    oversized.write_bytes(b"A" * (300 * 1024))

    app = create_app(settings)
    with TestClient(app) as client:
        csrf = login_client(client, TEST_ADMIN_USERNAME, TEST_ADMIN_PASSWORD)

        # Traversal rejected
        assert (
            client.post(
                "/api/v1/workspace/artifacts",
                json={
                    "slug": "trav-test",
                    "title": "Traversal",
                    "source_type": "allowlisted_script",
                    "rel_path": "../outside.txt",
                },
                headers={"X-CSRF-Token": csrf},
            ).status_code
            == 403
        )

        # Symlink rejected
        assert (
            client.post(
                "/api/v1/workspace/artifacts",
                json={
                    "slug": "sym-test",
                    "title": "Symlink",
                    "source_type": "allowlisted_script",
                    "rel_path": "escape.sh",
                },
                headers={"X-CSRF-Token": csrf},
            ).status_code
            == 403
        )

        # Oversized file rejected
        assert (
            client.post(
                "/api/v1/workspace/artifacts",
                json={
                    "slug": "huge-test",
                    "title": "Oversized",
                    "source_type": "allowlisted_report",
                    "rel_path": "huge.log",
                },
                headers={"X-CSRF-Token": csrf},
            ).status_code
            == 403
        )

        # Invalid git_reference URLs rejected; valid https://github.com accepted
        for bad_url in (
            "http://github.com/Tb3c123/HomeAgentP",
            "https://evil.example.com/Tb3c123/HomeAgentP",
            "javascript:alert(1)",
            "https://user:pass@github.com/Tb3c123/HomeAgentP",
        ):
            assert (
                client.post(
                    "/api/v1/workspace/artifacts",
                    json={
                        "slug": "bad-git",
                        "title": "Bad Git",
                        "source_type": "git_reference",
                        "git_url": bad_url,
                    },
                    headers={"X-CSRF-Token": csrf},
                ).status_code
                == 400
            )

        good_git = client.post(
            "/api/v1/workspace/artifacts",
            json={
                "slug": "good-git",
                "title": "Phase 04 Design Doc",
                "kind": "plan",
                "source_type": "git_reference",
                "git_url": "https://github.com/Tb3c123/HomeAgentP/blob/main/README.md",
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert good_git.status_code == 201
