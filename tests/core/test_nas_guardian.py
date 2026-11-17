"""Comprehensive Phase 02 & Hardening (P02-F01..F05) tests for NAS Guardian."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from tests.core.conftest import TEST_ADMIN_PASSWORD, TEST_ADMIN_USERNAME, TEST_SECRET_KEY

from homeagentp_core.config import Settings
from homeagentp_core.db.connection import db_session
from homeagentp_core.main import create_app, initialize_core_state
from homeagentp_core.modules.nas.collector import (
    CONTAINER_SNAPSHOT_SCHEMA_VERSION,
    HOST_SNAPSHOT_SCHEMA_VERSION,
    collect_nas_telemetry,
    inspect_container_health,
    inspect_mount_point,
    persist_nas_snapshot,
    query_nas_alerts,
    verify_direct_host_boundary,
)
from homeagentp_core.modules.nas.parsers import (
    compute_cpu_usage_percent,
    parse_proc_loadavg,
    parse_proc_meminfo,
    parse_proc_mounts,
    parse_proc_psi_pressure,
    parse_proc_stat_cpu,
)
from homeagentp_core.modules.nas.scheduler import NasCollectionScheduler


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

    def fake_stat(path: str) -> os.stat_result:
        if path == "/":
            return _make_stat_result(0o040755, dev=2048)
        if path == "/mnt/disk1":
            return _make_stat_result(0o040755, dev=2049)
        if path == "/mnt/disk2":
            return _make_stat_result(0o040755, dev=2048)
        raise FileNotFoundError(path)

    def fake_statvfs(path: str) -> os.statvfs_result:
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
    assert disk1["is_mounted"] is True
    assert disk1["is_root_fallback"] is False
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
    assert disk2["is_root_fallback"] is True
    assert "root filesystem" in str(disk2["reason"])

    # 3. Even if a stale entry appeared in proc_mounts, st_dev == root_dev still catches fallback
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
    assert res_perm["status"] == "permission_denied"
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


def test_p02_f01_host_vs_container_namespace_boundary(tmp_path: Path) -> None:
    """Verify P02-F01: container's own /proc, /, or overlayfs mounts are rejected as unavailable
    and NEVER falsely report /mnt/disk1 or /mnt/disk2 as missing/unmounted."""
    scripts_dir = tmp_path / "scripts"
    reports_dir = tmp_path / "reports"
    scripts_dir.mkdir()
    reports_dir.mkdir()

    # Case 1: Adapter enabled with direct_host_fs pointing at container's own /proc or /
    container_ns_settings = Settings(
        env="testing",
        db_path=tmp_path / "f01_container.db",
        secret_key=TEST_SECRET_KEY,
        admin_username=TEST_ADMIN_USERNAME,
        admin_password=TEST_ADMIN_PASSWORD,
        scripts_dir=scripts_dir,
        reports_dir=reports_dir,
        nas_adapter_enabled=True,
        nas_telemetry_mode="direct_host_fs",
        nas_proc_root=Path("/proc"),
        nas_root_mount_path=Path("/"),
    )
    ok_ns, err_ns = verify_direct_host_boundary(container_ns_settings)
    assert ok_ns is False
    assert err_ns is not None and "local process/container namespace" in err_ns

    snap_ns = collect_nas_telemetry(container_ns_settings, sample_delay_seconds=0.0)
    assert snap_ns["adapter_status"] == "unavailable"
    assert snap_ns["telemetry_boundary"]["host_verified"] is False
    assert snap_ns["alerts"] == []
    # /mnt/disk1 and /mnt/disk2 must be 'unavailable', NOT 'missing' or 'unmounted_fallback'
    assert snap_ns["mounts"]["/mnt/disk1"]["status"] == "unavailable"
    assert snap_ns["mounts"]["/mnt/disk2"]["status"] == "unavailable"

    # Case 2: Custom proc_root path, but its mounts file shows a Docker 'overlay' root filesystem
    fake_proc = tmp_path / "host_proc"
    fake_root = tmp_path / "host_root"
    fake_proc.mkdir()
    fake_root.mkdir()
    (fake_proc / "mounts").write_text(
        "overlay / overlay rw,relatime,lowerdir=/var/lib/docker/overlay2/l 0 0\n",
        encoding="utf-8",
    )
    overlay_settings = container_ns_settings.model_copy(
        update={
            "nas_proc_root": fake_proc,
            "nas_root_mount_path": fake_root,
        }
    )
    snap_overlay = collect_nas_telemetry(overlay_settings, sample_delay_seconds=0.0)
    assert snap_overlay["adapter_status"] == "unavailable"
    assert snap_overlay["telemetry_boundary"]["host_verified"] is False
    assert "overlay" in str(snap_overlay["reason"])
    assert snap_overlay["mounts"]["/mnt/disk1"]["status"] == "unavailable"
    assert snap_overlay["alerts"] == []

    # Case 3: Host snapshot mode (`host_snapshot`) with a valid, fresh host collector JSON
    now_dt = datetime(2026, 11, 17, 6, 30, 0, tzinfo=UTC)
    host_snapshot = {
        "schema_version": HOST_SNAPSHOT_SCHEMA_VERSION,
        "generated_at": now_dt.isoformat(),
        "ttl_seconds": 120,
        "cpu": {
            "status": "ok",
            "usage_percent": 22.5,
            "logical_cores": 4,
            "load_1m": 0.45,
            "load_5m": 0.38,
            "load_15m": 0.29,
            "pressure": {
                "status": "ok",
                "some": {"avg10": 0.5, "avg60": 0.2, "avg300": 0.1, "total_us": 4000},
                "full": None,
            },
        },
        "memory": {
            "status": "ok",
            "total_bytes": 16 * 1024**3,
            "available_bytes": 10 * 1024**3,
            "used_bytes": 6 * 1024**3,
            "usage_percent": 37.5,
            "swap_total_bytes": 4 * 1024**3,
            "swap_free_bytes": 4 * 1024**3,
            "swap_used_bytes": 0,
            "swap_usage_percent": 0.0,
            "pressure": {"status": "ok", "some": None, "full": None},
        },
        "mounts": [
            {
                "mount_point": "/",
                "status": "mounted",
                "device": "/dev/nvme0n1p2",
                "fstype": "ext4",
                "total_bytes": 250 * 1024**3,
                "used_bytes": 50 * 1024**3,
                "available_bytes": 200 * 1024**3,
                "usage_percent": 20.0,
            },
            {
                "mount_point": "/mnt/disk1",
                "status": "mounted",
                "device": "/dev/sda1",
                "fstype": "ext4",
                "total_bytes": 8000 * 1024**3,
                "used_bytes": 4000 * 1024**3,
                "available_bytes": 4000 * 1024**3,
                "usage_percent": 50.0,
            },
            {
                "mount_point": "/mnt/disk2",
                "status": "unmounted_fallback",
                "device": "",
                "fstype": "",
                "reason": "Host collector detected /mnt/disk2 on root device.",
            },
        ],
    }
    (reports_dir / "nas_host_snapshot.json").write_text(
        json.dumps(host_snapshot), encoding="utf-8"
    )
    host_snap_settings = container_ns_settings.model_copy(
        update={
            "nas_telemetry_mode": "host_snapshot",
            "nas_host_snapshot_rel_path": "nas_host_snapshot.json",
        }
    )
    snap_host = collect_nas_telemetry(host_snap_settings, now=now_dt)
    assert snap_host["adapter_status"] == "critical"
    assert snap_host["telemetry_boundary"]["mode"] == "host_snapshot"
    assert snap_host["telemetry_boundary"]["host_verified"] is True
    assert snap_host["telemetry_boundary"]["fresh"] is True
    assert snap_host["mounts"]["/mnt/disk1"]["status"] == "mounted"
    assert snap_host["mounts"]["/mnt/disk2"]["status"] == "unmounted_fallback"
    assert any(a["code"] == "mount.unmounted_fallback" for a in snap_host["alerts"])


def test_p02_f03_container_snapshot_schema_and_stale_detection(tmp_path: Path) -> None:
    """Verify P02-F03: container snapshot requires schema_version/generated_at/TTL and marks
    expired snapshots as 'stale' rather than live 'running' services."""
    scripts_dir = tmp_path / "scripts"
    reports_dir = tmp_path / "reports"
    scripts_dir.mkdir()
    reports_dir.mkdir()

    now_dt = datetime(2026, 11, 17, 7, 0, 0, tzinfo=UTC)
    stale_dt = now_dt - timedelta(seconds=300)

    stale_payload = {
        "schema_version": CONTAINER_SNAPSHOT_SCHEMA_VERSION,
        "generated_at": stale_dt.isoformat(),
        "ttl_seconds": 120,
        "containers": [
            {
                "name": "jellyfin",
                "state": "running",
                "memory_used_bytes": 500_000_000,
                "memory_limit_bytes": 2_000_000_000,
                "restart_count": 0,
            }
        ],
    }
    (reports_dir / "containers.json").write_text(json.dumps(stale_payload), encoding="utf-8")

    settings = Settings(
        env="testing",
        db_path=tmp_path / "f03.db",
        secret_key=TEST_SECRET_KEY,
        admin_username=TEST_ADMIN_USERNAME,
        admin_password=TEST_ADMIN_PASSWORD,
        scripts_dir=scripts_dir,
        reports_dir=reports_dir,
        nas_adapter_enabled=True,
        nas_expected_services=["jellyfin"],
        nas_container_snapshot_rel_path="containers.json",
        nas_snapshot_max_age_seconds=180,
    )

    # 1. Expired snapshot (age 300s > ttl 120s) -> status == 'stale', fresh == False
    res_stale = inspect_container_health(settings, now=now_dt)
    assert res_stale["status"] == "stale"
    assert res_stale["fresh"] is False
    assert res_stale["age_seconds"] == 300.0
    assert res_stale["services"]["jellyfin"]["status"] == "stale"

    # 2. Fresh snapshot (age 15s <= ttl 120s) -> status == 'ok', fresh == True
    fresh_payload = {
        **stale_payload,
        "generated_at": (now_dt - timedelta(seconds=15)).isoformat(),
    }
    (reports_dir / "containers.json").write_text(json.dumps(fresh_payload), encoding="utf-8")
    res_fresh = inspect_container_health(settings, now=now_dt)
    assert res_fresh["status"] == "ok"
    assert res_fresh["fresh"] is True
    assert res_fresh["age_seconds"] == 15.0
    assert res_fresh["services"]["jellyfin"]["status"] == "running"

    # 3. Missing generated_at -> status == 'stale'
    no_ts_payload = {"schema_version": CONTAINER_SNAPSHOT_SCHEMA_VERSION, "containers": []}
    (reports_dir / "containers.json").write_text(json.dumps(no_ts_payload), encoding="utf-8")
    res_no_ts = inspect_container_health(settings, now=now_dt)
    assert res_no_ts["status"] == "stale"
    assert res_no_ts["fresh"] is False


def test_p02_f04_alert_lifecycle_dedup_resolve_and_reopen(tmp_path: Path) -> None:
    """Verify P02-F04: alert appearance, deduplication, resolution, and re-occurrence."""
    scripts_dir = tmp_path / "scripts"
    reports_dir = tmp_path / "reports"
    scripts_dir.mkdir()
    reports_dir.mkdir()
    db_file = tmp_path / "f04_alerts.db"

    settings = Settings(
        env="testing",
        db_path=db_file,
        secret_key=TEST_SECRET_KEY,
        admin_username=TEST_ADMIN_USERNAME,
        admin_password=TEST_ADMIN_PASSWORD,
        scripts_dir=scripts_dir,
        reports_dir=reports_dir,
        seed_examples=False,
    )
    initialize_core_state(settings)

    def _make_snap(ts: str, alerts: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "collected_at": ts,
            "adapter_status": "critical" if alerts else "online",
            "cpu": {"usage_percent": 20.0, "pressure": {}},
            "memory": {"usage_percent": 40.0, "pressure": {}},
            "mounts": {},
            "mounts_list": [],
            "containers": {},
            "alerts": alerts,
        }

    disk_alert = {
        "alert_key": "mount:/mnt/disk2:mount.unmounted_fallback",
        "code": "mount.unmounted_fallback",
        "severity": "critical",
        "category": "mount_guardian",
        "component": "mount:/mnt/disk2",
        "target": "/mnt/disk2",
        "message": "Mount /mnt/disk2 fell back to root filesystem.",
        "metric_value": None,
        "threshold_value": None,
        "details": {"mount_point": "/mnt/disk2"},
    }

    t1 = "2026-11-17T06:00:00+00:00"
    t2 = "2026-11-17T06:01:00+00:00"
    t3 = "2026-11-17T06:02:00+00:00"
    t4 = "2026-11-17T06:03:00+00:00"

    with db_session(db_file) as conn:
        # Step 1: Alert first appears at t1
        persist_nas_snapshot(conn, _make_snap(t1, [dict(disk_alert)]), retention_limit=50)
        active_1 = query_nas_alerts(conn, include_resolved=False)
        assert len(active_1) == 1
        assert active_1[0]["status"] == "active"
        assert active_1[0]["first_seen_at"] == t1
        assert active_1[0]["last_seen_at"] == t1
        assert active_1[0]["resolved_at"] is None
        assert active_1[0]["occurrences"] == 1
        first_id = active_1[0]["id"]

        # Step 2: Same alert persists at t2 -> deduplicated into same row, occurrences == 2
        persist_nas_snapshot(conn, _make_snap(t2, [dict(disk_alert)]), retention_limit=50)
        active_2 = query_nas_alerts(conn, include_resolved=False)
        assert len(active_2) == 1
        assert active_2[0]["id"] == first_id
        assert active_2[0]["first_seen_at"] == t1
        assert active_2[0]["last_seen_at"] == t2
        assert active_2[0]["occurrences"] == 2

        # Step 3: Condition clears at t3 -> row transitions to 'resolved' with resolved_at == t3
        persist_nas_snapshot(conn, _make_snap(t3, []), retention_limit=50)
        active_3 = query_nas_alerts(conn, include_resolved=False)
        assert len(active_3) == 0
        all_3 = query_nas_alerts(conn, include_resolved=True)
        assert len(all_3) == 1
        assert all_3[0]["id"] == first_id
        assert all_3[0]["status"] == "resolved"
        assert all_3[0]["resolved_at"] == t3

        # Step 4: Alert re-occurs at t4 -> new 'active' row created while resolved history stays
        persist_nas_snapshot(conn, _make_snap(t4, [dict(disk_alert)]), retention_limit=50)
        active_4 = query_nas_alerts(conn, include_resolved=False)
        assert len(active_4) == 1
        assert active_4[0]["id"] != first_id
        assert active_4[0]["status"] == "active"
        assert active_4[0]["first_seen_at"] == t4
        assert active_4[0]["occurrences"] == 1
        all_4 = query_nas_alerts(conn, include_resolved=True)
        assert len(all_4) == 2


def test_p02_f02_scheduler_non_overlapping_timeout_and_write_throttling(tmp_path: Path) -> None:
    """Verify P02-F02: background scheduler prevents overlapping runs, handles timeouts,
    throttles excessive SQLite writes, and shuts down cleanly."""
    scripts_dir = tmp_path / "scripts"
    reports_dir = tmp_path / "reports"
    scripts_dir.mkdir()
    reports_dir.mkdir()
    db_file = tmp_path / "f02_sched.db"

    settings = Settings(
        env="testing",
        db_path=db_file,
        secret_key=TEST_SECRET_KEY,
        admin_username=TEST_ADMIN_USERNAME,
        admin_password=TEST_ADMIN_PASSWORD,
        scripts_dir=scripts_dir,
        reports_dir=reports_dir,
        nas_adapter_enabled=True,
        nas_scheduler_enabled=True,
        nas_collection_interval_seconds=10,
        nas_collection_timeout_seconds=1.0,
        nas_min_persist_interval_seconds=60,
        seed_examples=False,
    )
    initialize_core_state(settings)

    def fast_collector(_cfg: Settings) -> dict[str, Any]:
        return {
            "collected_at": datetime.now(UTC).isoformat(),
            "adapter_status": "online",
            "cpu": {"usage_percent": 12.0, "pressure": {}},
            "memory": {"usage_percent": 35.0, "pressure": {}},
            "mounts": {},
            "mounts_list": [],
            "containers": {},
            "alerts": [],
        }

    async def _run_scheduler_checks() -> None:
        sched = NasCollectionScheduler(settings, collector_fn=fast_collector)
        res1 = await sched.run_once()
        assert res1 is not None
        first_snap_id = res1["snapshot_id"]
        assert first_snap_id > 0

        # Second immediate run within min_persist_interval_seconds (60s) with unchanged status
        # must be throttled and reuse the existing snapshot row ID without inserting a new row
        res2 = await sched.run_once()
        assert res2 is not None
        assert res2["snapshot_id"] == first_snap_id

        with db_session(db_file) as conn:
            cnt = int(conn.execute("SELECT COUNT(*) FROM nas_metric_snapshots").fetchone()[0])
            assert cnt == 1

        # Test overlap protection & timeout handling
        import time as _time

        def slow_collector(_cfg: Settings) -> dict[str, Any]:
            _time.sleep(0.35)
            return fast_collector(_cfg)

        overlap_sched = NasCollectionScheduler(settings, collector_fn=slow_collector)
        t_a = asyncio.create_task(overlap_sched.run_once())
        await asyncio.sleep(0.05)
        t_b = asyncio.create_task(overlap_sched.run_once())
        out_a, out_b = await asyncio.gather(t_a, t_b)
        assert (out_a is None) or (out_b is None)
        assert overlap_sched.skipped_overlap_count == 1

        # Timeout test + verify underlying worker thread does NOT overlap on next run_once()
        timeout_settings = settings.model_copy(update={"nas_collection_timeout_seconds": 1.0})
        active_worker_threads = 0
        max_concurrent_workers = 0
        call_number = 0

        def hanging_Then_recovering_collector(_cfg: Settings) -> dict[str, Any]:
            nonlocal active_worker_threads, max_concurrent_workers, call_number
            call_number += 1
            active_worker_threads += 1
            max_concurrent_workers = max(max_concurrent_workers, active_worker_threads)
            try:
                if call_number == 1:
                    _time.sleep(1.35)
                else:
                    _time.sleep(0.05)
                return fast_collector(_cfg)
            finally:
                active_worker_threads -= 1

        timeout_sched = NasCollectionScheduler(
            timeout_settings, collector_fn=hanging_Then_recovering_collector
        )
        out_timeout = await timeout_sched.run_once()
        assert out_timeout is None
        assert timeout_sched.last_status == "timeout"
        assert timeout_sched.last_error is not None and "timed out" in timeout_sched.last_error
        # Immediately invoke run_once() while the timed-out worker thread is STILL running:
        # Must be rejected with skipped_worker_busy and never spawn a second concurrent worker!
        assert timeout_sched.worker_thread_busy is True
        out_while_busy = await timeout_sched.run_once()
        assert out_while_busy is None
        assert timeout_sched.last_status == "skipped_worker_busy"
        assert timeout_sched.skipped_overlap_count == 1
        assert max_concurrent_workers == 1

        # Wait for the first worker thread to finish, then confirm the next run succeeds
        await asyncio.sleep(0.5)
        assert timeout_sched.worker_thread_busy is False
        out_after_recovery = await timeout_sched.run_once()
        assert out_after_recovery is not None
        assert timeout_sched.last_status == "online"
        assert max_concurrent_workers == 1
        clean_stop = await timeout_sched.stop(wait_timeout=0.5)
        assert clean_stop["running"] is False
        assert clean_stop["stopping"] is False
        assert clean_stop["worker_thread_busy"] is False
        assert clean_stop["last_status"] == "stopped"

        # Bounded shutdown test when worker thread is STILL hung on OS I/O:
        # Must NOT claim "stopped" while the worker thread is still running!
        def hung_on_shutdown_collector(_cfg: Settings) -> dict[str, Any]:
            _time.sleep(1.35)
            return fast_collector(_cfg)

        hung_sched = NasCollectionScheduler(
            timeout_settings,
            collector_fn=hung_on_shutdown_collector,
            shutdown_timeout_seconds=0.1,
        )
        out_hung = await hung_sched.run_once()
        assert out_hung is None
        assert hung_sched.last_status == "timeout"
        assert hung_sched.worker_thread_busy is True

        # Trigger bounded stop (0.05s wait) while worker thread is still blocked (~0.35s left)
        stop_state = await hung_sched.stop(wait_timeout=0.05)
        assert stop_state["running"] is False
        assert stop_state["stopping"] is True
        assert stop_state["worker_thread_busy"] is True
        assert stop_state["in_progress"] is True
        assert stop_state["last_status"] == "stopping_worker_hung"
        assert "still active" in str(stop_state["last_error"])

        # Attempting a new collection while stopping must be rejected immediately
        rejected = await hung_sched.run_once()
        assert rejected is None
        assert hung_sched.last_status == "stopping_worker_hung"

        # Once the hung worker finally finishes in the background, state transitions to "stopped"
        await asyncio.sleep(0.45)
        final_state = hung_sched.status_summary()
        assert final_state["worker_thread_busy"] is False
        assert final_state["stopping"] is False
        assert final_state["last_status"] == "stopped"

        # Start and graceful stop test
        await sched.start()
        assert sched.running is True
        await asyncio.sleep(0.05)
        await sched.stop()
        assert sched.running is False
        assert sched.last_status == "stopped"

    asyncio.run(_run_scheduler_checks())


def test_host_snapshot_producer_and_systemd_templates(tmp_path: Path) -> None:
    """Verify non-root filesystem permissions, snapshot handoff, and systemd/Compose alignment."""
    import stat as _stat

    from homeagentp_core.modules.nas import host_producer
    from homeagentp_core.modules.scripts.safe_reader import read_allowlisted_text_file

    # Mandatory guard: do not run as root (root bypasses POSIX directory permission checks)
    assert os.geteuid() != 0, "Filesystem permission tests must run as a non-root user."

    proc_dir = tmp_path / "proc"
    (proc_dir / "pressure").mkdir(parents=True)
    (proc_dir / "stat").write_text(
        "cpu  2000 0 200 7800 0 0 0 0 0 0\ncpu0 2000 0 200 7800 0 0 0 0 0 0\n",
        encoding="utf-8",
    )
    (proc_dir / "loadavg").write_text("0.55 0.40 0.25 1/150 500\n", encoding="utf-8")
    (proc_dir / "pressure" / "cpu").write_text(
        "some avg10=0.25 avg60=0.10 avg300=0.05 total=1000\n",
        encoding="utf-8",
    )
    (proc_dir / "meminfo").write_text(
        "MemTotal:       8000000 kB\n"
        "MemAvailable:    6000000 kB\n"
        "SwapTotal:       1000000 kB\n"
        "SwapFree:        1000000 kB\n",
        encoding="utf-8",
    )
    (proc_dir / "pressure" / "memory").write_text(
        "some avg10=0.00 avg60=0.00 avg300=0.00 total=0\n"
        "full avg10=0.00 avg60=0.00 avg300=0.00 total=0\n",
        encoding="utf-8",
    )
    (proc_dir / "mounts").write_text(
        "/dev/nvme0n1p2 / ext4 rw 0 0\n/dev/sda1 /mnt/disk1 ext4 rw 0 0\n",
        encoding="utf-8",
    )

    def fake_stat(path: str) -> os.stat_result:
        if path == "/":
            return _make_stat_result(0o040755, dev=100)
        if path == "/mnt/disk1":
            return _make_stat_result(0o040755, dev=200)
        if path == "/mnt/disk2":
            return _make_stat_result(0o040755, dev=100)  # Unmounted fallback on root dev
        raise FileNotFoundError(path)

    def fake_statvfs(_path: str) -> os.statvfs_result:
        return _make_statvfs_result(4096, 1000, 500, 500)

    reports_dir = tmp_path / "reports"
    scripts_dir = tmp_path / "scripts"
    reports_dir.mkdir(mode=0o755)
    scripts_dir.mkdir(mode=0o755)
    out_file = reports_dir / "nas_host_snapshot.json"

    payload = host_producer.build_host_snapshot_payload(
        proc_root=proc_dir,
        root_mount_path="/",
        required_mounts=["/mnt/disk1", "/mnt/disk2"],
        ttl_seconds=120,
        sample_delay_seconds=0.0,
        stat_fn=fake_stat,
        statvfs_fn=fake_statvfs,
    )

    # Even under a restrictive process umask (0077), write_atomic_json_snapshot must produce
    # mode 0644 (rw-r--r--) with st_nlink == 1 so Core UID 10001 can read it across :ro mount.
    old_umask = os.umask(0o077)
    try:
        written = host_producer.write_atomic_json_snapshot(out_file, payload)
    finally:
        os.umask(old_umask)

    assert written == out_file.resolve()
    assert out_file.exists()
    st_out = os.lstat(out_file)
    assert _stat.S_ISREG(st_out.st_mode)
    assert _stat.S_IMODE(st_out.st_mode) == 0o644
    assert bool(st_out.st_mode & _stat.S_IRUSR)
    assert bool(st_out.st_mode & _stat.S_IRGRP)
    assert bool(st_out.st_mode & _stat.S_IROTH)
    assert st_out.st_nlink == 1

    # Verify Core safe_reader can read the exact snapshot file without symlink/hardlink rejection
    safe_file = read_allowlisted_text_file(reports_dir, "nas_host_snapshot.json")
    assert safe_file.size_bytes > 0
    assert len(safe_file.sha256) == 64
    assert json.loads(safe_file.content)["schema_version"] == HOST_SNAPSHOT_SCHEMA_VERSION

    # Verify non-root permission failure when snapshot directory is read-only (0555)
    ro_dir = tmp_path / "ro_reports"
    ro_dir.mkdir(mode=0o555)
    try:
        try:
            host_producer.write_atomic_json_snapshot(ro_dir / "nas_host_snapshot.json", payload)
            raise AssertionError("Expected PermissionError on read-only snapshot directory")
        except PermissionError:
            pass
        assert list(ro_dir.iterdir()) == []
    finally:
        ro_dir.chmod(0o755)

    # Verify symlinked target or parent directory is rejected
    sym_target = reports_dir / "symlink_snap.json"
    sym_target.symlink_to(out_file)
    try:
        host_producer.write_atomic_json_snapshot(sym_target, payload)
        raise AssertionError("Expected PermissionError on symlink target")
    except PermissionError:
        pass

    # Verify Core consumes the producer's output via host_snapshot mode
    settings = Settings(
        env="testing",
        db_path=tmp_path / "producer_test.db",
        secret_key=TEST_SECRET_KEY,
        admin_username=TEST_ADMIN_USERNAME,
        admin_password=TEST_ADMIN_PASSWORD,
        scripts_dir=scripts_dir,
        reports_dir=reports_dir,
        nas_adapter_enabled=True,
        nas_telemetry_mode="host_snapshot",
        nas_host_snapshot_rel_path="nas_host_snapshot.json",
    )
    snap = collect_nas_telemetry(settings)
    assert snap["telemetry_boundary"]["host_verified"] is True
    assert snap["telemetry_boundary"]["fresh"] is True
    assert snap["mounts"]["/mnt/disk1"]["status"] == "mounted"
    assert snap["mounts"]["/mnt/disk2"]["status"] == "unmounted_fallback"

    # Also test CLI entrypoint main()
    cli_out = reports_dir / "cli_snapshot.json"
    rc = host_producer.main(
        [
            "--output",
            str(cli_out),
            "--proc-root",
            str(proc_dir),
            "--root-mount",
            "/",
            "--required-mounts",
            "/mnt/disk1,/mnt/disk2",
            "--ttl-seconds",
            "90",
        ]
    )
    assert rc == 0
    assert cli_out.exists()

    # Verify sample systemd service, timer, Docker Compose, and .env.example path synchronization
    repo_root = Path(__file__).resolve().parents[2]
    svc_file = repo_root / "deploy" / "systemd" / "homeagentp-nas-host-snapshot.service"
    tmr_file = repo_root / "deploy" / "systemd" / "homeagentp-nas-host-snapshot.timer"
    compose_file = repo_root / "deploy" / "docker-compose.dev.yml"
    env_example_file = repo_root / "config" / "examples" / ".env.example"
    assert svc_file.exists()
    assert tmr_file.exists()
    svc_text = svc_file.read_text(encoding="utf-8")
    compose_text = compose_file.read_text(encoding="utf-8")
    env_text = env_example_file.read_text(encoding="utf-8")

    assert "User=10001" in svc_text
    assert "Group=10001" in svc_text
    assert "UMask=0022" in svc_text
    assert "StateDirectory=homeagentp/reports" in svc_text
    assert "ReadWritePaths=/var/lib/homeagentp/reports" in svc_text
    assert "--output /var/lib/homeagentp/reports/nas_host_snapshot.json" in svc_text
    assert "NoNewPrivileges=yes" in svc_text
    assert "ProtectSystem=strict" in svc_text
    assert "homeagentp_core.modules.nas.host_producer" in svc_text

    # Confirm Docker Compose mounts /var/lib/homeagentp/reports read-only to /config/reports
    # and runs homeagentp-core as UID:GID 10001:10001 without Docker Socket or privileged mode
    compose_active = "\n".join(
        line for line in compose_text.splitlines() if not line.strip().startswith("#")
    )
    assert 'user: "10001:10001"' in compose_active
    assert "${HOMEAGENTP_HOST_REPORTS_DIR:-/var/lib/homeagentp/reports}:/config/reports:ro" in (
        compose_active
    )
    assert "HOMEAGENTP_REPORTS_DIR: /config/reports" in compose_active
    assert (
        "HOMEAGENTP_NAS_HOST_SNAPSHOT_REL_PATH: "
        "${HOMEAGENTP_NAS_HOST_SNAPSHOT_REL_PATH:-nas_host_snapshot.json}"
    ) in compose_active
    assert "docker.sock" not in compose_active
    assert "privileged: true" not in compose_active
    assert "HOMEAGENTP_HOST_REPORTS_DIR=/var/lib/homeagentp/reports" in env_text


def test_nas_guardian_api_collection_alerts_and_retention(tmp_path: Path) -> None:
    """End-to-end test of /api/v1/nas/* with verified direct host directory, fresh container
    snapshot, include_resolved parameter, and snapshot retention pruning."""
    scripts_dir = tmp_path / "scripts"
    reports_dir = tmp_path / "reports"
    proc_dir = tmp_path / "host_proc"
    root_dir = tmp_path / "host_root"
    (proc_dir / "pressure").mkdir(parents=True)
    root_dir.mkdir()
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

    container_snapshot = {
        "schema_version": CONTAINER_SNAPSHOT_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "ttl_seconds": 300,
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
        ],
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
        nas_telemetry_mode="direct_host_fs",
        nas_proc_root=proc_dir,
        nas_root_mount_path=root_dir,
        nas_required_mounts=["/mnt/disk1", "/mnt/disk2"],
        nas_expected_services=["jellyfin", "qbittorrent"],
        nas_container_snapshot_rel_path="containers_snapshot.json",
        nas_history_retention_limit=5,
        seed_examples=False,
    )

    app = create_app(settings)
    with TestClient(app) as client:
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
        assert st_data["telemetry_boundary"]["host_verified"] is True
        assert st_data["memory"]["usage_percent"] == 90.0
        assert st_data["containers"]["status"] == "degraded"
        assert st_data["containers"]["fresh"] is True

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

        alerts_resp = client.get("/api/v1/nas/alerts?include_resolved=false")
        assert alerts_resp.status_code == 200
        active_alerts = alerts_resp.json()
        alert_codes = {a["code"] for a in active_alerts}
        assert "ram.usage_warning" in alert_codes
        assert "container.not_running" in alert_codes
        assert "container.memory_warning" in alert_codes
        # All deduplicated alerts must have occurrences == 7 and status == 'active'
        for a in active_alerts:
            assert a["status"] == "active"
            assert a["occurrences"] == 7
