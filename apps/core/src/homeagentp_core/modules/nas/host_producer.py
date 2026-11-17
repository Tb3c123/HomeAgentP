"""Least-privilege NAS Host Snapshot Producer (`homeagentp.nas_host.v1`).

Runs on the Debian 12 NAS host (e.g., via a restricted systemd service + timer with
`DynamicUser=yes`, `ProtectSystem=strict`, `ReadWritePaths=/var/lib/homeagentp/reports`)
and writes an atomic JSON snapshot (`nas_host_snapshot.json`) into the directory mounted
read-only (`:ro`) into `homeagentp-core` (`HOMEAGENTP_REPORTS_DIR`).

Security & Storage Safety Invariants:
- Reads only host `/proc/stat`, `/proc/loadavg`, `/proc/pressure/*`, `/proc/meminfo`,
  and `/proc/mounts`.
- Inspects only top-level mount points (`/`, `/mnt/disk1`, `/mnt/disk2`) via `os.stat`
  (`follow_symlinks=False`) and `os.statvfs`.
- Zero writes to `/mnt/disk1` or `/mnt/disk2`; zero media directory traversal.
- Atomic file publication: writes to `<output>.tmp`, calls `fsync()`, sets mode `0o644`
  (single regular file, `st_nlink == 1`), and atomically replaces `<output>` via `os.replace()`
  so `homeagentp-core` never reads a half-written JSON file.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from homeagentp_core.modules.nas.collector import (
    HOST_SNAPSHOT_SCHEMA_VERSION,
    StatFunc,
    StatVfsFunc,
    _default_lstat,
    collect_cpu_telemetry,
    collect_memory_telemetry,
    inspect_mount_point,
)
from homeagentp_core.modules.nas.parsers import parse_proc_mounts


def build_host_snapshot_payload(
    *,
    proc_root: Path = Path("/proc"),
    root_mount_path: str = "/",
    required_mounts: list[str] | None = None,
    ttl_seconds: int = 120,
    sample_delay_seconds: float = 0.05,
    stat_fn: StatFunc = _default_lstat,
    statvfs_fn: StatVfsFunc = os.statvfs,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build a schema-compliant `homeagentp.nas_host.v1` snapshot dictionary from host `/proc`."""
    ref_now = now or datetime.now(UTC)
    mounts_to_check = (
        required_mounts if required_mounts is not None else ["/mnt/disk1", "/mnt/disk2"]
    )

    cpu = collect_cpu_telemetry(proc_root, sample_delay_seconds=sample_delay_seconds)
    memory = collect_memory_telemetry(proc_root)

    mounts_file = proc_root / "mounts"
    try:
        mounts_text = mounts_file.read_text(encoding="utf-8")
        proc_mounts = parse_proc_mounts(mounts_text)
    except (OSError, ValueError) as exc:
        all_paths = [root_mount_path, *[m for m in mounts_to_check if m != root_mount_path]]
        mounts_list: list[dict[str, Any]] = [
            {
                "path": p,
                "mount_point": p,
                "required": p != root_mount_path,
                "require_distinct_device": p != root_mount_path,
                "status": "unavailable",
                "healthy": False,
                "is_mounted": False,
                "is_root_fallback": False,
                "device": "",
                "fstype": "",
                "read_only": None,
                "total_bytes": None,
                "used_bytes": None,
                "available_bytes": None,
                "usage_percent": None,
                "reason": f"Cannot read {mounts_file}: {exc}",
            }
            for p in all_paths
        ]
    else:
        mounts_list = [
            inspect_mount_point(
                root_mount_path,
                proc_mounts,
                root_mount_path=root_mount_path,
                inspect_fs_path=root_mount_path,
                require_distinct_device=False,
                stat_fn=stat_fn,
                statvfs_fn=statvfs_fn,
            )
        ]
        for mp in mounts_to_check:
            if mp == root_mount_path:
                continue
            mounts_list.append(
                inspect_mount_point(
                    mp,
                    proc_mounts,
                    root_mount_path=root_mount_path,
                    inspect_fs_path=mp,
                    require_distinct_device=True,
                    stat_fn=stat_fn,
                    statvfs_fn=statvfs_fn,
                )
            )

    return {
        "schema_version": HOST_SNAPSHOT_SCHEMA_VERSION,
        "generated_at": ref_now.isoformat(),
        "ttl_seconds": int(ttl_seconds),
        "cpu": cpu,
        "memory": memory,
        "mounts": mounts_list,
    }


def write_atomic_json_snapshot(output_path: Path, payload: dict[str, Any]) -> Path:
    """Write a JSON snapshot atomically via `.tmp` + `fchmod(0o644)` + `fsync` + `os.replace`.

    Ensures the resulting file is a regular single-link file (`st_nlink == 1`) with mode `0644`
    (`rw-r--r--`) so `homeagentp-core` running as non-root UID/GID `10001:10001` can read it
    across a `:ro` bind mount.
    """
    if output_path.is_symlink() or output_path.parent.is_symlink():
        raise PermissionError(f"Symlinked snapshot output path is prohibited: {output_path}")

    resolved_parent = output_path.parent.resolve()
    resolved_parent.mkdir(parents=True, exist_ok=True)
    if not os.access(resolved_parent, os.W_OK | os.X_OK):
        raise PermissionError(
            f"Snapshot directory is not writable by current user (uid={os.geteuid()}): "
            f"{resolved_parent}"
        )

    resolved_out = resolved_parent / output_path.name
    tmp_path = resolved_out.with_name(f".{resolved_out.name}.{os.getpid()}.tmp")

    serialized = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    try:
        fd = os.open(
            str(tmp_path),
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0),
            0o644,
        )
        try:
            os.fchmod(fd, 0o644)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise

        os.replace(tmp_path, resolved_out)
        dir_fd = os.open(str(resolved_parent), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)

    return resolved_out


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for generating an atomic NAS host telemetry snapshot."""
    parser = argparse.ArgumentParser(
        description="Generate an atomic read-only HomeAgentP NAS host telemetry snapshot."
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Destination path for nas_host_snapshot.json",
    )
    parser.add_argument(
        "--proc-root",
        type=Path,
        default=Path("/proc"),
        help="Path to host /proc directory (default: /proc)",
    )
    parser.add_argument(
        "--root-mount",
        type=str,
        default="/",
        help="Path to host root mount point (default: /)",
    )
    parser.add_argument(
        "--required-mounts",
        type=str,
        default="/mnt/disk1,/mnt/disk2",
        help="Comma-separated required HDD mount points (default: /mnt/disk1,/mnt/disk2)",
    )
    parser.add_argument(
        "--ttl-seconds",
        type=int,
        default=120,
        help="Snapshot validity TTL in seconds (default: 120)",
    )
    args = parser.parse_args(argv)

    req_mounts = [m.strip() for m in str(args.required_mounts).split(",") if m.strip()]
    payload = build_host_snapshot_payload(
        proc_root=args.proc_root,
        root_mount_path=args.root_mount,
        required_mounts=req_mounts,
        ttl_seconds=args.ttl_seconds,
    )
    write_atomic_json_snapshot(args.output, payload)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
