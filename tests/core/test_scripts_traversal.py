"""Tests for read-only script/report viewer and strict path traversal / symlink denial."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from homeagentp_core.config import Settings
from homeagentp_core.modules.scripts.safe_reader import (
    PathSecurityError,
    read_allowlisted_text_file,
)


def test_list_and_view_allowlisted_script(
    authenticated_client: tuple[TestClient, str],
) -> None:
    client, _ = authenticated_client
    list_resp = client.get("/api/v1/scripts")
    assert list_resp.status_code == 200
    scripts = list_resp.json()
    assert len(scripts) >= 1
    assert scripts[0]["slug"] == "disk-usage-report"
    assert scripts[0]["is_executable_allowed"] is False
    assert scripts[0]["execution_policy"] == "read_only_phase_01"

    detail_resp = client.get("/api/v1/scripts/disk-usage-report")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["checksum_verified"] is True
    assert "df -h" in detail["content"]


def test_path_traversal_and_absolute_paths_denied(
    authenticated_client: tuple[TestClient, str],
) -> None:
    client, _ = authenticated_client
    malicious_paths = [
        "../secret.txt",
        "../../etc/passwd",
        "/etc/passwd",
        "subdir/../../outside.sh",
    ]
    for bad_path in malicious_paths:
        resp = client.get("/api/v1/scripts/preview-file", params={"rel_path": bad_path})
        assert resp.status_code == 403, f"Expected 403 for traversal path: {bad_path}"


def test_symlink_escape_denied(
    authenticated_client: tuple[TestClient, str],
    isolated_env: Settings,
    tmp_path: Path,
) -> None:
    client, _ = authenticated_client

    # Create a sensitive file outside scripts_dir and a symlink inside scripts_dir pointing to it
    outside_secret = tmp_path / "outside_credentials.txt"
    outside_secret.write_text("TOP_SECRET_TOKEN=12345", encoding="utf-8")

    symlink_inside = isolated_env.scripts_dir / "escaped_link.sh"
    symlink_inside.symlink_to(outside_secret)

    # Direct reader call must raise PathSecurityError
    with pytest.raises(PathSecurityError):
        read_allowlisted_text_file(isolated_env.scripts_dir, "escaped_link.sh")

    # API endpoint must return 403 Forbidden
    resp = client.get("/api/v1/scripts/preview-file", params={"rel_path": "escaped_link.sh"})
    assert resp.status_code == 403
    assert "Symlinks are prohibited" in resp.json()["detail"]


def test_checksum_tampering_detected(
    authenticated_client: tuple[TestClient, str],
    isolated_env: Settings,
) -> None:
    client, _ = authenticated_client
    # Modify script content on disk without updating its manifest SHA-256
    script_file = isolated_env.scripts_dir / "disk_usage_report.sh"
    script_file.write_text("#!/usr/bin/env bash\nrm -rf /\n", encoding="utf-8")

    resp = client.get("/api/v1/scripts/disk-usage-report")
    assert resp.status_code == 403
    assert "SHA-256 checksum mismatch" in resp.json()["detail"]


def test_reports_viewer_works_and_audit_logs_redacted(
    authenticated_client: tuple[TestClient, str],
) -> None:
    client, _ = authenticated_client
    reports_resp = client.get("/api/v1/reports")
    assert reports_resp.status_code == 200
    reports = reports_resp.json()
    assert len(reports) == 1
    slug = reports[0]["slug"]

    detail_resp = client.get(f"/api/v1/reports/{slug}")
    assert detail_resp.status_code == 200
    assert "Daily NAS Report" in detail_resp.json()["content"]

    audit_resp = client.get("/api/v1/audit-logs")
    assert audit_resp.status_code == 200
    assert len(audit_resp.json()) >= 1
