"""Read-only NAS Guardian telemetry collector, Mount Guardian, and Container Health adapter.

Security & Storage Safety Invariants (Phase 02):
- Strictly read-only: reads /proc files, calls os.stat(..., follow_symlinks=False) and os.statvfs().
- Zero writes to /mnt/disk1, /mnt/disk2, or any monitored mount point.
- Zero directory listing (os.listdir / os.scandir) on media/HDD mounts.
- Zero /var/run/docker.sock access; container health uses an optional TOCTOU-safe read-only
  JSON snapshot file or reports 'unavailable'.
- Never fabricates live telemetry: disabled or unreadable sources return 'unavailable' and None.
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


def _default_lstat(path: str) -> os.stat_result:
    return os.stat(path, follow_symlinks=False)


def _read_proc_text(proc_root: Path, rel_name: str) -> str:
    """Safely read a virtual file under proc_root."""
    target = proc_root / rel_name
    if target.is_symlink():
        raise PermissionError(f"Symlink prohibited for proc file: {target}")
    return target.read_text(encoding="utf-8")


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
        pressure = {"status": "unavailable", "reason": str(exc)}

    return {
        "status": cpu_status,
        "reason": error_reason,
        "usage_percent": usage_percent,
        "logical_cores": logical_cores,
        "load_1m": load_1m,
        "load_5m": load_5m,
        "load_15m": load_15m,
        "pressure": pressure,
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
        pressure = {"status": "unavailable", "reason": str(exc)}

    return {
        "status": mem_status,
        "reason": reason,
        **mem,
        "pressure": pressure,
    }


def inspect_mount_point(
    mount_path: str,
    proc_mounts: dict[str, MountEntry],
    *,
    root_mount_path: str = "/",
    require_distinct_device: bool = True,
    stat_fn: StatFunc = _default_lstat,
    statvfs_fn: StatVfsFunc = os.statvfs,
) -> dict[str, Any]:
    """Inspect a single mount point in read-only mode and detect unmounted root-fs fallback.

    Detection rules:
    1. If lstat(mount_path) fails with FileNotFoundError -> status='missing'.
    2. If lstat(mount_path) fails with PermissionError -> status='unavailable'.
    3. If mount_path is a symlink or not a directory -> status='invalid_mount'.
    4. If require_distinct_device is True (e.g., /mnt/disk1, /mnt/disk2):
       - Must appear in /proc/mounts AND
       - Must have st_dev != lstat(root_mount_path).st_dev.
       If the directory exists on disk but fails either check, the HDD is unmounted and
       the directory is sitting on the root filesystem -> status='unmounted_fallback'.
    5. Otherwise, read filesystem capacity via os.statvfs(mount_path) -> status='mounted'.
    """
    base_result: dict[str, Any] = {
        "mount_point": mount_path,
        "require_distinct_device": require_distinct_device,
        "status": "unavailable",
        "healthy": False,
        "device": None,
        "fstype": None,
        "read_only": None,
        "total_bytes": None,
        "used_bytes": None,
        "available_bytes": None,
        "usage_percent": None,
        "reason": None,
    }

    try:
        target_stat = stat_fn(mount_path)
    except FileNotFoundError:
        base_result["status"] = "missing"
        base_result["reason"] = f"Mount directory does not exist: {mount_path}"
        return base_result
    except PermissionError as exc:
        base_result["status"] = "unavailable"
        base_result["reason"] = f"Permission denied inspecting mount: {exc}"
        return base_result
    except OSError as exc:
        base_result["status"] = "unavailable"
        base_result["reason"] = f"OS error inspecting mount: {exc}"
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
            base_result["reason"] = (
                f"Mount directory {mount_path} exists on the root filesystem, "
                "but the dedicated storage device is not mounted."
            )
            return base_result

    try:
        vfs = statvfs_fn(mount_path)
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
            "device": mount_entry.device if mount_entry else "unknown",
            "fstype": mount_entry.fstype if mount_entry else "unknown",
            "read_only": ("ro" in options) if options else False,
            "total_bytes": total_bytes,
            "used_bytes": used_bytes,
            "available_bytes": available_bytes,
            "usage_percent": usage_percent,
            "reason": None,
        }
    )
    return base_result


def inspect_all_mounts(
    settings: Settings,
    *,
    stat_fn: StatFunc = _default_lstat,
    statvfs_fn: StatVfsFunc = os.statvfs,
) -> list[dict[str, Any]]:
    """Inspect root filesystem and all configured NAS HDD mounts."""
    try:
        mounts_text = _read_proc_text(settings.nas_proc_root, "mounts")
        proc_mounts = parse_proc_mounts(mounts_text)
    except (OSError, ValueError) as exc:
        all_paths = [str(settings.nas_root_mount_path), *settings.nas_required_mounts]
        return [
            {
                "mount_point": p,
                "require_distinct_device": p != str(settings.nas_root_mount_path),
                "status": "unavailable",
                "healthy": False,
                "device": None,
                "fstype": None,
                "read_only": None,
                "total_bytes": None,
                "used_bytes": None,
                "available_bytes": None,
                "usage_percent": None,
                "reason": f"Cannot read {settings.nas_proc_root}/mounts: {exc}",
            }
            for p in all_paths
        ]

    root_str = str(settings.nas_root_mount_path)
    results: list[dict[str, Any]] = [
        inspect_mount_point(
            root_str,
            proc_mounts,
            root_mount_path=root_str,
            require_distinct_device=False,
            stat_fn=stat_fn,
            statvfs_fn=statvfs_fn,
        )
    ]

    for req_mount in settings.nas_required_mounts:
        if req_mount == root_str:
            continue
        results.append(
            inspect_mount_point(
                req_mount,
                proc_mounts,
                root_mount_path=root_str,
                require_distinct_device=True,
                stat_fn=stat_fn,
                statvfs_fn=statvfs_fn,
            )
        )
    return results


def inspect_container_health(settings: Settings) -> dict[str, Any]:
    """Read optional least-privilege container health snapshot without touching docker.sock."""
    rel_path = settings.nas_container_snapshot_rel_path.strip()
    if not rel_path:
        return {
            "status": "unavailable",
            "source": "none",
            "reason": (
                "No read-only container snapshot configured "
                "(mounting /var/run/docker.sock is prohibited by B+ security policy)."
            ),
            "services": [
                {
                    "name": svc,
                    "state": "unavailable",
                    "healthy": None,
                    "memory_used_bytes": None,
                    "memory_limit_bytes": None,
                    "memory_percent": None,
                    "cpu_percent": None,
                    "restart_count": None,
                }
                for svc in settings.nas_expected_services
            ],
        }

    try:
        safe_file = read_allowlisted_text_file(settings.reports_dir, rel_path)
        payload = json.loads(safe_file.content)
        if not isinstance(payload, dict) or not isinstance(payload.get("containers"), list):
            raise ValueError("Container snapshot JSON must contain a 'containers' list.")
    except (FileNotFoundError, PathSecurityError, ValueError, json.JSONDecodeError) as exc:
        return {
            "status": "unavailable",
            "source": rel_path,
            "reason": f"Container snapshot unavailable or invalid: {exc}",
            "services": [
                {
                    "name": svc,
                    "state": "unavailable",
                    "healthy": None,
                    "memory_used_bytes": None,
                    "memory_limit_bytes": None,
                    "memory_percent": None,
                    "cpu_percent": None,
                    "restart_count": None,
                }
                for svc in settings.nas_expected_services
            ],
        }

    by_name: dict[str, dict[str, Any]] = {}
    for item in payload["containers"]:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            by_name[item["name"].strip().lower()] = item

    services_out: list[dict[str, Any]] = []
    for svc in settings.nas_expected_services:
        raw = by_name.get(svc.lower())
        if raw is None:
            services_out.append(
                {
                    "name": svc,
                    "state": "missing",
                    "healthy": False,
                    "memory_used_bytes": None,
                    "memory_limit_bytes": None,
                    "memory_percent": None,
                    "cpu_percent": None,
                    "restart_count": None,
                }
            )
            continue

        state_str = str(raw.get("state", "unknown")).lower()
        mem_used = raw.get("memory_used_bytes")
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

        services_out.append(
            {
                "name": svc,
                "state": state_str,
                "healthy": state_str == "running",
                "memory_used_bytes": mem_used if isinstance(mem_used, int) else None,
                "memory_limit_bytes": mem_limit if isinstance(mem_limit, int) else None,
                "memory_percent": mem_pct,
                "cpu_percent": cpu_pct,
                "restart_count": restart_cnt,
            }
        )

    return {
        "status": "ok",
        "source": rel_path,
        "reason": None,
        "services": services_out,
    }


def evaluate_nas_alerts(
    settings: Settings,
    cpu: dict[str, Any],
    memory: dict[str, Any],
    mounts: list[dict[str, Any]],
    containers: dict[str, Any],
) -> list[dict[str, Any]]:
    """Evaluate read-only alert thresholds against collected NAS telemetry."""
    alerts: list[dict[str, Any]] = []
    now_iso = datetime.now(UTC).isoformat()

    # 1. CPU threshold checks
    cpu_pct = cpu.get("usage_percent")
    if isinstance(cpu_pct, (int, float)):
        if cpu_pct >= settings.nas_cpu_critical_percent:
            alerts.append(
                {
                    "code": "cpu.usage_critical",
                    "severity": "critical",
                    "component": "cpu",
                    "message": (
                        f"CPU usage is critical ({cpu_pct}% >= "
                        f"{settings.nas_cpu_critical_percent}%)."
                    ),
                    "details": {"usage_percent": cpu_pct},
                    "created_at": now_iso,
                }
            )
        elif cpu_pct >= settings.nas_cpu_warn_percent:
            alerts.append(
                {
                    "code": "cpu.usage_warning",
                    "severity": "warning",
                    "component": "cpu",
                    "message": (
                        f"CPU usage is elevated ({cpu_pct}% >= "
                        f"{settings.nas_cpu_warn_percent}%)."
                    ),
                    "details": {"usage_percent": cpu_pct},
                    "created_at": now_iso,
                }
            )

    # 2. Memory threshold checks
    ram_pct = memory.get("usage_percent")
    if isinstance(ram_pct, (int, float)):
        if ram_pct >= settings.nas_ram_critical_percent:
            alerts.append(
                {
                    "code": "ram.usage_critical",
                    "severity": "critical",
                    "component": "memory",
                    "message": (
                        f"Memory usage is critical ({ram_pct}% >= "
                        f"{settings.nas_ram_critical_percent}%)."
                    ),
                    "details": {"usage_percent": ram_pct},
                    "created_at": now_iso,
                }
            )
        elif ram_pct >= settings.nas_ram_warn_percent:
            alerts.append(
                {
                    "code": "ram.usage_warning",
                    "severity": "warning",
                    "component": "memory",
                    "message": (
                        f"Memory usage is elevated ({ram_pct}% >= "
                        f"{settings.nas_ram_warn_percent}%)."
                    ),
                    "details": {"usage_percent": ram_pct},
                    "created_at": now_iso,
                }
            )

    # 3. Mount Guardian & Disk Capacity checks
    for m in mounts:
        mp = str(m.get("mount_point", ""))
        st = str(m.get("status", "unavailable"))
        if st in {"missing", "unmounted_fallback", "invalid_symlink", "invalid_mount"}:
            alerts.append(
                {
                    "code": f"mount.{st}",
                    "severity": "critical",
                    "component": f"mount:{mp}",
                    "message": m.get("reason") or f"Mount point {mp} is in state '{st}'.",
                    "details": {"mount_point": mp, "status": st},
                    "created_at": now_iso,
                }
            )
        elif st == "mounted":
            disk_pct = m.get("usage_percent")
            if isinstance(disk_pct, (int, float)):
                if disk_pct >= settings.nas_disk_critical_percent:
                    alerts.append(
                        {
                            "code": "disk.usage_critical",
                            "severity": "critical",
                            "component": f"mount:{mp}",
                            "message": (
                                f"Filesystem {mp} usage is critical ({disk_pct}% >= "
                                f"{settings.nas_disk_critical_percent}%)."
                            ),
                            "details": {"mount_point": mp, "usage_percent": disk_pct},
                            "created_at": now_iso,
                        }
                    )
                elif disk_pct >= settings.nas_disk_warn_percent:
                    alerts.append(
                        {
                            "code": "disk.usage_warning",
                            "severity": "warning",
                            "component": f"mount:{mp}",
                            "message": (
                                f"Filesystem {mp} usage is high ({disk_pct}% >= "
                                f"{settings.nas_disk_warn_percent}%)."
                            ),
                            "details": {"mount_point": mp, "usage_percent": disk_pct},
                            "created_at": now_iso,
                        }
                    )

    # 4. Container Health checks (only when container snapshot is active)
    if containers.get("status") == "ok":
        for svc in containers.get("services", []):
            name = str(svc.get("name", "unknown"))
            state_str = str(svc.get("state", "unknown"))
            if state_str not in {"running", "unavailable"}:
                alerts.append(
                    {
                        "code": "container.not_running",
                        "severity": "critical",
                        "component": f"container:{name}",
                        "message": f"Configured service '{name}' is in state '{state_str}'.",
                        "details": {"service": name, "state": state_str},
                        "created_at": now_iso,
                    }
                )
            mem_pct = svc.get("memory_percent")
            if isinstance(mem_pct, (int, float)):
                if mem_pct >= settings.nas_container_mem_critical_percent:
                    alerts.append(
                        {
                            "code": "container.memory_critical",
                            "severity": "critical",
                            "component": f"container:{name}",
                            "message": (
                                f"Container '{name}' memory usage is critical "
                                f"({mem_pct}% of limit)."
                            ),
                            "details": {"service": name, "memory_percent": mem_pct},
                            "created_at": now_iso,
                        }
                    )
                elif mem_pct >= settings.nas_container_mem_warn_percent:
                    alerts.append(
                        {
                            "code": "container.memory_warning",
                            "severity": "warning",
                            "component": f"container:{name}",
                            "message": (
                                f"Container '{name}' memory usage is elevated "
                                f"({mem_pct}% of limit)."
                            ),
                            "details": {"service": name, "memory_percent": mem_pct},
                            "created_at": now_iso,
                        }
                    )

    return alerts


def collect_nas_telemetry(
    settings: Settings,
    *,
    stat_fn: StatFunc = _default_lstat,
    statvfs_fn: StatVfsFunc = os.statvfs,
    sample_delay_seconds: float = 0.02,
) -> dict[str, Any]:
    """Collect a complete read-only NAS Guardian snapshot or return honest unavailable state."""
    now_iso = datetime.now(UTC).isoformat()
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

    if not settings.nas_adapter_enabled:
        all_paths = [str(settings.nas_root_mount_path), *settings.nas_required_mounts]
        return {
            "collected_at": now_iso,
            "adapter_enabled": False,
            "adapter_status": "unavailable",
            "reason": (
                "NAS Guardian read-only adapter is disabled "
                "(set HOMEAGENTP_NAS_ADAPTER_ENABLED=true to enable)."
            ),
            "cpu": {
                "status": "unavailable",
                "reason": "Adapter disabled",
                "usage_percent": None,
                "logical_cores": None,
                "load_1m": None,
                "load_5m": None,
                "load_15m": None,
                "pressure": {"status": "unavailable"},
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
                "pressure": {"status": "unavailable"},
            },
            "mounts": [
                {
                    "mount_point": p,
                    "require_distinct_device": p != str(settings.nas_root_mount_path),
                    "status": "unavailable",
                    "healthy": False,
                    "device": None,
                    "fstype": None,
                    "read_only": None,
                    "total_bytes": None,
                    "used_bytes": None,
                    "available_bytes": None,
                    "usage_percent": None,
                    "reason": "Adapter disabled",
                }
                for p in all_paths
            ],
            "containers": inspect_container_health(settings),
            "alerts": [],
            "thresholds": thresholds,
        }

    cpu = collect_cpu_telemetry(
        settings.nas_proc_root, sample_delay_seconds=sample_delay_seconds
    )
    memory = collect_memory_telemetry(settings.nas_proc_root)
    mounts = inspect_all_mounts(settings, stat_fn=stat_fn, statvfs_fn=statvfs_fn)
    containers = inspect_container_health(settings)
    alerts = evaluate_nas_alerts(settings, cpu, memory, mounts, containers)

    if cpu["status"] == "unavailable" and memory["status"] == "unavailable":
        adapter_status = "unavailable"
    elif (
        cpu["status"] != "ok"
        or memory["status"] != "ok"
        or any(not m.get("healthy", False) for m in mounts)
        or any(a["severity"] == "critical" for a in alerts)
    ):
        adapter_status = "degraded"
    else:
        adapter_status = "online"

    return {
        "collected_at": now_iso,
        "adapter_enabled": True,
        "adapter_status": adapter_status,
        "reason": None,
        "cpu": cpu,
        "memory": memory,
        "mounts": mounts,
        "containers": containers,
        "alerts": alerts,
        "thresholds": thresholds,
    }


def persist_nas_snapshot(
    conn: sqlite3.Connection,
    snapshot: dict[str, Any],
    *,
    retention_limit: int = 120,
) -> int:
    """Persist a NAS telemetry snapshot and any generated alerts, then prune old rows."""
    cpu = snapshot["cpu"]
    mem = snapshot["memory"]
    alerts = snapshot["alerts"]

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
            str(snapshot["collected_at"]),
            str(snapshot["adapter_status"]),
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
            json.dumps(snapshot.get("mounts", []), ensure_ascii=False),
            json.dumps(snapshot.get("containers", {}), ensure_ascii=False),
            json.dumps(alerts, ensure_ascii=False),
        ),
    )
    snapshot_id = int(cursor.lastrowid or 0)

    for alert in alerts:
        conn.execute(
            """
            INSERT INTO nas_alerts (code, severity, component, message, details_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(alert["code"]),
                str(alert["severity"]),
                str(alert["component"]),
                str(alert["message"]),
                json.dumps(alert.get("details", {}), ensure_ascii=False),
                str(alert["created_at"]),
            ),
        )

    # Prune old snapshots and alerts to keep SSD I/O and SQLite footprint minimal
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
        WHERE id NOT IN (
            SELECT id FROM nas_alerts ORDER BY id DESC LIMIT ?
        )
        """,
        (retention_limit * 2,),
    )
    return snapshot_id
