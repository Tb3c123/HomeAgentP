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

## 7. Phase 02 — NAS Guardian Configuration & Operational Notes

### 7.1. Read-Only NAS Adapter Settings (`.env`)

By default, `HOMEAGENTP_NAS_ADAPTER_ENABLED=false` so development environments never fabricate live NAS metrics and instead return `unavailable`. To enable read-only telemetry collection in staging:

```dotenv
HOMEAGENTP_NAS_ADAPTER_ENABLED=true
HOMEAGENTP_NAS_PROC_ROOT=/proc
HOMEAGENTP_NAS_ROOT_MOUNT_PATH=/
HOMEAGENTP_NAS_REQUIRED_MOUNTS=/mnt/disk1,/mnt/disk2
HOMEAGENTP_NAS_EXPECTED_SERVICES=jellyfin,sonarr,radarr,bazarr,prowlarr,seerr,qbittorrent,adguard,portainer
HOMEAGENTP_NAS_CONTAINER_SNAPSHOT_REL_PATH=
HOMEAGENTP_NAS_COLLECTION_INTERVAL_SECONDS=60
HOMEAGENTP_NAS_HISTORY_RETENTION_LIMIT=500
```

### 7.2. Mount Guardian & Unmounted Fallback Detection (`/mnt/disk1`, `/mnt/disk2`)

- **Problem:** When an external/internal data drive (`/mnt/disk1` or `/mnt/disk2`) is accidentally unmounted on Linux, the empty mount directory on `/` still exists. A naive `os.statvfs("/mnt/disk1")` call would report the root SSD's capacity and free space, hiding the lost mount and risking writes filling up `/`.
- **Mitigation in `inspect_mount_point()`:**
  1. Verifies the path is not a symlink (`lstat`).
  2. Parses `/proc/mounts` to check if the canonical mount point is an active mount entry.
  3. Compares `st_dev` of the mount directory against `st_dev` of `HOMEAGENTP_NAS_ROOT_MOUNT_PATH` (`/`).
  4. If the directory exists on disk (`S_ISDIR`) but is absent from `/proc/mounts` or shares `st_dev` with `/`, Mount Guardian marks it `status: "unmounted_fallback"`, `is_root_fallback: true`, suppresses misleading disk capacity numbers (`null`), and emits a `critical` alert (`mount:<path>:unmounted_fallback`).
- **Storage Safety:** Mount Guardian only calls `lstat` and `statvfs` on the top-level mount point path. It performs **zero writes** to HDDs and **never walks media subdirectories**.

### 7.3. Container Health Without `/var/run/docker.sock`

- Mounting `/var/run/docker.sock` into `homeagentp-core` is **strictly prohibited** by `AGENTS.md` (equivalent to host root).
- Instead, `homeagentp-core` reads an optional, allowlisted read-only JSON snapshot (`HOMEAGENTP_NAS_CONTAINER_SNAPSHOT_REL_PATH`) inside `HOMEAGENTP_REPORTS_DIR` via the hardened `read_allowlisted_text_file()` descriptor reader (`O_NOFOLLOW`, `st_nlink == 1`).
- If `HOMEAGENTP_NAS_CONTAINER_SNAPSHOT_REL_PATH` is empty or unreadable, container health honestly reports `status: "unavailable"` without breaching container isolation.

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

