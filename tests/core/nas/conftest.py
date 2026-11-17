"""Shared helpers for NAS Guardian test suites."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from tests.core.conftest import TEST_ADMIN_PASSWORD, TEST_ADMIN_USERNAME, TEST_SECRET_KEY

from homeagentp_core.config import Settings


def make_stat_result(mode: int, dev: int) -> os.stat_result:
    return os.stat_result((mode, 1, dev, 1, 1000, 1000, 4096, 0, 0, 0))


def make_statvfs_result(
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


def make_nas_settings(tmp_path: Path, db_name: str = "nas_test.db", **overrides: Any) -> Settings:
    scripts_dir = tmp_path / "scripts"
    reports_dir = tmp_path / "reports"
    scripts_dir.mkdir(exist_ok=True)
    reports_dir.mkdir(exist_ok=True)
    params: dict[str, Any] = {
        "env": "testing",
        "db_path": tmp_path / db_name,
        "secret_key": TEST_SECRET_KEY,
        "admin_username": TEST_ADMIN_USERNAME,
        "admin_password": TEST_ADMIN_PASSWORD,
        "scripts_dir": scripts_dir,
        "reports_dir": reports_dir,
        "seed_examples": False,
    }
    params.update(overrides)
    return Settings(**params)


def write_sample_proc_tree(
    proc_dir: Path,
    *,
    stat_text: str = "cpu  2000 0 200 7800 0 0 0 0 0 0\ncpu0 2000 0 200 7800 0 0 0 0 0 0\n",
    loadavg_text: str = "0.55 0.40 0.25 1/150 500\n",
    cpu_psi_text: str = "some avg10=0.25 avg60=0.10 avg300=0.05 total=1000\n",
    meminfo_text: str = (
        "MemTotal:       8000000 kB\n"
        "MemAvailable:    6000000 kB\n"
        "SwapTotal:       1000000 kB\n"
        "SwapFree:        1000000 kB\n"
    ),
    mem_psi_text: str = (
        "some avg10=0.00 avg60=0.00 avg300=0.00 total=0\n"
        "full avg10=0.00 avg60=0.00 avg300=0.00 total=0\n"
    ),
    mounts_text: str = "/dev/nvme0n1p2 / ext4 rw 0 0\n/dev/sda1 /mnt/disk1 ext4 rw 0 0\n",
) -> None:
    (proc_dir / "pressure").mkdir(parents=True, exist_ok=True)
    (proc_dir / "stat").write_text(stat_text, encoding="utf-8")
    (proc_dir / "loadavg").write_text(loadavg_text, encoding="utf-8")
    (proc_dir / "pressure" / "cpu").write_text(cpu_psi_text, encoding="utf-8")
    (proc_dir / "meminfo").write_text(meminfo_text, encoding="utf-8")
    (proc_dir / "pressure" / "memory").write_text(mem_psi_text, encoding="utf-8")
    (proc_dir / "mounts").write_text(mounts_text, encoding="utf-8")
