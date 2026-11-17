"""Mount Guardian inspection tests for NAS Guardian."""

from __future__ import annotations

import os

from tests.core.nas.conftest import make_stat_result, make_statvfs_result

from homeagentp_core.modules.nas.collector import inspect_mount_point
from homeagentp_core.modules.nas.parsers import parse_proc_mounts


def test_mount_guardian_detects_missing_and_unmounted_root_fallback() -> None:
    """Verify Mount Guardian detects both missing directories and unmounted root-fs directories."""
    mounts_text = (
        "/dev/nvme0n1p2 / ext4 rw,relatime 0 0\n"
        "/dev/sda1 /mnt/disk1 ext4 rw,relatime 0 0\n"
    )
    proc_mounts = parse_proc_mounts(mounts_text)

    def fake_stat(path: str) -> os.stat_result:
        if path == "/":
            return make_stat_result(0o040755, dev=2048)
        if path == "/mnt/disk1":
            return make_stat_result(0o040755, dev=2049)
        if path == "/mnt/disk2":
            return make_stat_result(0o040755, dev=2048)
        raise FileNotFoundError(path)

    def fake_statvfs(path: str) -> os.statvfs_result:
        return make_statvfs_result(4096, 1000, 100, 100)

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
        return make_stat_result(0o120777, dev=2049)

    res_sym = inspect_mount_point(
        "/mnt/disk1",
        proc_mounts,
        stat_fn=symlink_stat,
    )
    assert res_sym["status"] == "invalid_symlink"
    assert res_sym["healthy"] is False
