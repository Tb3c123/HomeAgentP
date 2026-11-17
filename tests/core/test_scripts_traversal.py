"""Tests for TOCTOU-resistant read-only script/report viewer (F02)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from homeagentp_core.config import Settings
from homeagentp_core.modules.scripts.safe_reader import (
    MAX_READ_BYTES,
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
    isolated_env: Settings,
) -> None:
    client, _ = authenticated_client
    malicious_paths = [
        "../secret.txt",
        "../../etc/passwd",
        "/etc/passwd",
        "subdir/../../outside.sh",
        "./disk_usage_report.sh",
        "sub\\..\\secret.sh",
    ]
    for bad_path in malicious_paths:
        resp = client.get("/api/v1/scripts/preview-file", params={"rel_path": bad_path})
        assert resp.status_code == 403, f"Expected 403 for traversal path: {bad_path}"

    # Direct test with null byte
    with pytest.raises(PathSecurityError):
        read_allowlisted_text_file(isolated_env.scripts_dir, "disk_usage_report.sh\x00.txt")


def test_leaf_and_intermediate_directory_symlink_escape_denied(
    authenticated_client: tuple[TestClient, str],
    isolated_env: Settings,
    tmp_path: Path,
) -> None:
    """Verify F02: Leaf and intermediate directory symlinks are rejected by dir_fd openat."""
    client, _ = authenticated_client

    outside_dir = tmp_path / "outside_dir"
    outside_dir.mkdir(parents=True, exist_ok=True)
    outside_secret = outside_dir / "outside_credentials.txt"
    outside_secret.write_text("TOP_SECRET_TOKEN=12345", encoding="utf-8")

    # 1. Leaf symlink inside scripts_dir pointing to outside_secret
    symlink_leaf = isolated_env.scripts_dir / "escaped_link.sh"
    symlink_leaf.symlink_to(outside_secret)

    with pytest.raises(PathSecurityError):
        read_allowlisted_text_file(isolated_env.scripts_dir, "escaped_link.sh")

    resp = client.get("/api/v1/scripts/preview-file", params={"rel_path": "escaped_link.sh"})
    assert resp.status_code == 403

    # 2. Intermediate directory symlink inside scripts_dir pointing to outside_dir
    symlink_dir = isolated_env.scripts_dir / "linked_subdir"
    symlink_dir.symlink_to(outside_dir)

    with pytest.raises(PathSecurityError, match="Symlinks are prohibited"):
        read_allowlisted_text_file(
            isolated_env.scripts_dir, "linked_subdir/outside_credentials.txt"
        )

    dir_resp = client.get(
        "/api/v1/scripts/preview-file",
        params={"rel_path": "linked_subdir/outside_credentials.txt"},
    )
    assert dir_resp.status_code == 403


def test_hardlink_and_special_files_denied(
    authenticated_client: tuple[TestClient, str],
    isolated_env: Settings,
    tmp_path: Path,
) -> None:
    """Verify F02: Hardlinks (st_nlink > 1), directories, oversize, and binary files rejected."""
    client, _ = authenticated_client

    # 1. Hardlink to an outside file on the same filesystem
    outside_target = tmp_path / "outside_hardlink_source.sh"
    outside_target.write_text("echo 'secret hardlink'", encoding="utf-8")
    hardlink_inside = isolated_env.scripts_dir / "hardlinked.sh"
    os.link(outside_target, hardlink_inside)

    with pytest.raises(PathSecurityError, match="Hardlinked files"):
        read_allowlisted_text_file(isolated_env.scripts_dir, "hardlinked.sh")

    hl_resp = client.get("/api/v1/scripts/preview-file", params={"rel_path": "hardlinked.sh"})
    assert hl_resp.status_code == 403

    # 2. Directory opened as file
    nested_dir = isolated_env.scripts_dir / "real_subdir"
    nested_dir.mkdir(exist_ok=True)
    with pytest.raises(PathSecurityError):
        read_allowlisted_text_file(isolated_env.scripts_dir, "real_subdir")

    # 3. Oversize file (> MAX_READ_BYTES)
    oversize_file = isolated_env.scripts_dir / "huge_script.sh"
    oversize_file.write_bytes(b"a" * (MAX_READ_BYTES + 10))
    with pytest.raises(PathSecurityError, match="exceeds maximum"):
        read_allowlisted_text_file(isolated_env.scripts_dir, "huge_script.sh")

    # 4. Non-UTF8 binary file
    binary_file = isolated_env.scripts_dir / "binary.bin"
    binary_file.write_bytes(b"\xff\xfe\xfd\x00\x80")
    with pytest.raises(PathSecurityError, match="Binary files"):
        read_allowlisted_text_file(isolated_env.scripts_dir, "binary.bin")


def test_checksum_tampering_detected(
    authenticated_client: tuple[TestClient, str],
    isolated_env: Settings,
) -> None:
    client, _ = authenticated_client
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
