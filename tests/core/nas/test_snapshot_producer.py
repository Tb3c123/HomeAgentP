"""Host/container namespace boundary, snapshot schema, and producer tests."""

from __future__ import annotations

import json
import os
import stat as _stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tests.core.nas.conftest import (
    make_nas_settings,
    make_stat_result,
    make_statvfs_result,
    write_sample_proc_tree,
)

from homeagentp_core.modules.nas import host_producer
from homeagentp_core.modules.nas.collector import (
    CONTAINER_SNAPSHOT_SCHEMA_VERSION,
    HOST_SNAPSHOT_SCHEMA_VERSION,
    collect_nas_telemetry,
    inspect_container_health,
    verify_direct_host_boundary,
)
from homeagentp_core.modules.scripts.safe_reader import read_allowlisted_text_file


def test_p02_f01_host_vs_container_namespace_boundary(tmp_path: Path) -> None:
    """Verify P02-F01: container's own /proc, /, or overlayfs mounts are rejected as unavailable
    and NEVER falsely report /mnt/disk1 or /mnt/disk2 as missing/unmounted."""
    # Case 1: Adapter enabled with direct_host_fs pointing at container's own /proc or /
    container_ns_settings = make_nas_settings(
        tmp_path,
        db_name="f01_container.db",
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
    reports_dir = tmp_path / "reports"
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
    settings = make_nas_settings(
        tmp_path,
        db_name="f03.db",
        nas_adapter_enabled=True,
        nas_expected_services=["jellyfin"],
        nas_container_snapshot_rel_path="containers.json",
        nas_snapshot_max_age_seconds=180,
    )
    reports_dir = settings.reports_dir

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


def test_host_snapshot_producer_and_systemd_templates(tmp_path: Path) -> None:
    """Verify non-root filesystem permissions, snapshot handoff, and systemd/Compose alignment."""
    # Mandatory guard: do not run as root (root bypasses POSIX directory permission checks)
    assert os.geteuid() != 0, "Filesystem permission tests must run as a non-root user."

    proc_dir = tmp_path / "proc"
    write_sample_proc_tree(proc_dir)

    def fake_stat(path: str) -> os.stat_result:
        if path == "/":
            return make_stat_result(0o040755, dev=100)
        if path == "/mnt/disk1":
            return make_stat_result(0o040755, dev=200)
        if path == "/mnt/disk2":
            return make_stat_result(0o040755, dev=100)  # Unmounted fallback on root dev
        raise FileNotFoundError(path)

    def fake_statvfs(_path: str) -> os.statvfs_result:
        return make_statvfs_result(4096, 1000, 500, 500)

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
    settings = make_nas_settings(
        tmp_path,
        db_name="producer_test.db",
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
    repo_root = Path(__file__).resolve().parents[3]
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
