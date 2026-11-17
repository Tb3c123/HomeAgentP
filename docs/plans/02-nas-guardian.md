# Phase 02 — NAS Guardian (Read-Only Telemetry, Mount Integrity & Container Health)

Status: IMPLEMENTED & HARDENED (`feature/phase-02-nas-guardian`, `P02-F01`..`P02-F04` FIXED) / LOCAL UNIT & INTEGRATION TESTS PASS / CONTAINER RUNTIME `NOT_TESTED` (`P02-F05` BLOCKED IN SANDBOX) / `NOT_DEPLOYED`.

## Goal
Implement **NAS Guardian** (`Phase 02`) within the two-container HomeAgentP B+ architecture (`homeagentp-core` + `homeagentp-web`) to provide read-only host resource telemetry, HDD mount integrity verification (`/mnt/disk1`, `/mnt/disk2`), least-privilege container health observation, background periodic collection, stateful alert lifecycle management, and bounded SQLite metric history.

## Scope & Hardened Architecture (`P02-F01`–`P02-F05`)

1. **Host Telemetry Boundary (`P02-F01` — `apps/core/src/homeagentp_core/modules/nas/collector.py`)**:
   - **Strict Namespace Separation**: `homeagentp-core` **never** assumes its own `/proc`, `/`, or `/proc/mounts` inside a container reflects the Debian 12 NAS host.
   - **`host_snapshot` Mode (Recommended for Docker / CasaOS)**: A least-privilege host systemd timer writes an atomic JSON snapshot (`nas_host_snapshot.json`, schema `homeagentp.nas_host.v1`) into an allowlisted directory mounted `:ro` into `homeagentp-core` (`HOMEAGENTP_REPORTS_DIR`). `homeagentp-core` reads the file using the TOCTOU-safe descriptor reader (`read_allowlisted_text_file`, `O_NOFOLLOW`, `st_nlink == 1`), verifies `generated_at` and `ttl_seconds`, and marks expired data as `stale`.
   - **`direct_host_fs` Mode**: Requires explicit read-only host mounts (`/host/proc`, `/host/root`). `verify_direct_host_boundary()` rejects `/proc`, `/`, and any container `overlay`/`aufs`/`shm` root filesystem, returning `status="unavailable"` (`host_verified=False`) and **never** falsely reporting `/mnt/disk1` or `/mnt/disk2` as unmounted when the host boundary is unverified.

2. **Automatic Background Collection Scheduler (`P02-F02` — `apps/core/src/homeagentp_core/modules/nas/scheduler.py`)**:
   - `NasCollectionScheduler` runs inside the FastAPI `lifespan` independently of Dashboard browser requests (default interval `60s` when `HOMEAGENTP_NAS_SCHEDULER_ENABLED=true`).
   - **Non-Overlapping**: Guarded by an `asyncio.Lock` (`skipped_overlap_count` tracked if a cycle is already running).
   - **Timeout & Graceful Shutdown**: Wraps each collection in `asyncio.wait_for(..., timeout=nas_collection_timeout_seconds)` and cancels/awaits cleanly on application shutdown.
   - **SQLite Write-Throttling**: Skips background persistence when telemetry is `unavailable` and enforces `nas_min_persist_interval_seconds` when `adapter_status` is unchanged to protect the NAS NVMe/SSD from excessive writes.

3. **Container Snapshot Schema, Freshness & TTL (`P02-F03`)**:
   - Validates `schema_version == "homeagentp.containers.v1"`, `generated_at` (ISO-8601 UTC), `ttl_seconds`, and `containers` list.
   - Evaluates snapshot age against `min(ttl_seconds, HOMEAGENTP_NAS_SNAPSHOT_MAX_AGE_SECONDS)`.
   - Expired snapshots report `status="stale"`, `fresh=False`, mark service entries `stale`, and raise a `container.snapshot_stale` warning alert instead of presenting stale data as live `running` containers.
   - **No Docker Socket in Core**: `homeagentp-core` never mounts `/var/run/docker.sock`.

