# Phase 01 — Operations Runbook, Security Notes, Backup & Rollback

> **Scope Notice:** This runbook applies to **local development and isolated staging** for Phase 01 Foundation. It does **not** grant permission to deploy onto the production Debian 12 / CasaOS NAS without separate explicit owner approval.

---

## 1. Local Development Startup (User-Space, Without Docker)

### 1.1. Prepare `.env` at Repository Root (Local Only — Never Commit)

From the repository root (`HomeAgentP/`):

```bash
cp config/examples/.env.example .env
```

Generate a fresh random secret key and set a strong local development password in `.env`:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Update `HOMEAGENTP_SECRET_KEY` and `HOMEAGENTP_ADMIN_PASSWORD` in `.env`.
- `homeagentp-core` refuses to start if placeholder secrets from `.env.example` are left unchanged.
- Relative paths in `.env` (`HOMEAGENTP_DB_PATH=./data/homeagentp.db`, `HOMEAGENTP_SCRIPTS_DIR=./config/examples/scripts`, `HOMEAGENTP_REPORTS_DIR=./config/examples/reports`) are relative to the repository root, so run `uvicorn` from the repository root as shown below (note: `Settings` also checks `(".env", "../../.env")` if invoked from `apps/core`).

### 1.2. Install & Start `homeagentp-core` (Port 8311)

From the repository root (`HomeAgentP/`):

```bash
uv venv apps/core/.venv
uv pip install --python apps/core/.venv/bin/python -e "apps/core[dev]"
apps/core/.venv/bin/uvicorn homeagentp_core.main:create_app --factory --host 127.0.0.1 --port 8311
```

### 1.3. Install & Start `homeagentp-web` (Port 8310)

In a second terminal:

```bash
cd apps/web
npm install
npm run dev
```

Open `http://127.0.0.1:8310` to sign in and inspect the Dashboard.

---

## 2. Local Containerized Staging (`deploy/docker-compose.dev.yml`)

> **Status in Isolated Dev VM:** `NOT_TESTED` (no Docker daemon available in the sandboxed development VM). Run these steps on a staging workstation with Docker Compose installed (not on the production NAS):

```bash
cp config/examples/.env.example .env
# Edit .env to set random HOMEAGENTP_SECRET_KEY and HOMEAGENTP_ADMIN_PASSWORD
docker compose --env-file .env -f deploy/docker-compose.dev.yml up --build -d
```

### Verify Health & Shutdown

```bash
curl -sf http://127.0.0.1:8310/api/v1/health
docker compose --env-file .env -f deploy/docker-compose.dev.yml down
```

---

## 3. Atomic SQLite Backup & Isolated Restore Verification (F03)

`homeagentp-core` runs SQLite in `WAL` mode and provides `backup_sqlite_database()` and `restore_sqlite_database()` in `apps/core/src/homeagentp_core/db/connection.py`.
- `backup_sqlite_database()` writes to a temporary `.tmp` file in the target directory, converts the backup journal mode to `DELETE` (single self-contained file), runs `PRAGMA integrity_check;` and `PRAGMA foreign_key_check;`, flushes to disk (`fsync`), and publishes atomically via `os.replace()`.
- If interrupted or if integrity checks fail, the temporary file is unlinked and any existing valid backup at the destination path remains untouched.

### Create an Atomic Verified Online Backup

```bash
apps/core/.venv/bin/python -c "
from pathlib import Path
from homeagentp_core.db.connection import backup_sqlite_database
out = backup_sqlite_database(Path('./data/homeagentp.db'), Path('./data/backups/homeagentp-backup.db'))
print('Verified atomic backup written to:', out)
"
```

### Verify & Restore into an Isolated Path

```bash
apps/core/.venv/bin/python -c "
from pathlib import Path
from homeagentp_core.db.connection import restore_sqlite_database, verify_sqlite_integrity
restored = restore_sqlite_database(
    Path('./data/backups/homeagentp-backup.db'),
    Path('./data/backups/homeagentp-restored-drill.db'),
)
verify_sqlite_integrity(restored)
print('Isolated restore verified:', restored)
"
```

---

## 4. Security & Threat Model Notes (Phase 01 Hardening)

