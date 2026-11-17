"""Comprehensive Phase 02 tests for NAS Guardian parsers, Mount Guardian, alerts, and API."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tests.core.conftest import TEST_ADMIN_PASSWORD, TEST_ADMIN_USERNAME, TEST_SECRET_KEY

from homeagentp_core.config import Settings
from homeagentp_core.main import create_app
from homeagentp_core.modules.nas.collector import (
    collect_nas_telemetry,
    inspect_mount_point,
)
from homeagentp_core.modules.nas.parsers import (
    compute_cpu_usage_percent,
    parse_proc_loadavg,
    parse_proc_meminfo,
    parse_proc_mounts,
    parse_proc_psi_pressure,
    parse_proc_stat_cpu,
)


def _make_stat_result(mode: int, dev: int) -> os.stat_result:
    return os.stat_result((mode, 1, dev, 1, 1000, 1000, 4096, 0, 0, 0))


def _make_statvfs_result(
    frsize: int, total_blocks: int, free_blocks: int, avail_blocks: int
) -> os.statvfs_result:
    return os.statvfs_result(
        (
            frsize,
            frsize,
            total_blocks,
            free_blocks,
            avail_blocks,
            1000,
            900,
            900,
            0,
            255,
        )
    )


def test_parse_cpu_loadavg_psi_and_meminfo() -> None:
    stat_1 = (
        "cpu  1000 50 300 8000 200 10 20 0 0 0\n"
        "cpu0 250 10 80 2000 50 2 5 0 0 0\n"
        "cpu1 250 15 70 2000 50 3 5 0 0 0\n"
        "cpu2 250 10 75 2000 50 2 5 0 0 0\n"
        "cpu3 250 15 75 2000 50 3 5 0 0 0\n"
    )
    stat_2 = (
        "cpu  1300 50 400 8600 200 10 20 0 0 0\n"
        "cpu0 325 10 105 2150 50 2 5 0 0 0\n"
        "cpu1 325 15 95 2150 50 3 5 0 0 0\n"
        "cpu2 325 10 100 2150 50 2 5 0 0 0\n"
        "cpu3 325 15 100 2150 50 3 5 0 0 0\n"
    )
    t1 = parse_proc_stat_cpu(stat_1)
    t2 = parse_proc_stat_cpu(stat_2)
    assert t1.logical_cores == 4
    # Delta total = 1000, delta idle = 600 -> busy = 40.0%
    assert compute_cpu_usage_percent(t1, t2) == 40.0

    load_1m, load_5m, load_15m = parse_proc_loadavg("0.65 0.42 0.31 2/410 9981\n")
    assert (load_1m, load_5m, load_15m) == (0.65, 0.42, 0.31)

    psi = parse_proc_psi_pressure(
        "some avg10=1.20 avg60=0.75 avg300=0.30 total=50123\n"
        "full avg10=0.10 avg60=0.05 avg300=0.00 total=4200\n"
    )
    assert psi["status"] == "ok"
    assert psi["some"]["avg10"] == 1.2
    assert psi["full"]["avg60"] == 0.05

    meminfo = parse_proc_meminfo(
        "MemTotal:       16000000 kB\n"
        "MemFree:         2000000 kB\n"
        "MemAvailable:    8000000 kB\n"
        "Buffers:          500000 kB\n"
        "Cached:          5500000 kB\n"
        "SwapTotal:       4000000 kB\n"
        "SwapFree:        3000000 kB\n"
    )
    assert meminfo["total_bytes"] == 16000000 * 1024
    assert meminfo["available_bytes"] == 8000000 * 1024
    assert meminfo["used_bytes"] == 8000000 * 1024
    assert meminfo["usage_percent"] == 50.0
    assert meminfo["swap_usage_percent"] == 25.0


def test_parsers_reject_malformed_data() -> None:
    with pytest.raises(ValueError):
        parse_proc_stat_cpu("not_a_cpu_line 1 2 3\n")
    with pytest.raises(ValueError):
        parse_proc_loadavg("0.10 only_two\n")
    with pytest.raises(ValueError):
        parse_proc_psi_pressure("invalid psi line\n")
    with pytest.raises(ValueError):
        parse_proc_meminfo("MemTotal: 0 kB\n")


def test_mount_guardian_detects_missing_and_unmounted_root_fallback() -> None:
    """Verify Mount Guardian detects both missing directories and unmounted root-fs directories."""
    mounts_text = (
        "/dev/nvme0n1p2 / ext4 rw,relatime 0 0\n"
        "/dev/sda1 /mnt/disk1 ext4 rw,relatime 0 0\n"
    )
    proc_mounts = parse_proc_mounts(mounts_text)

    # Simulate:
    # - '/' is on device 2048
    # - '/mnt/disk1' is mounted on distinct device 2049
    # - '/mnt/disk2' directory still exists on disk, but is on root device 2048 (unmounted HDD!)
    # - '/mnt/disk3' directory does not exist at all
    def fake_stat(path: str) -> os.stat_result:
        if path == "/":
            return _make_stat_result(0o040755, dev=2048)
        if path == "/mnt/disk1":
            return _make_stat_result(0o040755, dev=2049)
        if path == "/mnt/disk2":
            return _make_stat_result(0o040755, dev=2048)
        raise FileNotFoundError(path)

    def fake_statvfs(path: str) -> os.statvfs_result:
        # 1000 blocks of 4096 bytes, 100 free/available -> 90.0% used
        return _make_statvfs_result(4096, 1000, 100, 100)

    # 1. Properly mounted /mnt/disk1
    disk1 = inspect_mount_point(
        "/mnt/disk1",
        proc_mounts,
        root_mount_path="/",
        require_distinct_device=True,
        stat_fn=fake_stat,
        statvfs_fn=fake_statvfs,
    )
    assert disk1["status"] == "mounted"
    assert disk1["healthy"] is True
    assert disk1["device"] == "/dev/sda1"
    assert disk1["fstype"] == "ext4"
    assert disk1["usage_percent"] == 90.0

    # 2. /mnt/disk2 directory exists on root filesystem, but HDD is unmounted!
    disk2 = inspect_mount_point(
        "/mnt/disk2",
        proc_mounts,
        root_mount_path="/",
        require_distinct_device=True,
        stat_fn=fake_stat,
        statvfs_fn=fake_statvfs,
    )
    assert disk2["status"] == "unmounted_fallback"
    assert disk2["healthy"] is False
    assert "root filesystem" in str(disk2["reason"])

    # 3.Even if a stale entry appeared in proc_mounts, st_dev == root_dev still catches fallback
    proc_mounts_with_stale = dict(proc_mounts)
    proc_mounts_with_stale["/mnt/disk2"] = proc_mounts["/mnt/disk1"]
    disk2_same_dev = inspect_mount_point(
        "/mnt/disk2",
        proc_mounts_with_stale,
        root_mount_path="/",
        require_distinct_device=True,
        stat_fn=fake_stat,
        statvfs_fn=fake_statvfs,
    )
    assert disk2_same_dev["status"] == "unmounted_fallback"
    assert disk2_same_dev["healthy"] is False

    # 4. Non-existent directory /mnt/disk3 -> missing
    disk3 = inspect_mount_point(
        "/mnt/disk3",
        proc_mounts,
        root_mount_path="/",
        require_distinct_device=True,
        stat_fn=fake_stat,
        statvfs_fn=fake_statvfs,
    )
    assert disk3["status"] == "missing"
    assert disk3["healthy"] is False


def test_mount_guardian_handles_permission_error_and_symlinks() -> None:
    proc_mounts = parse_proc_mounts("/dev/sda1 /mnt/disk1 ext4 rw 0 0\n")

    def perm_denied_stat(path: str) -> os.stat_result:
        raise PermissionError("Permission denied")

    res_perm = inspect_mount_point(
        "/mnt/disk1",
        proc_mounts,
        stat_fn=perm_denied_stat,
    )
    assert res_perm["status"] == "unavailable"
    assert res_perm["healthy"] is False
    assert res_perm["total_bytes"] is None

    def symlink_stat(path: str) -> os.stat_result:
        return _make_stat_result(0o120777, dev=2049)

    res_sym = inspect_mount_point(
        "/mnt/disk1",
        proc_mounts,
        stat_fn=symlink_stat,
    )
    assert res_sym["status"] == "invalid_symlink"
    assert res_sym["healthy"] is False


def test_disabled_adapter_and_missing_proc_never_fabricate_metrics(tmp_path: Path) -> None:
    scripts_dir = tmp_path / "scripts"
    reports_dir = tmp_path / "reports"
    scripts_dir.mkdir()
    reports_dir.mkdir()

    # 1. Adapter disabled
    disabled_settings = Settings(
        env="testing",
        db_path=tmp_path / "disabled.db",
        secret_key=TEST_SECRET_KEY,
        admin_username=TEST_ADMIN_USERNAME,
        admin_password=TEST_ADMIN_PASSWORD,
        scripts_dir=scripts_dir,
        reports_dir=reports_dir,
        nas_adapter_enabled=False,
    )
    snap_disabled = collect_nas_telemetry(disabled_settings)
    assert snap_disabled["adapter_status"] == "unavailable"
    assert snap_disabled["cpu"]["usage_percent"] is None
    assert snap_disabled["memory"]["total_bytes"] is None
    assert all(m["status"] == "unavailable" for m in snap_disabled["mounts"])

    # 2. Adapter enabled, but proc_root is empty/missing files
    empty_proc = tmp_path / "empty_proc"
    empty_proc.mkdir()
    missing_proc_settings = disabled_settings.model_copy(
        update={"nas_adapter_enabled": True, "nas_proc_root": empty_proc}
    )
    snap_missing = collect_nas_telemetry(missing_proc_settings, sample_delay_seconds=0.0)
    assert snap_missing["adapter_status"] == "unavailable"
    assert snap_missing["cpu"]["status"] == "unavailable"
    assert snap_missing["cpu"]["usage_percent"] is None
    assert snap_missing["memory"]["status"] == "unavailable"
    assert snap_missing["memory"]["usage_percent"] is None


def test_nas_guardian_api_collection_alerts_and_retention(tmp_path: Path) -> None:
    """End-to-end test of /api/v1/nas/* with synthetic /proc and container snapshot."""
    scripts_dir = tmp_path / "scripts"
    reports_dir = tmp_path / "reports"
    proc_dir = tmp_path / "proc"
    (proc_dir / "pressure").mkdir(parents=True)
    scripts_dir.mkdir()
    reports_dir.mkdir()

    (proc_dir / "stat").write_text(
        "cpu  9000 0 500 500 0 0 0 0 0 0\ncpu0 9000 0 500 500 0 0 0 0 0 0\n",
        encoding="utf-8",
    )
    (proc_dir / "loadavg").write_text("1.85 1.20 0.95 2/200 1001\n", encoding="utf-8")
    (proc_dir / "pressure" / "cpu").write_text(
        "some avg10=2.50 avg60=1.10 avg300=0.50 total=10000\n",
        encoding="utf-8",
    )
    # 90% RAM used (triggers ram.usage_warning at >=85%)
    (proc_dir / "meminfo").write_text(
        "MemTotal:       16000000 kB\n"
        "MemAvailable:    1600000 kB\n"
        "SwapTotal:       2000000 kB\n"
        "SwapFree:        2000000 kB\n",
        encoding="utf-8",
    )
    (proc_dir / "pressure" / "memory").write_text(
        "some avg10=0.50 avg60=0.20 avg300=0.10 total=2000\n"
        "full avg10=0.00 avg60=0.00 avg300=0.00 total=0\n",
        encoding="utf-8",
    )
    (proc_dir / "mounts").write_text(
        "/dev/nvme0n1p2 / ext4 rw 0 0\n",
        encoding="utf-8",
    )

    # Write a read-only container snapshot in reports_dir
    container_snapshot = {
        "containers": [
            {
                "name": "jellyfin",
                "state": "running",
                "memory_used_bytes": 900_000_000,
                "memory_limit_bytes": 1_000_000_000,
                "cpu_percent": 12.5,
                "restart_count": 0,
            },
            {
                "name": "qbittorrent",
                "state": "exited",
                "memory_used_bytes": 0,
                "memory_limit_bytes": 1_000_000_000,
                "cpu_percent": 0.0,
                "restart_count": 3,
            },
        ]
    }
    (reports_dir / "containers_snapshot.json").write_text(
        json.dumps(container_snapshot),
        encoding="utf-8",
    )

    settings = Settings(
        env="testing",
        db_path=tmp_path / "nas_test.db",
        secret_key=TEST_SECRET_KEY,
        admin_username=TEST_ADMIN_USERNAME,
        admin_password=TEST_ADMIN_PASSWORD,
        scripts_dir=scripts_dir,
        reports_dir=reports_dir,
        nas_adapter_enabled=True,
        nas_proc_root=proc_dir,
        nas_required_mounts=["/mnt/disk1", "/mnt/disk2"],
        nas_expected_services=["jellyfin", "qbittorrent"],
        nas_container_snapshot_rel_path="containers_snapshot.json",
        nas_history_retention_limit=5,
        seed_examples=False,
    )

    app = create_app(settings)
    with TestClient(app) as client:
        # Unauthenticated requests to /api/v1/nas/* must be rejected with 401
        assert client.get("/api/v1/nas/status").status_code == 401
        assert client.get("/api/v1/nas/history").status_code == 401
        assert client.get("/api/v1/nas/alerts").status_code == 401

        login_resp = client.post(
            "/api/v1/auth/login",
            json={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
        )
        assert login_resp.status_code == 200
        csrf = login_resp.json()["csrf_token"]

        status_resp = client.get("/api/v1/nas/status")
        assert status_resp.status_code == 200
        st_data = status_resp.json()
        assert st_data["adapter_enabled"] is True
        assert st_data["memory"]["usage_percent"] == 90.0
        assert st_data["containers"]["status"] == "ok"

        # Collect 7 snapshots; retention limit is 5, so only 5 must remain in history
        for _ in range(7):
            collect_resp = client.post(
                "/api/v1/nas/collect",
                headers={"X-CSRF-Token": csrf},
            )
            assert collect_resp.status_code == 200

        history_resp = client.get("/api/v1/nas/history")
        assert history_resp.status_code == 200
        history_items = history_resp.json()
        assert len(history_items) == 5

        alerts_resp = client.get("/api/v1/nas/alerts")
        assert alerts_resp.status_code == 200
        alert_codes = {a["code"] for a in alerts_resp.json()}
        assert "ram.usage_warning" in alert_codes
        assert "container.not_running" in alert_codes
        assert "container.memory_warning" in alert_codes