4. **Stateful Alert Lifecycle (`P02-F04` — `002_nas_guardian.sql`, `sync_alert_lifecycle()`)**:
   - Tracks `status` (`active` | `resolved`), `first_seen_at`, `last_seen_at`, `resolved_at`, and `occurrences`.
   - Deduplicates repeated active alerts with the same `alert_key` (`{component}:{code}`), updating `last_seen_at` and incrementing `occurrences`.
   - Automatically transitions cleared alerts from `active` to `resolved` (`resolved_at` timestamped) and creates a new `active` record if the fault re-occurs later.
   - Synchronized between backend (`GET /api/v1/nas/alerts?include_resolved=true|false`) and frontend (`Show resolved` toggle in the NAS Alerts card).

5. **CPU, RAM, PSI & Mount Guardian**:
   - CPU usage `%` (`/proc/stat` delta), load average (`1m`, `5m`, `15m`), and Linux PSI (`/proc/pressure/cpu`).
   - RAM total/available/used/`%`, Swap total/free/used/`%`, and Linux PSI (`/proc/pressure/memory`).
   - Mount Guardian verifies `/`, `/mnt/disk1`, and `/mnt/disk2`, detecting both missing directories (`missing`) and unmounted directories that fell back onto the root filesystem (`unmounted_fallback`).

## Non-goals
- No `/var/run/docker.sock` access or container lifecycle mutations (`start`/`stop`/`restart`/`rm`).
- No SMART raw block device access (`CAP_SYS_RAWIO` / `/dev/sdX`) inside `homeagentp-core`.
- No writes to `/mnt/disk1` or `/mnt/disk2` and no media file indexing.
- No production NAS deployment.

## Acceptance Criteria
- [x] **P02-F01**: Host vs container namespace boundary enforced; container `/proc`, `/`, and `overlay` root are rejected as `unavailable` without false HDD unmount alerts.
- [x] **P02-F02**: Background `NasCollectionScheduler` runs non-overlapping cycles, enforces timeouts, throttles SQLite writes, and shuts down gracefully.
- [x] **P02-F03**: Container & host snapshots validate `schema_version`, `generated_at`, and `ttl_seconds`, flagging expired snapshots as `stale`.
- [x] **P02-F04**: Alert lifecycle supports `active`/`resolved`, deduplication (`occurrences`), `first_seen_at`, `last_seen_at`, `resolved_at`, and `include_resolved` filtering across backend and frontend.
- [x] Unit & integration tests cover CPU/RAM/PSI parsing, Mount Guardian `missing` & `unmounted_fallback`, permission errors, symlinks, boundary rejection, snapshot staleness, scheduler concurrency/timeout, and alert lifecycle transitions.
- [x] Ruff, Mypy, Pytest (`28 passed`), TypeScript (`tsc --noEmit`), Vitest, Vite production build, and `npm audit` (`0 vulnerabilities`) pass with real logs.

## Pre-Production Mandatory Checklist (Carry-Over & Operational Gates)
Before any production deployment to the Debian 12 / CasaOS NAS is requested in Phase 06, the following items **must** be completed and verified:
1. **Phase 01 & 02 Docker Compose Staging Verification (`F05` / `P02-F05`)**: Execute `docker compose --env-file .env -f deploy/docker-compose.dev.yml up --build` on an isolated staging host with a Docker daemon to verify container startup, healthchecks, Nginx proxy, CSRF, host snapshot handoff, non-root filesystem permissions, and restart persistence.
2. **Stopped-Database Restore Drill**: Verify `restore_sqlite_database()` against a stopped `homeagentp-core` instance in staging and confirm clean startup and schema/data integrity.
3. **Existing Antigravity Terminal Container Security Audit & Hardening**: Audit and lock down the legacy root + RW Docker Socket + wide `ttyd` (port 7681) container currently running on the NAS before any production cutover.
