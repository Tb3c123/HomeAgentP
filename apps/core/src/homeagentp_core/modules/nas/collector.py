"""Read-only NAS Guardian telemetry collector, Mount Guardian, Container Health & Alerts.

Security & Boundary Invariants (Phase 02 Hardening — P02-F01..F04):
1. Host vs Container Telemetry Boundary (P02-F01):
   - NEVER assumes the container's own `/proc`, `/`, or `/proc/mounts` represents the NAS host.
   - If `direct_host_fs` mode is selected while `/proc`, `/`, or `/proc/mounts` points to the
     unverified container namespace, telemetry returns `status='unavailable'` with
     `boundary_reason='container_namespace_rejected'` and NEVER falsely reports `/mnt/disk1` or
     `/mnt/disk2` as unmounted.
   - Recommended production/CasaOS mode is `host_snapshot`, where a least-privilege host collector
     writes an atomic JSON snapshot (`nas_host_snapshot.json`) into a read-only directory mounted
     into Core (`HOMEAGENTP_REPORTS_DIR`).
2. Container Snapshot Schema, TTL & Freshness (P02-F03):
   - Validates `schema_version`, `generated_at` (ISO-8601 UTC), `ttl_seconds`, and `containers`.
   - Computes snapshot age against `min(ttl_seconds, settings.nas_snapshot_max_age_seconds)`.
   - If expired, returns `status='stale'` (`fresh=False`) and does NOT treat stale entries as live.
3. Alert Lifecycle & Deduplication (P02-F04):
   - Alerts are deduplicated by `alert_key` (`{component}:{code}`).
   - Active alerts update `last_seen_at`, `message`, `metric_value`, and increment `occurrences`.
   - Alerts whose condition clears transition to `status='resolved'` with `resolved_at`.
   - Re-occurring alerts insert a new `'active'` record (preserving historical resolved intervals).
"""

from __future__ import annotations

import json
import os
import sqlite3
import stat
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from homeagentp_core.config import Settings
from homeagentp_core.modules.nas.parsers import (
    CpuTicks,
    MountEntry,
    compute_cpu_usage_percent,
    parse_proc_loadavg,
    parse_proc_meminfo,
    parse_proc_mounts,
    parse_proc_psi_pressure,
    parse_proc_stat_cpu,
)
from homeagentp_core.modules.scripts.safe_reader import (
    PathSecurityError,
    read_allowlisted_text_file,
)

StatFunc = Callable[[str], os.stat_result]
StatVfsFunc = Callable[[str], os.statvfs_result]

_PREV_CPU_TICKS: dict[str, CpuTicks] = {}
_LAST_PERSIST_EPOCH: dict[str, float] = {}

CONTAINER_SNAPSHOT_SCHEMA_VERSION = "homeagentp.containers.v1"
HOST_SNAPSHOT_SCHEMA_VERSION = "homeagentp.nas_host.v1"


def _default_lstat(path: str) -> os.stat_result:
    return os.stat(path, follow_symlinks=False)


def _read_proc_text(proc_root: Path, rel_name: str) -> str:
    """Safely read a virtual file under proc_root."""
    target = proc_root / rel_name
    if target.is_symlink():
        raise PermissionError(f"Symlink prohibited for proc file: {target}")
    return target.read_text(encoding="utf-8")


def parse_iso8601_utc(value: str) -> datetime:
    """Parse an ISO-8601 timestamp into a timezone-aware UTC datetime."""
    cleaned = value.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    dt = datetime.fromisoformat(cleaned)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def check_snapshot_freshness(
    generated_at_raw: Any,
    ttl_seconds_raw: Any,
    *,
    max_age_seconds: int,
    now: datetime | None = None,
) -> tuple[bool, float | None, int, str | None]:
    """Validate snapshot generated_at and TTL; return (is_fresh, age_sec, effective_ttl, reason)."""
    if not isinstance(generated_at_raw, str) or not generated_at_raw.strip():
        return False, None, max_age_seconds, "Snapshot missing valid 'generated_at' timestamp."
    try:
        gen_dt = parse_iso8601_utc(generated_at_raw)
    except ValueError as exc:
        return False, None, max_age_seconds, f"Invalid 'generated_at' ISO-8601 timestamp: {exc}"

    ttl_val = max_age_seconds
    if isinstance(ttl_seconds_raw, int) and ttl_seconds_raw > 0:
        ttl_val = min(ttl_seconds_raw, max_age_seconds)
    elif ttl_seconds_raw is not None and not isinstance(ttl_seconds_raw, int):
        return False, None, max_age_seconds, "Snapshot 'ttl_seconds' must be a positive integer."

    ref_now = now or datetime.now(UTC)
    age_seconds = round((ref_now - gen_dt).total_seconds(), 2)
    if age_seconds < -30.0:
        return (
            False,
            age_seconds,
            ttl_val,
            f"Snapshot timestamp is in the future (age={age_seconds}s).",
        )
    if age_seconds > ttl_val:
        return (
            False,
            age_seconds,
            ttl_val,
            f"Snapshot is stale (age {age_seconds}s > TTL {ttl_val}s).",
        )
    return True, max(0.0, age_seconds), ttl_val, None


def verify_direct_host_boundary(
    settings: Settings,
    *,
    proc_mounts: dict[str, MountEntry] | None = None,
) -> tuple[bool, str | None]:
    """Verify that direct_host_fs paths do not accidentally inspect the container's own namespace.

    In a container (Docker/CasaOS), `/proc` and `/` reflect the container's PID/mount namespace
    and overlayfs root (`overlay`), NOT the Debian 12 NAS host. Unless `nas_proc_root` and
    `nas_root_mount_path` are explicitly pointed to dedicated host mounts (or custom test paths)
    and the root mount is not container `overlay`, direct inspection is rejected as `unavailable`.
    """
    proc_str = os.path.normpath(str(settings.nas_proc_root))
    root_str = os.path.normpath(str(settings.nas_root_mount_path))

    if proc_str == "/proc" or root_str == "/":
        return (
            False,
            "Direct host telemetry rejected: nas_proc_root (/proc) or nas_root_mount_path (/) "
            "points to the local process/container namespace instead of an explicit host mount "
            "(/host/proc, /host/root) or host_snapshot mode.",
        )

    if not settings.nas_proc_root.exists() or not settings.nas_root_mount_path.exists():
        return (
            False,
            f"Direct host telemetry paths do not exist ({proc_str}, {root_str}).",
        )

    if proc_mounts is not None:
        root_entry = proc_mounts.get("/")
        if root_entry is not None and root_entry.fstype in {"overlay", "aufs", "shm"}:
            return (
                False,
                f"Direct host telemetry rejected: mounts table reports container root fstype "
                f"'{root_entry.fstype}' rather than a physical host filesystem.",
            )

    return True, None


