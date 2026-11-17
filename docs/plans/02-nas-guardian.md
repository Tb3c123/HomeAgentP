# Phase 02 — NAS Guardian (Read-Only Telemetry, Mount Integrity & Container Health)

Status: IN_PROGRESS (`feature/phase-02-nas-guardian`) / LOCAL UNIT & INTEGRATION TESTS / CONTAINER RUNTIME `NOT_TESTED` / `NOT_DEPLOYED`.

## Goal
Implement **NAS Guardian** (`Phase 02`) within the two-container HomeAgentP B+ architecture (`homeagentp-core` + `homeagentp-web`) to provide read-only host resource telemetry, HDD mount integrity verification (`/mnt/disk1`, `/mnt/disk2`), least-privilege container health observation, alert evaluation, and bounded SQLite metric history.

## Scope
1. **CPU Telemetry (`apps/core/src/homeagentp_core/modules/nas/collector.py`)**:
   - Parse `/proc/stat` (two-sample delta or stateful previous-sample delta) for CPU usage percentage.
   - Parse `/proc/loadavg` for `1m`, `5m`, and `15m` load averages alongside logical CPU count.
   - Parse `/proc/pressure/cpu` (Linux PSI `some` `avg10`, `avg60`, `avg300`), reporting `unavailable` when PSI is unsupported or unreadable.
2. **RAM & Swap Telemetry**:
   - Parse `/proc/meminfo` for `MemTotal`, `MemAvailable`, `MemUsed`, `UsagePercent`, `SwapTotal`, `SwapFree`, `SwapUsed`, and `SwapUsagePercent`.
   - Parse `/proc/pressure/memory` (Linux PSI `some` and `full` `avg10`, `avg60`, `avg300`).
3. **SSD/HDD Capacity & Mount Guardian**:
   - Inspect `/proc/mounts` and `os.statvfs` / `os.stat` for configured mount points (`/`, `/mnt/disk1`, `/mnt/disk2`).
   - Detect missing mounts **including** the critical failure mode where `/mnt/disk1` or `/mnt/disk2` still exists as an empty directory on the root filesystem (`/`) after the underlying ext4 HDD has been unmounted (`unmounted_fallback`, detected via `/proc/mounts` membership and `st_dev` comparison against `/`).
   - Strictly read-only: zero writes to HDDs, zero directory traversal of media files, zero broad HDD volume mounts.
4. **Least-Privilege Container Health**:
   - Never mount `/var/run/docker.sock`, never run as root, never use `privileged: true` or `network_mode: host`, and never start/stop/restart/modify containers.
   - Support reading a schema-validated, read-only container status snapshot file (`HOMEAGENTP_CONTAINER_SNAPSHOT_PATH`) from an allowlisted directory (using TOCTOU-safe `openat` reader). When unconfigured or absent, explicitly report `status: "unavailable"`.
5. **Monitoring, Threshold Alerts & Bounded SQLite History (`002_nas_guardian.sql`)**:
   - Persist snapshots in `nas_metric_snapshots` (with automatic retention pruning to protect SSD wear and SQLite size on Intel N200) and alerts in `nas_alerts`.
   - Evaluate configurable warning/critical thresholds for CPU, RAM, Disk usage, Mount integrity (`unmounted_fallback` / `missing`), and Container health.
6. **Dashboard (`apps/web`)**:
   - NAS Guardian view displaying CPU, RAM/Swap, PSI pressure, Mount Guardian table, Container Health table, Alert Thresholds, Active Alerts, and Collection History, preserving honest `UNAVAILABLE` states whenever data sources are disabled or unreachable.

## Non-goals
- No `/var/run/docker.sock` access or container lifecycle mutations (`start`/`stop`/`restart`/`rm`).
- No SMART raw block device access (`CAP_SYS_RAWIO` / `/dev/sdX`) inside `homeagentp-core`.
- No writes to `/mnt/disk1` or `/mnt/disk2` and no media file indexing.
- No production NAS deployment.

## Acceptance Criteria
- [x] Unit tests for CPU, loadavg, PSI pressure, RAM/swap (`/proc/meminfo`), and storage capacity parsing.
- [x] Unit & integration tests for Mount Guardian detecting both non-existent mount paths (`missing`) and unmounted directories residing on the root filesystem (`unmounted_fallback`).
- [x] Tests for malformed `/proc` data, `PermissionError`, missing files, and disabled adapter states returning `unavailable` without fabricating live metrics.
- [x] Read-only boundary tests confirming zero writes to monitored mount targets and TOCTOU-safe reading of optional container snapshots.
- [x] SQLite persistence and retention pruning tests for `nas_metric_snapshots` and `nas_alerts`.
- [x] Ruff, Mypy (`--strict`), Pytest, TypeScript (`tsc --noEmit`), Vitest, Vite production build, and `npm audit` pass with real logs.

## Pre-Production Mandatory Checklist (Carry-Over & Operational Gates)
Before any production deployment to the Debian 12 / CasaOS NAS is requested in Phase 06, the following items **must** be completed and verified:
1. **Phase 01 & 02 Docker Compose Staging Verification**: Execute `docker compose --env-file .env -f deploy/docker-compose.dev.yml up --build` on an isolated staging host with a Docker daemon to verify container startup, healthchecks, Nginx proxy, CSRF, non-root filesystem permissions, and restart persistence.
2. **Stopped-Database Restore Drill**: Verify `restore_sqlite_database()` against a stopped `homeagentp-core` instance in staging and confirm clean startup and schema/data integrity.
3. **Existing Antigravity Terminal Container Security Audit & Hardening**: Audit and lock down the legacy root + RW Docker Socket + wide `ttyd` (port 7681) container currently running on the NAS before any production cutover.