1. **No Consumer Antigravity CLI Wrapping:** HomeAgentP does not call, proxy, or wrap `agy` or consumer OAuth tokens. Task handoff uses Git branches, PRs, and Markdown Task Briefs.
2. **Least Privilege & Container Hardening:**
   - `homeagentp-core` runs as UID/GID `10001:10001`.
   - `homeagentp-web` runs as UID/GID `101:101`.
   - Both containers drop all Linux capabilities (`cap_drop: [ALL]`), enforce `no-new-privileges:true`, use `read_only: true` root filesystems, and mount **no** `/var/run/docker.sock` or `/mnt/disk*`.
3. **TOCTOU-Resistant Read-Only Script & Report Viewer (`safe_reader.py` — F02):**
   - **Threat Model:** Classic user-space path checks (`Path.is_symlink()` + `Path.resolve()` followed by `open()`) are susceptible to Time-of-Check to Time-of-Use (TOCTOU) symlink swaps if an attacker can modify an intermediate directory or leaf entry between check and open, or plant hardlinks (`st_nlink > 1`) to sensitive files on the same filesystem.
   - **Mitigation:** `read_allowlisted_text_file()` opens the allowlisted root directory with `O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC` and steps through each single path component using `os.open(part, ..., dir_fd=current_dir_fd)`. The leaf file is opened relative to the final directory descriptor with `O_RDONLY | O_NOFOLLOW | O_CLOEXEC`. All post-open checks (`stat.S_ISREG`, `st_nlink == 1`, `st_size <= 256 KiB`, UTF-8 decoding, and SHA-256 verification) operate exclusively on the open `file_fd`.
   - **Residual Boundary:** In production/staging, allowlisted directories are mounted read-only (`:ro`) and owned by root/admin so unprivileged processes cannot mutate files while they are being read.
4. **Authentication, Audit Persistence & CSRF (F01):**
   - Passwords hashed with PBKDF2-HMAC-SHA256 (`600,000` iterations).
   - Session tokens are stored only as HMAC-SHA256 hashes in SQLite.
   - Failed login attempts (`auth.login_failed`) and expired session deletions are committed by exiting `db_session()` cleanly **before** raising `HTTPException(401)`.
   - All state-changing endpoints require a matching `X-CSRF-Token` header.
5. **Atomic SQL Migrations:**
   - Each migration file and its `INSERT INTO schema_migrations` record run inside an explicit `BEGIN IMMEDIATE ... COMMIT` block with automatic `ROLLBACK` on any statement error.

---

## 5. Rollback Procedure

1. **Code / Git Rollback (Development Repository):**
   - Close or revert the feature branch PR without merging to `main`, or revert the merge commit via `git revert <commit_sha>`.
2. **Local Staging Container Rollback:**
   - Stop containers: `docker compose --env-file .env -f deploy/docker-compose.dev.yml down`.
   - Restore the previous SQLite backup using `restore_sqlite_database(Path('./data/backups/homeagentp-backup.db'), Path('./data/homeagentp.db'))`.
   - Checkout the previous known-good Git tag/commit and rebuild.

---

## 6. Troubleshooting

| Symptom | Likely Cause | Safe Resolution |
| :--- | :--- | :--- |
| `ValidationError: HOMEAGENTP_SECRET_KEY uses a disallowed placeholder value` | `.env` still contains placeholder values from `.env.example`. | Generate a new random secret (`python3 -c "import secrets; print(secrets.token_urlsafe(32))"`) and update `.env`. |
| `FileNotFoundError: Allowlisted base directory does not exist` | `uvicorn` was started from a directory where relative `HOMEAGENTP_SCRIPTS_DIR` does not resolve. | Start `uvicorn` from the repository root (`HomeAgentP/`) or set absolute paths in `.env`. |
| `401 Unauthorized` on Dashboard or API calls | Session expired or cookie not sent over HTTP when `HOMEAGENTP_COOKIE_SECURE=true`. | For localhost HTTP dev, set `HOMEAGENTP_COOKIE_SECURE=false` in `.env` and sign in again. |
| `403 Forbidden: Missing or invalid CSRF token` | Write request (`POST`/`PATCH`) missing `X-CSRF-Token` header or using an outdated token. | Refresh `/api/v1/auth/me` or sign out and back in so the UI holds the active session's CSRF token. |
| `403 Forbidden: Symlinks are prohibited` / `Hardlinked files (st_nlink > 1) are prohibited` / `SHA-256 checksum mismatch` | Script file in `HOMEAGENTP_SCRIPTS_DIR` is a symlink, hardlink, or was edited without updating `manifest.json`. | Replace with a regular single-link file and update `manifest.json` SHA-256 after human review. |

