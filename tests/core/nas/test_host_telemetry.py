"""Host /proc telemetry parser tests for NAS Guardian."""

from __future__ import annotations

import pytest

from homeagentp_core.modules.nas.parsers import (
    compute_cpu_usage_percent,
    parse_proc_loadavg,
    parse_proc_meminfo,
    parse_proc_psi_pressure,
    parse_proc_stat_cpu,
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