def collect_cpu_telemetry(
    proc_root: Path,
    *,
    sample_delay_seconds: float = 0.02,
) -> dict[str, Any]:
    """Collect read-only CPU usage, load averages, and PSI pressure from proc_root."""
    key = str(proc_root)
    cpu_status = "ok"
    usage_percent: float | None = None
    logical_cores: int | None = None
    error_reason: str | None = None

    try:
        stat_text_1 = _read_proc_text(proc_root, "stat")
        ticks_1 = parse_proc_stat_cpu(stat_text_1)
        logical_cores = ticks_1.logical_cores

        prev_ticks = _PREV_CPU_TICKS.get(key)
        if prev_ticks is not None:
            usage_percent = compute_cpu_usage_percent(prev_ticks, ticks_1)

        if usage_percent is None and sample_delay_seconds > 0:
            time.sleep(sample_delay_seconds)
            stat_text_2 = _read_proc_text(proc_root, "stat")
            ticks_2 = parse_proc_stat_cpu(stat_text_2)
            usage_percent = compute_cpu_usage_percent(ticks_1, ticks_2)
            _PREV_CPU_TICKS[key] = ticks_2
        else:
            _PREV_CPU_TICKS[key] = ticks_1
    except (OSError, ValueError) as exc:
        cpu_status = "unavailable"
        error_reason = str(exc)

    load_1m: float | None = None
    load_5m: float | None = None
    load_15m: float | None = None
    try:
        load_text = _read_proc_text(proc_root, "loadavg")
        load_1m, load_5m, load_15m = parse_proc_loadavg(load_text)
    except (OSError, ValueError) as exc:
        cpu_status = "unavailable" if usage_percent is None else "degraded"
        error_reason = error_reason or str(exc)

    try:
        psi_text = _read_proc_text(proc_root, "pressure/cpu")
        pressure = parse_proc_psi_pressure(psi_text)
    except (OSError, ValueError) as exc:
        pressure = {"status": "unavailable", "some": None, "full": None, "reason": str(exc)}

    return {
        "status": cpu_status,
        "reason": error_reason,
        "usage_percent": usage_percent,
        "logical_cores": logical_cores,
        "load_1m": load_1m,
        "load_5m": load_5m,
        "load_15m": load_15m,
        "pressure": {
            "status": pressure.get("status", "unavailable"),
            "some": pressure.get("some"),
            "full": pressure.get("full"),
        },
    }


def collect_memory_telemetry(proc_root: Path) -> dict[str, Any]:
    """Collect read-only RAM, Swap, and PSI memory pressure from proc_root."""
    try:
        meminfo_text = _read_proc_text(proc_root, "meminfo")
        mem = parse_proc_meminfo(meminfo_text)
        mem_status = "ok"
        reason: str | None = None
    except (OSError, ValueError) as exc:
        mem = {
            "total_bytes": None,
            "available_bytes": None,
            "used_bytes": None,
            "usage_percent": None,
            "swap_total_bytes": None,
            "swap_free_bytes": None,
            "swap_used_bytes": None,
            "swap_usage_percent": None,
        }
        mem_status = "unavailable"
        reason = str(exc)

    try:
        psi_text = _read_proc_text(proc_root, "pressure/memory")
        pressure = parse_proc_psi_pressure(psi_text)
    except (OSError, ValueError) as exc:
        pressure = {"status": "unavailable", "some": None, "full": None, "reason": str(exc)}

    return {
        "status": mem_status,
        "reason": reason,
        **mem,
        "pressure": {
            "status": pressure.get("status", "unavailable"),
            "some": pressure.get("some"),
            "full": pressure.get("full"),
        },
    }


def inspect_mount_point(
    mount_path: str,
    proc_mounts: dict[str, MountEntry],
    *,
    root_mount_path: str = "/host/root",
    inspect_fs_path: str | None = None,
    require_distinct_device: bool = True,
    stat_fn: StatFunc = _default_lstat,
    statvfs_fn: StatVfsFunc = os.statvfs,
) -> dict[str, Any]:
    """Inspect a single host mount point in read-only mode and detect unmounted root-fs fallback.

    `mount_path` is the canonical NAS host path (e.g. `/`, `/mnt/disk1`, `/mnt/disk2`) looked up
    in the host's `/proc/mounts`. `inspect_fs_path` is the local read-only path where that mount
    is exposed for `lstat`/`statvfs` (defaults to `mount_path`).
    """
    fs_target = inspect_fs_path if inspect_fs_path is not None else mount_path
    base_result: dict[str, Any] = {
        "path": mount_path,
        "mount_point": mount_path,
        "required": require_distinct_device,
        "require_distinct_device": require_distinct_device,
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
        "reason": "",
    }

    try:
        target_stat = stat_fn(fs_target)
    except FileNotFoundError:
        base_result["status"] = "missing"
        base_result["reason"] = f"Mount directory does not exist: {mount_path}"
        return base_result
    except PermissionError as exc:
        base_result["status"] = "permission_denied"
        base_result["reason"] = f"Permission denied inspecting mount {mount_path}: {exc}"
        return base_result
    except OSError as exc:
        base_result["status"] = "unavailable"
        base_result["reason"] = f"OS error inspecting mount {mount_path}: {exc}"
        return base_result

    if stat.S_ISLNK(target_stat.st_mode):
        base_result["status"] = "invalid_symlink"
        base_result["reason"] = f"Mount point must not be a symlink: {mount_path}"
        return base_result

    if not stat.S_ISDIR(target_stat.st_mode):
        base_result["status"] = "invalid_mount"
        base_result["reason"] = f"Mount point is not a directory: {mount_path}"
        return base_result

    mount_entry = proc_mounts.get(mount_path)

    if require_distinct_device:
        root_dev: int | None = None
        try:
            root_dev = stat_fn(root_mount_path).st_dev
        except OSError:
            root_dev = None

        same_as_root = root_dev is not None and target_stat.st_dev == root_dev
        if mount_entry is None or same_as_root:
            base_result["status"] = "unmounted_fallback"
            base_result["is_root_fallback"] = True
            base_result["reason"] = (
                f"Mount directory {mount_path} exists on the root filesystem, "
                "but the dedicated storage device is not mounted."
            )
            return base_result

    try:
        vfs = statvfs_fn(fs_target)
    except PermissionError as exc:
        base_result["status"] = "permission_denied"
        base_result["reason"] = f"Permission denied in statvfs for {mount_path}: {exc}"
        return base_result
    except OSError as exc:
        base_result["status"] = "unavailable"
        base_result["reason"] = f"statvfs failed for {mount_path}: {exc}"
        return base_result

    frsize = int(vfs.f_frsize or vfs.f_bsize or 4096)
    total_bytes = max(0, int(vfs.f_blocks) * frsize)
    free_bytes = max(0, int(vfs.f_bfree) * frsize)
    available_bytes = max(0, int(vfs.f_bavail) * frsize)
    used_bytes = max(0, total_bytes - free_bytes)
    usage_percent = (
        round(((total_bytes - available_bytes) / total_bytes) * 100.0, 2)
        if total_bytes > 0
        else 0.0
    )

    options = mount_entry.options if mount_entry else []
    base_result.update(
        {
            "status": "mounted",
            "healthy": True,
            "is_mounted": True,
            "is_root_fallback": False,
            "device": mount_entry.device if mount_entry else "unknown",
            "fstype": mount_entry.fstype if mount_entry else "unknown",
            "read_only": ("ro" in options) if options else False,
            "total_bytes": total_bytes,
            "used_bytes": used_bytes,
            "available_bytes": available_bytes,
            "usage_percent": usage_percent,
            "reason": "",
        }
    )
    return base_result