---

## 7. Phase 02 — NAS Guardian Hardening (`P02-F01`–`P02-F05`) & Host Collector Guide

### 7.1. Host vs. Container Telemetry Boundary (`P02-F01`)

Inside a Docker/CasaOS container, `/proc`, `/`, and `/proc/mounts` belong to the **container's own namespace** (`overlay` rootfs), **not** the Debian 12 NAS host.
- If `homeagentp-core` blindly inspected `/proc/mounts` and `/` inside a container, `/mnt/disk1` and `/mnt/disk2` would be absent or appear on the container rootfs, triggering false-positive critical HDD unmount alerts.
- `homeagentp-core` enforces a strict boundary (`verify_direct_host_boundary()`):
  1. **`host_snapshot` Mode (Recommended for Debian 12 / CasaOS)**: A least-privilege host systemd timer writes an atomic JSON snapshot (`nas_host_snapshot.json`, schema `homeagentp.nas_host.v1`) into a host directory mounted read-only (`:ro`) into `homeagentp-core` (`HOMEAGENTP_REPORTS_DIR`). `homeagentp-core` never needs host filesystem mounts or elevated capabilities.
  2. **`direct_host_fs` Mode**: Requires explicit read-only host mounts (`HOMEAGENTP_NAS_PROC_ROOT=/host/proc`, `HOMEAGENTP_NAS_ROOT_MOUNT_PATH=/host/root`). If configured with container-local `/proc`, `/`, or if the mounts table reports a container `overlay`/`aufs`/`shm` root filesystem, `homeagentp-core` rejects the boundary, returns `status: "unavailable"` (`host_verified: false`), and **never** emits false HDD unmount alerts.

```dotenv
HOMEAGENTP_NAS_ADAPTER_ENABLED=true
HOMEAGENTP_NAS_TELEMETRY_MODE=host_snapshot
HOMEAGENTP_NAS_HOST_SNAPSHOT_REL_PATH=nas_host_snapshot.json
HOMEAGENTP_NAS_CONTAINER_SNAPSHOT_REL_PATH=containers_snapshot.json
HOMEAGENTP_NAS_SNAPSHOT_MAX_AGE_SECONDS=180
HOMEAGENTP_NAS_SCHEDULER_ENABLED=true
HOMEAGENTP_NAS_COLLECTION_INTERVAL_SECONDS=60
HOMEAGENTP_NAS_COLLECTION_TIMEOUT_SECONDS=10.0
HOMEAGENTP_NAS_MIN_PERSIST_INTERVAL_SECONDS=15
HOMEAGENTP_NAS_HISTORY_RETENTION_LIMIT=120
```

### 7.2. Host & Container Snapshot JSON Schemas & Freshness (`P02-F03`)

Both snapshot files are read via the TOCTOU-resistant `read_allowlisted_text_file()` (`O_NOFOLLOW`, `st_nlink == 1`) and validated for `schema_version`, `generated_at` (ISO-8601 UTC), and `ttl_seconds` (capped by `HOMEAGENTP_NAS_SNAPSHOT_MAX_AGE_SECONDS`). If `age_seconds > effective_ttl`, the snapshot is marked `status: "stale"` (`fresh: false`) and is **never** treated as live status.

