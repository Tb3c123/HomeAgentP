"""Pure parsers for Linux /proc telemetry files (CPU, LoadAvg, PSI Pressure, MemInfo, Mounts)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CpuTicks:
    user: int
    nice: int
    system: int
    idle: int
    iowait: int
    irq: int
    softirq: int
    steal: int
    logical_cores: int

    @property
    def idle_all(self) -> int:
        return self.idle + self.iowait

    @property
    def total(self) -> int:
        return (
            self.user
            + self.nice
            + self.system
            + self.idle
            + self.iowait
            + self.irq
            + self.softirq
            + self.steal
        )


@dataclass(frozen=True)
class MountEntry:
    device: str
    mount_point: str
    fstype: str
    options: list[str]


def parse_proc_stat_cpu(text: str) -> CpuTicks:
    """Parse aggregate CPU ticks and logical core count from /proc/stat content."""
    aggregate_parts: list[int] | None = None
    core_count = 0

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        fields = line.split()
        if fields[0] == "cpu":
            if len(fields) < 5:
                raise ValueError("Malformed 'cpu' line in /proc/stat: fewer than 4 tick columns.")
            try:
                values = [int(v) for v in fields[1:9]]
            except ValueError as exc:
                raise ValueError("Non-integer CPU tick value in /proc/stat.") from exc
            if any(v < 0 for v in values):
                raise ValueError("Negative CPU tick value in /proc/stat.")
            while len(values) < 8:
                values.append(0)
            aggregate_parts = values
        elif fields[0].startswith("cpu") and fields[0][3:].isdigit():
            core_count += 1

    if aggregate_parts is None:
        raise ValueError("Missing aggregate 'cpu' line in /proc/stat.")

    return CpuTicks(
        user=aggregate_parts[0],
        nice=aggregate_parts[1],
        system=aggregate_parts[2],
        idle=aggregate_parts[3],
        iowait=aggregate_parts[4],
        irq=aggregate_parts[5],
        softirq=aggregate_parts[6],
        steal=aggregate_parts[7],
        logical_cores=max(core_count, 1),
    )


def compute_cpu_usage_percent(prev: CpuTicks, curr: CpuTicks) -> float | None:
    """Compute CPU busy percentage between two CpuTicks snapshots."""
    total_delta = curr.total - prev.total
    idle_delta = curr.idle_all - prev.idle_all
    if total_delta <= 0 or idle_delta < 0 or idle_delta > total_delta:
        return None
    busy_ratio = 1.0 - (idle_delta / total_delta)
    return round(max(0.0, min(100.0, busy_ratio * 100.0)), 2)


def parse_proc_loadavg(text: str) -> tuple[float, float, float]:
    """Parse 1m, 5m, and 15m load averages from /proc/loadavg."""
    fields = text.strip().split()
    if len(fields) < 3:
        raise ValueError("Malformed /proc/loadavg: expected at least 3 fields.")
    try:
        load_1m = round(float(fields[0]), 2)
        load_5m = round(float(fields[1]), 2)
        load_15m = round(float(fields[2]), 2)
    except ValueError as exc:
        raise ValueError("Invalid float values in /proc/loadavg.") from exc
    if load_1m < 0 or load_5m < 0 or load_15m < 0:
        raise ValueError("Negative load average in /proc/loadavg.")
    return load_1m, load_5m, load_15m


def parse_proc_psi_pressure(text: str) -> dict[str, Any]:
    """Parse Linux PSI (/proc/pressure/cpu or /proc/pressure/memory) into structured metrics."""
    result: dict[str, Any] = {"status": "ok"}
    found_any = False

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split()
        kind = parts[0]
        if kind not in {"some", "full"} or len(parts) < 5:
            raise ValueError(f"Malformed PSI line: {line}")

        metrics: dict[str, float | int] = {}
        for kv in parts[1:]:
            if "=" not in kv:
                raise ValueError(f"Malformed PSI key=value token: {kv}")
            key, val_str = kv.split("=", 1)
            if key in {"avg10", "avg60", "avg300"}:
                metrics[key] = round(float(val_str), 2)
            elif key == "total":
                metrics[key] = int(val_str)

        if not {"avg10", "avg60", "avg300"}.issubset(metrics.keys()):
            raise ValueError(f"Missing avg10/avg60/avg300 in PSI line: {line}")

        result[kind] = metrics
        found_any = True

    if not found_any:
        raise ValueError("Empty PSI pressure file.")

    return result


def parse_proc_meminfo(text: str) -> dict[str, Any]:
    """Parse /proc/meminfo and return RAM and Swap metrics in bytes and percentages."""
    kv_kb: dict[str, int] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        key, rest = line.split(":", 1)
        tokens = rest.strip().split()
        if not tokens:
            continue
        try:
            kv_kb[key.strip()] = int(tokens[0])
        except ValueError as exc:
            raise ValueError(f"Invalid integer in /proc/meminfo for {key}: {rest}") from exc

    mem_total_kb = kv_kb.get("MemTotal", 0)
    if mem_total_kb <= 0:
        raise ValueError("Missing or non-positive MemTotal in /proc/meminfo.")

    if "MemAvailable" in kv_kb:
        mem_avail_kb = kv_kb["MemAvailable"]
    elif "MemFree" in kv_kb:
        mem_avail_kb = (
            kv_kb["MemFree"] + kv_kb.get("Buffers", 0) + kv_kb.get("Cached", 0)
        )
    else:
        raise ValueError("Missing MemAvailable and MemFree in /proc/meminfo.")

    if mem_avail_kb < 0:
        raise ValueError("Negative memory values in /proc/meminfo.")

    total_bytes = mem_total_kb * 1024
    available_bytes = min(total_bytes, mem_avail_kb * 1024)
    used_bytes = max(0, total_bytes - available_bytes)
    usage_percent = round((used_bytes / total_bytes) * 100.0, 2)

    swap_total_kb = max(0, kv_kb.get("SwapTotal", 0))
    swap_free_kb = max(0, min(swap_total_kb, kv_kb.get("SwapFree", 0)))
    swap_total_bytes = swap_total_kb * 1024
    swap_free_bytes = swap_free_kb * 1024
    swap_used_bytes = max(0, swap_total_bytes - swap_free_bytes)
    swap_usage_percent = (
        round((swap_used_bytes / swap_total_bytes) * 100.0, 2)
        if swap_total_bytes > 0
        else 0.0
    )

    return {
        "total_bytes": total_bytes,
        "available_bytes": available_bytes,
        "used_bytes": used_bytes,
        "usage_percent": usage_percent,
        "swap_total_bytes": swap_total_bytes,
        "swap_free_bytes": swap_free_bytes,
        "swap_used_bytes": swap_used_bytes,
        "swap_usage_percent": swap_usage_percent,
    }


def _unescape_mount_path(raw_path: str) -> str:
    """Decode /proc/mounts octal escapes such as \\040 (space) and \\011 (tab)."""
    return (
        raw_path.replace("\\040", " ")
        .replace("\\011", "\t")
        .replace("\\012", "\n")
        .replace("\\134", "\\")
    )


def parse_proc_mounts(text: str) -> dict[str, MountEntry]:
    """Parse /proc/mounts and return a mapping of mount_point -> MountEntry."""
    mounts: dict[str, MountEntry] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) < 4:
            continue
        device = fields[0]
        mount_point = _unescape_mount_path(fields[1])
        fstype = fields[2]
        options = [opt.strip() for opt in fields[3].split(",") if opt.strip()]
        mounts[mount_point] = MountEntry(
            device=device,
            mount_point=mount_point,
            fstype=fstype,
            options=options,
        )
    return mounts