def _unavailable_mounts_list(
    settings: Settings, reason: str, status: str = "unavailable"
) -> list[dict[str, Any]]:
    all_paths = ["/", *[m for m in settings.nas_required_mounts if m != "/"]]
    return [
        {
            "path": p,
            "mount_point": p,
            "required": p != "/",
            "require_distinct_device": p != "/",
            "status": status,
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
            "reason": reason,
        }
        for p in all_paths
    ]


def _mounts_list_to_dict(mounts_list: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(m["mount_point"]): m for m in mounts_list}


def inspect_container_health(
    settings: Settings,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Read optional least-privilege container health snapshot with schema + TTL validation."""
    rel_path = settings.nas_container_snapshot_rel_path.strip()

    def _build_services_map(state_val: str, reason_val: str) -> dict[str, dict[str, Any]]:
        return {
            svc: {
                "name": svc,
                "status": state_val,
                "state": state_val,
                "healthy": None,
                "memory_bytes": None,
                "memory_used_bytes": None,
                "memory_limit_bytes": None,
                "memory_percent": None,
                "cpu_percent": None,
                "restart_count": None,
                "reason": reason_val,
            }
            for svc in settings.nas_expected_services
        }

    if not rel_path:
        msg = (
            "No read-only container snapshot configured "
            "(mounting /var/run/docker.sock is prohibited by B+ security policy)."
        )
        services_map = _build_services_map("unavailable", msg)
        return {
            "status": "unavailable",
            "docker_socket_mounted": False,
            "source": "not_configured",
            "schema_version": None,
            "generated_at": None,
            "ttl_seconds": settings.nas_snapshot_max_age_seconds,
            "age_seconds": None,
            "fresh": False,
            "reason": msg,
            "services": services_map,
            "services_list": list(services_map.values()),
        }

    try:
        safe_file = read_allowlisted_text_file(settings.reports_dir, rel_path)
        payload = json.loads(safe_file.content)
        if not isinstance(payload, dict) or not isinstance(payload.get("containers"), list):
            raise ValueError("Container snapshot JSON must contain a 'containers' list.")
        schema_ver = str(payload.get("schema_version", CONTAINER_SNAPSHOT_SCHEMA_VERSION))
        if schema_ver != CONTAINER_SNAPSHOT_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported container snapshot schema_version '{schema_ver}' "
                f"(expected '{CONTAINER_SNAPSHOT_SCHEMA_VERSION}')."
            )
    except (FileNotFoundError, PathSecurityError, ValueError, json.JSONDecodeError) as exc:
        msg = f"Container snapshot unavailable or invalid: {exc}"
        services_map = _build_services_map("unavailable", msg)
        return {
            "status": "unavailable",
            "docker_socket_mounted": False,
            "source": rel_path,
            "schema_version": None,
            "generated_at": None,
            "ttl_seconds": settings.nas_snapshot_max_age_seconds,
            "age_seconds": None,
            "fresh": False,
            "reason": msg,
            "services": services_map,
            "services_list": list(services_map.values()),
        }

    is_fresh, age_sec, eff_ttl, fresh_err = check_snapshot_freshness(
        payload.get("generated_at"),
        payload.get("ttl_seconds"),
        max_age_seconds=settings.nas_snapshot_max_age_seconds,
        now=now,
    )
    if not is_fresh:
        stale_msg = fresh_err or "Container snapshot is stale or missing generated_at."
        services_map = _build_services_map("stale", stale_msg)
        return {
            "status": "stale",
            "docker_socket_mounted": False,
            "source": rel_path,
            "schema_version": CONTAINER_SNAPSHOT_SCHEMA_VERSION,
            "generated_at": payload.get("generated_at"),
            "ttl_seconds": eff_ttl,
            "age_seconds": age_sec,
            "fresh": False,
            "reason": stale_msg,
            "services": services_map,
            "services_list": list(services_map.values()),
        }

    by_name: dict[str, dict[str, Any]] = {}
    for item in payload["containers"]:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            by_name[item["name"].strip().lower()] = item

    services_map = {}
    any_unhealthy = False
    for svc in settings.nas_expected_services:
        raw = by_name.get(svc.lower())
        if raw is None:
            any_unhealthy = True
            services_map[svc] = {
                "name": svc,
                "status": "missing",
                "state": "missing",
                "healthy": False,
                "memory_bytes": None,
                "memory_used_bytes": None,
                "memory_limit_bytes": None,
                "memory_percent": None,
                "cpu_percent": None,
                "restart_count": None,
                "reason": "Service not present in container snapshot.",
            }
            continue

        state_str = str(raw.get("state", "unknown")).lower()
        mem_used = raw.get("memory_used_bytes")
        if mem_used is None:
            mem_used = raw.get("memory_bytes")
        mem_limit = raw.get("memory_limit_bytes")
        mem_pct: float | None = None
        if (
            isinstance(mem_used, int)
            and isinstance(mem_limit, int)
            and mem_limit > 0
            and mem_used >= 0
        ):
            mem_pct = round((mem_used / mem_limit) * 100.0, 2)

        cpu_val = raw.get("cpu_percent")
        cpu_pct = round(float(cpu_val), 2) if isinstance(cpu_val, (int, float)) else None
        restarts = raw.get("restart_count")
        restart_cnt = int(restarts) if isinstance(restarts, int) and restarts >= 0 else 0
        is_running = state_str == "running"
        if not is_running:
            any_unhealthy = True

        services_map[svc] = {
            "name": svc,
            "status": "running" if is_running else state_str,
            "state": state_str,
            "healthy": is_running,
            "memory_bytes": mem_used if isinstance(mem_used, int) else None,
            "memory_used_bytes": mem_used if isinstance(mem_used, int) else None,
            "memory_limit_bytes": mem_limit if isinstance(mem_limit, int) else None,
            "memory_percent": mem_pct,
            "cpu_percent": cpu_pct,
            "restart_count": restart_cnt,
            "reason": "",
        }

    return {
        "status": "degraded" if any_unhealthy else "ok",
        "docker_socket_mounted": False,
        "source": rel_path,
        "schema_version": CONTAINER_SNAPSHOT_SCHEMA_VERSION,
        "generated_at": str(payload.get("generated_at")),
        "ttl_seconds": eff_ttl,
        "age_seconds": age_sec,
        "fresh": True,
        "reason": "",
        "services": services_map,
        "services_list": list(services_map.values()),
    }


def evaluate_nas_alerts(
    settings: Settings,
    cpu: dict[str, Any],
    memory: dict[str, Any],
    mounts_list: list[dict[str, Any]],
    containers: dict[str, Any],
    *,
    host_telemetry_status: str = "ok",
    host_telemetry_reason: str | None = None,
    now_iso: str | None = None,
) -> list[dict[str, Any]]:
    """Evaluate read-only alert thresholds against collected NAS telemetry."""
    alerts: list[dict[str, Any]] = []
    ts_iso = now_iso or datetime.now(UTC).isoformat()

    if host_telemetry_status == "stale":
        alerts.append(
            {
                "alert_key": "host_telemetry:snapshot.stale",
                "code": "snapshot.stale",
                "severity": "warning",
                "category": "host_telemetry",
                "component": "host_telemetry",
                "target": "nas_host_snapshot",
                "message": host_telemetry_reason or "Host telemetry snapshot is stale.",
                "metric_value": None,
                "threshold_value": float(settings.nas_snapshot_max_age_seconds),
                "details": {"status": "stale"},
                "status": "active",
                "created_at": ts_iso,
            }
        )

    # 1. CPU threshold checks
    cpu_pct = cpu.get("usage_percent")
    if isinstance(cpu_pct, (int, float)):
        if cpu_pct >= settings.nas_cpu_critical_percent:
            alerts.append(
                {
                    "alert_key": "cpu:cpu.usage_critical",
                    "code": "cpu.usage_critical",
                    "severity": "critical",
                    "category": "cpu",
                    "component": "cpu",
                    "target": "cpu",
                    "message": (
                        f"CPU usage is critical ({cpu_pct}% >= "
                        f"{settings.nas_cpu_critical_percent}%)."
                    ),
                    "metric_value": float(cpu_pct),
                    "threshold_value": float(settings.nas_cpu_critical_percent),
                    "details": {"usage_percent": cpu_pct},
                    "status": "active",
                    "created_at": ts_iso,
                }
            )
        elif cpu_pct >= settings.nas_cpu_warn_percent:
            alerts.append(
                {
                    "alert_key": "cpu:cpu.usage_warning",
                    "code": "cpu.usage_warning",
                    "severity": "warning",
                    "category": "cpu",
                    "component": "cpu",
                    "target": "cpu",
                    "message": (
                        f"CPU usage is elevated ({cpu_pct}% >= "
                        f"{settings.nas_cpu_warn_percent}%)."
                    ),
                    "metric_value": float(cpu_pct),
                    "threshold_value": float(settings.nas_cpu_warn_percent),
                    "details": {"usage_percent": cpu_pct},
                    "status": "active",
                    "created_at": ts_iso,
                }
            )

    # 2. Memory threshold checks
    ram_pct = memory.get("usage_percent")
    if isinstance(ram_pct, (int, float)):
        if ram_pct >= settings.nas_ram_critical_percent:
            alerts.append(
                {
                    "alert_key": "memory:ram.usage_critical",
                    "code": "ram.usage_critical",
                    "severity": "critical",
                    "category": "memory",
                    "component": "memory",
                    "target": "memory",
                    "message": (
                        f"Memory usage is critical ({ram_pct}% >= "
                        f"{settings.nas_ram_critical_percent}%)."
                    ),
                    "metric_value": float(ram_pct),
                    "threshold_value": float(settings.nas_ram_critical_percent),
                    "details": {"usage_percent": ram_pct},
                    "status": "active",
                    "created_at": ts_iso,
                }
            )
        elif ram_pct >= settings.nas_ram_warn_percent:
            alerts.append(
                {
                    "alert_key": "memory:ram.usage_warning",
                    "code": "ram.usage_warning",
                    "severity": "warning",
                    "category": "memory",
                    "component": "memory",
                    "target": "memory",
                    "message": (
                        f"Memory usage is elevated ({ram_pct}% >= "
                        f"{settings.nas_ram_warn_percent}%)."
                    ),
                    "metric_value": float(ram_pct),
                    "threshold_value": float(settings.nas_ram_warn_percent),
                    "details": {"usage_percent": ram_pct},
                    "status": "active",
                    "created_at": ts_iso,
                }
            )

    # 3. Mount Guardian & Disk Capacity checks (only when host telemetry is verified/fresh)
    for m in mounts_list:
        mp = str(m.get("mount_point") or m.get("path") or "")
        st = str(m.get("status", "unavailable"))
        comp = f"mount:{mp}"
        if st in {"missing", "unmounted_fallback", "invalid_symlink", "invalid_mount"}:
            code = f"mount.{st}"
            alerts.append(
                {
                    "alert_key": f"{comp}:{code}",
                    "code": code,
                    "severity": "critical",
                    "category": "mount_guardian",
                    "component": comp,
                    "target": mp,
                    "message": m.get("reason") or f"Mount point {mp} is in state '{st}'.",
                    "metric_value": None,
                    "threshold_value": None,
                    "details": {"mount_point": mp, "status": st},
                    "status": "active",
                    "created_at": ts_iso,
                }
            )
        elif st == "mounted":
            disk_pct = m.get("usage_percent")
            if isinstance(disk_pct, (int, float)):
                if disk_pct >= settings.nas_disk_critical_percent:
                    alerts.append(
                        {
                            "alert_key": f"{comp}:disk.usage_critical",
                            "code": "disk.usage_critical",
                            "severity": "critical",
                            "category": "storage",
                            "component": comp,
                            "target": mp,
                            "message": (
                                f"Filesystem {mp} usage is critical ({disk_pct}% >= "
                                f"{settings.nas_disk_critical_percent}%)."
                            ),
                            "metric_value": float(disk_pct),
                            "threshold_value": float(settings.nas_disk_critical_percent),
                            "details": {"mount_point": mp, "usage_percent": disk_pct},
                            "status": "active",
                            "created_at": ts_iso,
                        }
                    )
                elif disk_pct >= settings.nas_disk_warn_percent:
                    alerts.append(
                        {
                            "alert_key": f"{comp}:disk.usage_warning",
                            "code": "disk.usage_warning",
                            "severity": "warning",
                            "category": "storage",
                            "component": comp,
                            "target": mp,
                            "message": (
                                f"Filesystem {mp} usage is high ({disk_pct}% >= "
                                f"{settings.nas_disk_warn_percent}%)."
                            ),
                            "metric_value": float(disk_pct),
                            "threshold_value": float(settings.nas_disk_warn_percent),
                            "details": {"mount_point": mp, "usage_percent": disk_pct},
                            "status": "active",
                            "created_at": ts_iso,
                        }
                    )

    # 4. Container Health checks
    c_status = containers.get("status")
    if c_status == "stale":
        alerts.append(
            {
                "alert_key": "containers:container.snapshot_stale",
                "code": "container.snapshot_stale",
                "severity": "warning",
                "category": "containers",
                "component": "containers",
                "target": str(containers.get("source", "containers_snapshot")),
                "message": str(containers.get("reason") or "Container snapshot is stale."),
                "metric_value": containers.get("age_seconds"),
                "threshold_value": float(
                    containers.get("ttl_seconds") or settings.nas_snapshot_max_age_seconds
                ),
                "details": {"source": containers.get("source")},
                "status": "active",
                "created_at": ts_iso,
            }
        )
    elif c_status in {"ok", "degraded"} and containers.get("fresh", False):
        services_iter = (
            containers["services"].values()
            if isinstance(containers.get("services"), dict)
            else containers.get("services", [])
        )
        for svc in services_iter:
            name = str(svc.get("name", "unknown"))
            state_str = str(svc.get("state", "unknown"))
            comp = f"container:{name}"
            if state_str not in {"running", "unavailable", "stale"}:
                alerts.append(
                    {
                        "alert_key": f"{comp}:container.not_running",
                        "code": "container.not_running",
                        "severity": "critical",
                        "category": "containers",
                        "component": comp,
                        "target": name,
                        "message": f"Configured service '{name}' is in state '{state_str}'.",
                        "metric_value": None,
                        "threshold_value": None,
                        "details": {"service": name, "state": state_str},
                        "status": "active",
                        "created_at": ts_iso,
                    }
                )
            mem_pct = svc.get("memory_percent")
            if isinstance(mem_pct, (int, float)):
                if mem_pct >= settings.nas_container_mem_critical_percent:
                    alerts.append(
                        {
                            "alert_key": f"{comp}:container.memory_critical",
                            "code": "container.memory_critical",
                            "severity": "critical",
                            "category": "containers",
                            "component": comp,
                            "target": name,
                            "message": (
                                f"Container '{name}' memory usage is critical "
                                f"({mem_pct}% of limit)."
                            ),
                            "metric_value": float(mem_pct),
                            "threshold_value": float(settings.nas_container_mem_critical_percent),
                            "details": {"service": name, "memory_percent": mem_pct},
                            "status": "active",
                            "created_at": ts_iso,
                        }
                    )
                elif mem_pct >= settings.nas_container_mem_warn_percent:
                    alerts.append(
                        {
                            "alert_key": f"{comp}:container.memory_warning",
                            "code": "container.memory_warning",
                            "severity": "warning",
                            "category": "containers",
                            "component": comp,
                            "target": name,
                            "message": (
                                f"Container '{name}' memory usage is elevated "
                                f"({mem_pct}% of limit)."
                            ),
                            "metric_value": float(mem_pct),
                            "threshold_value": float(settings.nas_container_mem_warn_percent),
                            "details": {"service": name, "memory_percent": mem_pct},
                            "status": "active",
                            "created_at": ts_iso,
                        }
                    )

    return alerts


def _collect_from_host_snapshot(
    settings: Settings,
    *,
    now: datetime,
) -> tuple[
    str,
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    list[dict[str, Any]],
    str | None,
]:
    """Read host CPU, RAM, and Mount telemetry from a least-privilege host JSON snapshot."""
    rel_path = settings.nas_host_snapshot_rel_path.strip()
    if not rel_path:
        reason = (
            "No host telemetry snapshot path configured "
            "(HOMEAGENTP_NAS_HOST_SNAPSHOT_REL_PATH)."
        )
        return (
            "unavailable",
            {
                "mode": "host_snapshot",
                "source": "not_configured",
                "host_verified": False,
                "fresh": False,
                "reason": reason,
            },
            {
                "status": "unavailable",
                "reason": reason,
                "usage_percent": None,
                "logical_cores": None,
                "load_1m": None,
                "load_5m": None,
                "load_15m": None,
                "pressure": {"status": "unavailable", "some": None, "full": None},
            },
            {
                "status": "unavailable",
                "reason": reason,
                "total_bytes": None,
                "available_bytes": None,
                "used_bytes": None,
                "usage_percent": None,
                "swap_total_bytes": None,
                "swap_free_bytes": None,
                "swap_used_bytes": None,
                "swap_usage_percent": None,
                "pressure": {"status": "unavailable", "some": None, "full": None},
            },
            _unavailable_mounts_list(settings, reason, status="unavailable"),
            reason,
        )

    try:
        safe_file = read_allowlisted_text_file(settings.reports_dir, rel_path)
        payload = json.loads(safe_file.content)
        if not isinstance(payload, dict):
            raise ValueError("Host snapshot JSON root must be an object.")
        schema_ver = str(payload.get("schema_version", HOST_SNAPSHOT_SCHEMA_VERSION))
        if schema_ver != HOST_SNAPSHOT_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported host snapshot schema_version '{schema_ver}' "
                f"(expected '{HOST_SNAPSHOT_SCHEMA_VERSION}')."
            )
    except (FileNotFoundError, PathSecurityError, ValueError, json.JSONDecodeError) as exc:
        reason = f"Host telemetry snapshot unavailable or invalid: {exc}"
        return (
            "unavailable",
            {
                "mode": "host_snapshot",
                "source": rel_path,
                "host_verified": False,
                "fresh": False,
                "reason": reason,
            },
            {
                "status": "unavailable",
                "reason": reason,
                "usage_percent": None,
                "logical_cores": None,
                "load_1m": None,
                "load_5m": None,
                "load_15m": None,
                "pressure": {"status": "unavailable", "some": None, "full": None},
            },
            {
                "status": "unavailable",
                "reason": reason,
                "total_bytes": None,
                "available_bytes": None,
                "used_bytes": None,
                "usage_percent": None,
                "swap_total_bytes": None,
                "swap_free_bytes": None,
                "swap_used_bytes": None,
                "swap_usage_percent": None,
                "pressure": {"status": "unavailable", "some": None, "full": None},
            },
            _unavailable_mounts_list(settings, reason, status="unavailable"),
            reason,
        )

    is_fresh, age_sec, eff_ttl, fresh_err = check_snapshot_freshness(
        payload.get("generated_at"),
        payload.get("ttl_seconds"),
        max_age_seconds=settings.nas_snapshot_max_age_seconds,
        now=now,
    )
    if not is_fresh:
        stale_msg = fresh_err or "Host telemetry snapshot is stale."
        return (
            "stale",
            {
                "mode": "host_snapshot",
                "source": rel_path,
                "schema_version": HOST_SNAPSHOT_SCHEMA_VERSION,
                "generated_at": payload.get("generated_at"),
                "ttl_seconds": eff_ttl,
                "age_seconds": age_sec,
                "host_verified": False,
                "fresh": False,
                "reason": stale_msg,
            },
            {
                "status": "stale",
                "reason": stale_msg,
                "usage_percent": None,
                "logical_cores": None,
                "load_1m": None,
                "load_5m": None,
                "load_15m": None,
                "pressure": {"status": "stale", "some": None, "full": None},
            },
            {
                "status": "stale",
                "reason": stale_msg,
                "total_bytes": None,
                "available_bytes": None,
                "used_bytes": None,
                "usage_percent": None,
                "swap_total_bytes": None,
                "swap_free_bytes": None,
                "swap_used_bytes": None,
                "swap_usage_percent": None,
                "pressure": {"status": "stale", "some": None, "full": None},
            },
            _unavailable_mounts_list(settings, stale_msg, status="unavailable"),
            stale_msg,
        )

    cpu_obj = payload.get("cpu")
    mem_obj = payload.get("memory")
    mounts_obj = payload.get("mounts")
    raw_cpu: dict[str, Any] = cpu_obj if isinstance(cpu_obj, dict) else {}
    raw_mem: dict[str, Any] = mem_obj if isinstance(mem_obj, dict) else {}
    raw_mounts: list[Any] = mounts_obj if isinstance(mounts_obj, list) else []

    cpu = {
        "status": str(raw_cpu.get("status", "ok")),
        "reason": raw_cpu.get("reason"),
        "usage_percent": raw_cpu.get("usage_percent"),
        "logical_cores": raw_cpu.get("logical_cores"),
        "load_1m": raw_cpu.get("load_1m"),
        "load_5m": raw_cpu.get("load_5m"),
        "load_15m": raw_cpu.get("load_15m"),
        "pressure": raw_cpu.get("pressure")
        if isinstance(raw_cpu.get("pressure"), dict)
        else {"status": "unavailable", "some": None, "full": None},
    }
    memory = {
        "status": str(raw_mem.get("status", "ok")),
        "reason": raw_mem.get("reason"),
        "total_bytes": raw_mem.get("total_bytes"),
        "available_bytes": raw_mem.get("available_bytes"),
        "used_bytes": raw_mem.get("used_bytes"),
        "usage_percent": raw_mem.get("usage_percent"),
        "swap_total_bytes": raw_mem.get("swap_total_bytes"),
        "swap_free_bytes": raw_mem.get("swap_free_bytes"),
        "swap_used_bytes": raw_mem.get("swap_used_bytes"),
        "swap_usage_percent": raw_mem.get("swap_usage_percent"),
        "pressure": raw_mem.get("pressure")
        if isinstance(raw_mem.get("pressure"), dict)
        else {"status": "unavailable", "some": None, "full": None},
    }

    by_mp: dict[str, dict[str, Any]] = {}
    for item in raw_mounts:
        if isinstance(item, dict):
            mp_val = item.get("mount_point") or item.get("path")
            if isinstance(mp_val, str):
                by_mp[mp_val] = item

    all_paths = ["/", *[m for m in settings.nas_required_mounts if m != "/"]]
    mounts_list: list[dict[str, Any]] = []
    for p in all_paths:
        m_raw = by_mp.get(p)
        if m_raw is None:
            mounts_list.append(
                {
                    "path": p,
                    "mount_point": p,
                    "required": p != "/",
                    "require_distinct_device": p != "/",
                    "status": "missing" if p != "/" else "unavailable",
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
                    "reason": f"Mount {p} missing from host snapshot.",
                }
            )
        else:
            st = str(m_raw.get("status", "unavailable"))
            mounts_list.append(
                {
                    "path": p,
                    "mount_point": p,
                    "required": p != "/",
                    "require_distinct_device": p != "/",
                    "status": st,
                    "healthy": st == "mounted",
                    "is_mounted": st == "mounted",
                    "is_root_fallback": st == "unmounted_fallback",
                    "device": str(m_raw.get("device") or ""),
                    "fstype": str(m_raw.get("fstype") or ""),
                    "read_only": m_raw.get("read_only"),
                    "total_bytes": m_raw.get("total_bytes"),
                    "used_bytes": m_raw.get("used_bytes"),
                    "available_bytes": m_raw.get("available_bytes"),
                    "usage_percent": m_raw.get("usage_percent"),
                    "reason": str(m_raw.get("reason") or ""),
                }
            )

    boundary = {
        "mode": "host_snapshot",
        "source": rel_path,
        "schema_version": HOST_SNAPSHOT_SCHEMA_VERSION,
        "generated_at": str(payload.get("generated_at")),
        "ttl_seconds": eff_ttl,
        "age_seconds": age_sec,
        "host_verified": True,
        "fresh": True,
        "reason": None,
    }
    return "ok", boundary, cpu, memory, mounts_list, None


def inspect_all_mounts(
    settings: Settings,
    *,
    stat_fn: StatFunc = _default_lstat,
    statvfs_fn: StatVfsFunc = os.statvfs,
) -> tuple[bool, str | None, list[dict[str, Any]]]:
    """Verify host mount boundary and inspect root + required NAS HDD mounts."""
    try:
        mounts_text = _read_proc_text(settings.nas_proc_root, "mounts")
        proc_mounts = parse_proc_mounts(mounts_text)
    except (OSError, ValueError) as exc:
        reason = f"Cannot read host mounts table ({settings.nas_proc_root}/mounts): {exc}"
        return False, reason, _unavailable_mounts_list(settings, reason)

    verified, boundary_err = verify_direct_host_boundary(settings, proc_mounts=proc_mounts)
    if not verified:
        reason = boundary_err or "Host telemetry boundary not verified."
        return False, reason, _unavailable_mounts_list(settings, reason)

    root_fs_path = str(settings.nas_root_mount_path)
    results: list[dict[str, Any]] = [
        inspect_mount_point(
            "/",
            proc_mounts,
            root_mount_path=root_fs_path,
            inspect_fs_path=root_fs_path,
            require_distinct_device=False,
            stat_fn=stat_fn,
            statvfs_fn=statvfs_fn,
        )
    ]

    for req_mount in settings.nas_required_mounts:
        if req_mount == "/":
            continue
        results.append(
            inspect_mount_point(
                req_mount,
                proc_mounts,
                root_mount_path=root_fs_path,
                inspect_fs_path=req_mount,
                require_distinct_device=True,
                stat_fn=stat_fn,
                statvfs_fn=statvfs_fn,
            )
        )
    return True, None, results


def collect_nas_telemetry(
    settings: Settings,
    *,
    stat_fn: StatFunc = _default_lstat,
    statvfs_fn: StatVfsFunc = os.statvfs,
    sample_delay_seconds: float = 0.02,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Collect a complete read-only NAS Guardian snapshot or return honest unavailable state."""
    ref_now = now or datetime.now(UTC)
    now_iso = ref_now.isoformat()
    thresholds = {
        "cpu_warn_percent": settings.nas_cpu_warn_percent,
        "cpu_critical_percent": settings.nas_cpu_critical_percent,
        "ram_warn_percent": settings.nas_ram_warn_percent,
        "ram_critical_percent": settings.nas_ram_critical_percent,
        "disk_warn_percent": settings.nas_disk_warn_percent,
        "disk_critical_percent": settings.nas_disk_critical_percent,
        "container_mem_warn_percent": settings.nas_container_mem_warn_percent,
        "container_mem_critical_percent": settings.nas_container_mem_critical_percent,
    }
    storage_safety = {
        "hdd_write_operations": 0,
        "media_tree_crawled": False,
        "docker_socket_used": False,
    }

    # Resolve effective telemetry mode:
    # - If adapter disabled -> 'disabled'
    # - If adapter enabled and telemetry_mode == 'disabled', auto-select 'host_snapshot' if
    #   host snapshot file exists in reports_dir, otherwise 'direct_host_fs' (which enforces
    #   verify_direct_host_boundary()).
    effective_mode = settings.nas_telemetry_mode
    if not settings.nas_adapter_enabled:
        effective_mode = "disabled"
    elif effective_mode == "disabled":
        candidate_snap = settings.reports_dir / settings.nas_host_snapshot_rel_path
        if settings.nas_host_snapshot_rel_path and candidate_snap.exists():
            effective_mode = "host_snapshot"
        else:
            effective_mode = "direct_host_fs"

    if effective_mode == "disabled":
        reason = (
            "NAS Guardian read-only adapter is disabled "
            "(set HOMEAGENTP_NAS_ADAPTER_ENABLED=true and configure "
            "host_snapshot or direct_host_fs)."
        )
        mounts_list = _unavailable_mounts_list(settings, "Adapter disabled")
        return {
            "status": "unavailable",
            "adapter_status": "unavailable",
            "adapter_enabled": False,
            "collected_at": now_iso,
            "collection_interval_seconds": settings.nas_collection_interval_seconds,
            "history_retention_limit": settings.nas_history_retention_limit,
            "reason": reason,
            "telemetry_boundary": {
                "mode": "disabled",
                "source": "none",
                "host_verified": False,
                "fresh": False,
                "reason": reason,
            },
            "cpu": {
                "status": "unavailable",
                "reason": "Adapter disabled",
                "usage_percent": None,
                "logical_cores": None,
                "load_1m": None,
                "load_5m": None,
                "load_15m": None,
                "pressure": {"status": "unavailable", "some": None, "full": None},
            },
            "memory": {
                "status": "unavailable",
                "reason": "Adapter disabled",
                "total_bytes": None,
                "available_bytes": None,
                "used_bytes": None,
                "usage_percent": None,
                "swap_total_bytes": None,
                "swap_free_bytes": None,
                "swap_used_bytes": None,
                "swap_usage_percent": None,
                "pressure": {"status": "unavailable", "some": None, "full": None},
            },
            "mounts": _mounts_list_to_dict(mounts_list),
            "mounts_list": mounts_list,
            "containers": inspect_container_health(settings, now=ref_now),
            "alerts": [],
            "thresholds": thresholds,
            "storage_safety": storage_safety,
        }

    containers = inspect_container_health(settings, now=ref_now)

    if effective_mode == "host_snapshot":
        host_st, boundary, cpu, memory, mounts_list, host_reason = _collect_from_host_snapshot(
            settings, now=ref_now
        )
    else:
        # direct_host_fs mode: verify boundary first!
        verified, boundary_err, mounts_list = inspect_all_mounts(
            settings, stat_fn=stat_fn, statvfs_fn=statvfs_fn
        )
        if not verified:
            reason = boundary_err or "Direct host boundary verification failed."
            return {
                "status": "unavailable",
                "adapter_status": "unavailable",
                "adapter_enabled": True,
                "collected_at": now_iso,
                "collection_interval_seconds": settings.nas_collection_interval_seconds,
                "history_retention_limit": settings.nas_history_retention_limit,
                "reason": reason,
                "telemetry_boundary": {
                    "mode": "direct_host_fs",
                    "source": str(settings.nas_proc_root),
                    "host_verified": False,
                    "fresh": False,
                    "reason": reason,
                },
                "cpu": {
                    "status": "unavailable",
                    "reason": reason,
                    "usage_percent": None,
                    "logical_cores": None,
                    "load_1m": None,
                    "load_5m": None,
                    "load_15m": None,
                    "pressure": {"status": "unavailable", "some": None, "full": None},
                },
                "memory": {
                    "status": "unavailable",
                    "reason": reason,
                    "total_bytes": None,
                    "available_bytes": None,
                    "used_bytes": None,
                    "usage_percent": None,
                    "swap_total_bytes": None,
                    "swap_free_bytes": None,
                    "swap_used_bytes": None,
                    "swap_usage_percent": None,
                    "pressure": {"status": "unavailable", "some": None, "full": None},
                },
                "mounts": _mounts_list_to_dict(mounts_list),
                "mounts_list": mounts_list,
                "containers": containers,
                "alerts": [],
                "thresholds": thresholds,
                "storage_safety": storage_safety,
            }

        cpu = collect_cpu_telemetry(
            settings.nas_proc_root, sample_delay_seconds=sample_delay_seconds
        )
        memory = collect_memory_telemetry(settings.nas_proc_root)
        host_st = "ok"
        host_reason = None
        boundary = {
            "mode": "direct_host_fs",
            "source": str(settings.nas_proc_root),
            "host_verified": True,
            "fresh": True,
            "reason": None,
        }

    alerts = evaluate_nas_alerts(
        settings,
        cpu,
        memory,
        mounts_list,
        containers,
        host_telemetry_status=host_st,
        host_telemetry_reason=host_reason,
        now_iso=now_iso,
    )

    if host_st == "unavailable" or (
        cpu["status"] == "unavailable" and memory["status"] == "unavailable"
    ):
        adapter_status = "unavailable"
    elif host_st == "stale":
        adapter_status = "stale"
    elif any(a["severity"] == "critical" for a in alerts):
        adapter_status = "critical"
    elif (
        cpu["status"] != "ok"
        or memory["status"] != "ok"
        or any(not m.get("healthy", False) for m in mounts_list)
        or len(alerts) > 0
    ):
        adapter_status = "degraded"
    else:
        adapter_status = "online"

    return {
        "status": adapter_status,
        "adapter_status": adapter_status,
        "adapter_enabled": True,
        "collected_at": now_iso,
        "collection_interval_seconds": settings.nas_collection_interval_seconds,
        "history_retention_limit": settings.nas_history_retention_limit,
        "reason": host_reason,
        "telemetry_boundary": boundary,
        "cpu": cpu,
        "memory": memory,
        "mounts": _mounts_list_to_dict(mounts_list),
        "mounts_list": mounts_list,
        "containers": containers,
        "alerts": alerts,
        "thresholds": thresholds,
        "storage_safety": storage_safety,
    }


def sync_alert_lifecycle(
    conn: sqlite3.Connection,
    evaluated_alerts: list[dict[str, Any]],
    *,
    now_iso: str,
    can_resolve_missing: bool = True,
) -> list[dict[str, Any]]:
    """Synchronize active/resolved alert lifecycle in SQLite (`nas_alerts` — P02-F04).

    Rules:
    - Each active condition is keyed by `alert_key` (`{component}:{code}`).
    - If an active row with the same `alert_key` already exists:
      updates `last_seen_at`, `severity`, `message`, `metric_value`, `threshold_value`,
      `details_json`, and increments `occurrences` (deduplication).
    - If no active row exists for `alert_key`:
      inserts a new row with `status='active'`, `first_seen_at=now_iso`, `last_seen_at=now_iso`,
      `resolved_at=None`, `occurrences=1`.
    - If `can_resolve_missing` is True, any previously `'active'` row in `nas_alerts` whose
      `alert_key` is NOT in `evaluated_alerts` transitions to `status='resolved'` with
      `resolved_at=now_iso`.
    """
    existing_rows = conn.execute(
        "SELECT * FROM nas_alerts WHERE status = 'active' ORDER BY id ASC"
    ).fetchall()
    active_by_key: dict[str, sqlite3.Row] = {str(r["alert_key"]): r for r in existing_rows}
    seen_keys: set[str] = set()

    for alert in evaluated_alerts:
        key = str(alert["alert_key"])
        seen_keys.add(key)
        details_str = json.dumps(alert.get("details", {}), ensure_ascii=False)
        existing = active_by_key.get(key)
        if existing is not None:
            conn.execute(
                """
                UPDATE nas_alerts
                SET severity = ?,
                    message = ?,
                    metric_value = ?,
                    threshold_value = ?,
                    details_json = ?,
                    last_seen_at = ?,
                    occurrences = occurrences + 1
                WHERE id = ?
                """,
                (
                    str(alert["severity"]),
                    str(alert["message"]),
                    alert.get("metric_value"),
                    alert.get("threshold_value"),
                    details_str,
                    now_iso,
                    int(existing["id"]),
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO nas_alerts (
                    alert_key, code, severity, category, component, target,
                    message, metric_value, threshold_value, details_json,
                    status, first_seen_at, last_seen_at, resolved_at, occurrences
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, NULL, 1)
                """,
                (
                    key,
                    str(alert["code"]),
                    str(alert["severity"]),
                    str(alert.get("category", "nas")),
                    str(alert["component"]),
                    str(alert.get("target", alert["component"])),
                    str(alert["message"]),
                    alert.get("metric_value"),
                    alert.get("threshold_value"),
                    details_str,
                    now_iso,
                    now_iso,
                ),
            )

    if can_resolve_missing:
        for key, row in active_by_key.items():
            if key not in seen_keys:
                conn.execute(
                    """
                    UPDATE nas_alerts
                    SET status = 'resolved',
                        resolved_at = ?
                    WHERE id = ?
                    """,
                    (now_iso, int(row["id"])),
                )

    return query_nas_alerts(conn, include_resolved=False, limit=100)


def query_nas_alerts(
    conn: sqlite3.Connection,
    *,
    include_resolved: bool = False,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Query NAS alerts from SQLite with active/resolved filtering."""
    if include_resolved:
        rows = conn.execute(
            """
            SELECT * FROM nas_alerts
            ORDER BY CASE WHEN status = 'active' THEN 0 ELSE 1 END, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT * FROM nas_alerts
            WHERE status = 'active'
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        {
            "id": int(r["id"]),
            "alert_key": str(r["alert_key"]),
            "code": str(r["code"]),
            "severity": str(r["severity"]),
            "category": str(r["category"]),
            "component": str(r["component"]),
            "target": str(r["target"]),
            "message": str(r["message"]),
            "metric_value": r["metric_value"],
            "threshold_value": r["threshold_value"],
            "details": json.loads(str(r["details_json"])),
            "status": str(r["status"]),
            "first_seen_at": str(r["first_seen_at"]),
            "last_seen_at": str(r["last_seen_at"]),
            "resolved_at": r["resolved_at"],
            "occurrences": int(r["occurrences"]),
            "created_at": str(r["first_seen_at"]),
        }
        for r in rows
    ]


def persist_nas_snapshot(
    conn: sqlite3.Connection,
    snapshot: dict[str, Any],
    *,
    retention_limit: int = 120,
    min_persist_interval_seconds: int = 0,
    db_key: str = "default",
) -> int:
    """Persist a NAS telemetry snapshot, synchronize alert lifecycle, and prune old rows.

    Includes write-throttling (`min_persist_interval_seconds`) so background or repeated triggers
    do not cause excessive SQLite/SSD wear if invoked faster than the minimum interval when status
    has not changed.
    """
    now_epoch = time.monotonic()
    last_epoch = _LAST_PERSIST_EPOCH.get(db_key)
    now_iso = str(snapshot["collected_at"])
    adapter_status = str(snapshot["adapter_status"])

    # Always synchronize alert lifecycle if telemetry was verified or stale
    can_resolve = adapter_status in {"online", "degraded", "critical"}
    active_alerts = sync_alert_lifecycle(
        conn,
        snapshot.get("alerts", []),
        now_iso=now_iso,
        can_resolve_missing=can_resolve,
    )
    snapshot["alerts"] = active_alerts

    if (
        min_persist_interval_seconds > 0
        and last_epoch is not None
        and (now_epoch - last_epoch) < min_persist_interval_seconds
    ):
        latest_row = conn.execute(
            "SELECT id, adapter_status FROM nas_metric_snapshots ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if latest_row is not None and str(latest_row["adapter_status"]) == adapter_status:
            return int(latest_row["id"])

    _LAST_PERSIST_EPOCH[db_key] = now_epoch
    cpu = snapshot["cpu"]
    mem = snapshot["memory"]
    mounts_for_db = snapshot.get("mounts_list") or list(snapshot.get("mounts", {}).values())

    cursor = conn.execute(
        """
        INSERT INTO nas_metric_snapshots (
            collected_at, adapter_status,
            cpu_usage_percent, load_1m, load_5m, load_15m, cpu_cores, cpu_pressure_json,
            ram_total_bytes, ram_available_bytes, ram_used_bytes, ram_usage_percent,
            swap_total_bytes, swap_free_bytes, swap_used_bytes, swap_usage_percent,
            memory_pressure_json, mounts_json, containers_json, alerts_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            now_iso,
            adapter_status,
            cpu.get("usage_percent"),
            cpu.get("load_1m"),
            cpu.get("load_5m"),
            cpu.get("load_15m"),
            cpu.get("logical_cores"),
            json.dumps(cpu.get("pressure", {}), ensure_ascii=False),
            mem.get("total_bytes"),
            mem.get("available_bytes"),
            mem.get("used_bytes"),
            mem.get("usage_percent"),
            mem.get("swap_total_bytes"),
            mem.get("swap_free_bytes"),
            mem.get("swap_used_bytes"),
            mem.get("swap_usage_percent"),
            json.dumps(mem.get("pressure", {}), ensure_ascii=False),
            json.dumps(mounts_for_db, ensure_ascii=False),
            json.dumps(snapshot.get("containers", {}), ensure_ascii=False),
            json.dumps(active_alerts, ensure_ascii=False),
        ),
    )
    snapshot_id = int(cursor.lastrowid or 0)

    # Prune old snapshots and old resolved alerts to keep SSD I/O and SQLite footprint minimal
    conn.execute(
        """
        DELETE FROM nas_metric_snapshots
        WHERE id NOT IN (
            SELECT id FROM nas_metric_snapshots ORDER BY id DESC LIMIT ?
        )
        """,
        (retention_limit,),
    )
    conn.execute(
        """
        DELETE FROM nas_alerts
        WHERE status = 'resolved'
          AND id NOT IN (
              SELECT id FROM nas_alerts WHERE status = 'resolved' ORDER BY id DESC LIMIT ?
          )
        """,
        (retention_limit * 2,),
    )

    return snapshot_id