#### Host Snapshot Schema (`homeagentp.nas_host.v1`)
```json
{
  "schema_version": "homeagentp.nas_host.v1",
  "generated_at": "2026-11-17T06:30:00+00:00",
  "ttl_seconds": 120,
  "cpu": {
    "status": "ok",
    "usage_percent": 18.4,
    "logical_cores": 4,
    "load_1m": 0.42,
    "load_5m": 0.35,
    "load_15m": 0.28,
    "pressure": { "status": "ok", "some": { "avg10": 0.5, "avg60": 0.2, "avg300": 0.1, "total_us": 4000 }, "full": null }
  },
  "memory": {
    "status": "ok",
    "total_bytes": 17179869184,
    "available_bytes": 12884901888,
    "used_bytes": 4294967296,
    "usage_percent": 25.0,
    "swap_total_bytes": 4294967296,
    "swap_free_bytes": 4294967296,
    "swap_used_bytes": 0,
    "swap_usage_percent": 0.0,
    "pressure": { "status": "ok", "some": null, "full": null }
  },
  "mounts": [
    { "mount_point": "/", "status": "mounted", "device": "/dev/nvme0n1p2", "fstype": "ext4", "total_bytes": 268435456000, "used_bytes": 53687091200, "available_bytes": 214748364800, "usage_percent": 20.0 },
    { "mount_point": "/mnt/disk1", "status": "mounted", "device": "/dev/sda1", "fstype": "ext4", "total_bytes": 8000000000000, "used_bytes": 4000000000000, "available_bytes": 4000000000000, "usage_percent": 50.0 },
    { "mount_point": "/mnt/disk2", "status": "mounted", "device": "/dev/sdb1", "fstype": "ext4", "total_bytes": 8000000000000, "used_bytes": 3200000000000, "available_bytes": 4800000000000, "usage_percent": 40.0 }
  ]
}
```

#### Container Health Snapshot Schema (`homeagentp.containers.v1`)
- Mounting `/var/run/docker.sock` into `homeagentp-core` is **strictly prohibited**.
- A separate one-shot host systemd service/timer (running outside `homeagentp-core`) writes `containers_snapshot.json` atomically (`tmp` + `mv`) into the directory mounted `:ro` at `/config/reports` inside `homeagentp-core`:
```json
{
  "schema_version": "homeagentp.containers.v1",
  "generated_at": "2026-11-17T06:30:00+00:00",
  "ttl_seconds": 120,
  "containers": [
    {
      "name": "jellyfin",
      "state": "running",
      "memory_used_bytes": 900000000,
      "memory_limit_bytes": 2147483648,
      "cpu_percent": 12.5,
      "restart_count": 0
    }
  ]
}
```

### 7.3. Automatic Collection Scheduler (`P02-F02`) & Alert Lifecycle (`P02-F04`)

- **Background Scheduler (`NasCollectionScheduler`):** Runs every `HOMEAGENTP_NAS_COLLECTION_INTERVAL_SECONDS` (`60s` default) inside the FastAPI `lifespan`, guarded by an `asyncio.Lock` to prevent overlapping runs and `asyncio.wait_for` (`10s` default timeout). Skips SQLite writes when telemetry is `unavailable` and throttles repeated writes within `HOMEAGENTP_NAS_MIN_PERSIST_INTERVAL_SECONDS` when `adapter_status` is unchanged.
- **Stateful Alert Lifecycle (`nas_alerts`):** Deduplicates active alerts by `alert_key` (`{component}:{code}`), updating `last_seen_at` and incrementing `occurrences`. Automatically marks cleared alerts `status = 'resolved'` with `resolved_at`, and inserts a new `active` row if the fault re-occurs later.

---

## 8. Mandatory Pre-Production Checklist (Must Complete Before Any NAS Deployment)

Before requesting owner approval to deploy HomeAgentP onto the production Debian 12 / CasaOS NAS:

1. **Docker Compose Staging Verification (Phase 01 F05 & Phase 02):**
   - Run `deploy/docker-compose.dev.yml` on an isolated Linux staging host with a Docker daemon.
   - Verify container startup, healthcheck (`/api/v1/health`), Nginx reverse proxy, authentication, CSRF enforcement, SQLite persistence across restarts, read-only rootfs, and non-root UID/GID (`10001:10001` and `101:101`).
2. **Stopped-Database Restore Drill:**
   - Stop `homeagentp-core` completely, run `restore_sqlite_database()` to replace the active SQLite database file from a verified backup, run `PRAGMA integrity_check;` and `PRAGMA foreign_key_check;`, and restart `homeagentp-core` to confirm clean recovery.
3. **Security Review & Hardening of Existing Antigravity Terminal Container (`ttyd` Port `7681`):**
   - Audit the pre-existing Antigravity terminal container on the NAS (currently running as `root`, mounting `/var/run/docker.sock` RW, and exposing `ttyd` on `0.0.0.0:7681`).
   - Restrict network exposure (bind to localhost/VPN only), remove unnecessary root/Docker socket privileges, and **never** use that container to run unreviewed AI-generated deployment scripts.

