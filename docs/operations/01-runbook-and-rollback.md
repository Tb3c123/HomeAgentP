# Phase 01 — Operations Runbook, Security Notes, Backup & Rollback

> **Scope Notice:** This runbook applies to **local development and isolated staging** for Phase 01 Foundation. It does **not** grant permission to deploy onto the production Debian 12 / CasaOS NAS without separate explicit owner approval.

---

## 1. Local Development Startup (User-Space, Without Docker)

### 1.1. Prepare `.env` (Local Only — Never Commit)

```bash
cp config/examples/.env.example .env
```

Generate a fresh random secret key and set a strong local development password in `.env`:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Update `HOMEAGENTP_SECRET_KEY` and `HOMEAGENTP_ADMIN_PASSWORD` in `.env`. Note that `homeagentp-core` intentionally refuses to start if placeholder secrets from `.env.example` are left unchanged.

### 1.2. Start `homeagentp-core` (Port 8311)

```bash
cd apps/core
uv venv .venv
uv pip install -e ".[dev]"
.venv/bin/uvicorn homeagentp_core.main:create_app --factory --host 127.0.0.1 --port 8311
```

### 1.3. Start `homeagentp-web` (Port 8310)

In a second terminal:

```bash
cd apps/web
npm install
npm run dev
```

Open `http://127.0.0.1:8310` to sign in and inspect the Dashboard.

---

## 2. Local Containerized Staging (`deploy/docker-compose.dev.yml`)

When testing on a workstation with Docker Compose installed (not on the production NAS):

```bash
cp config/examples/.env.example .env
# Edit .env to set random HOMEAGENTP_SECRET_KEY and HOMEAGENTP_ADMIN_PASSWORD
docker compose --env-file .env -f deploy/docker-compose.dev.yml up --build -d
```

### Shutdown

```bash
docker compose --env-file .env -f deploy/docker-compose.dev.yml down
```

---

## 3. Consistent SQLite Backup & Isolated Restore Verification

`homeagentp-core` runs SQLite in `WAL` mode and provides `backup_sqlite_database()` in `apps/core/src/homeagentp_core/db/connection.py` using SQLite's online backup API.

### Create a Consistent Online Backup

```bash
apps/core/.venv/bin/python -c "
from pathlib import Path
from homeagentp_core.db.connection import backup_sqlite_database
backup_sqlite_database(Path('./data/homeagentp.db'), Path('./data/backups/homeagentp-backup.db'))
print('Backup completed.')
"
```

### Verify Restore in an Isolated Path

```bash
apps/core/.venv/bin/python -c "
import sqlite3
conn = sqlite3.connect('./data/backups/homeagentp-backup.db')
print('Integrity check:', conn.execute('PRAGMA integrity_check;').fetchone()[0])
print('Schema version:', conn.execute('SELECT version FROM schema_migrations').fetchall())
conn.close()
"
```

---

## 4. Security & Threat Model Notes (Phase 01)

1. **No Consumer Antigravity CLI Wrapping:** HomeAgentP does not call, proxy, or wrap `agy` or consumer OAuth tokens. Task handoff uses Git branches, PRs, and Markdown Task Briefs.
2. **Least Privilege & Container Hardening:**
   - `homeagentp-core` runs as UID/GID `10001:10001`.
   - `homeagentp-web` runs as UID/GID `101:101`.
   - Both containers drop all Linux capabilities (`cap_drop: [ALL]`), enforce `no-new-privileges:true`, use `read_only: true` root filesystems, and mount **no** `/var/run/docker.sock` or `/mnt/disk*`.
3. **Read-Only Script & Report Viewer:**
   - `read_allowlisted_text_file()` rejects `..` traversal, absolute paths, and any intermediate or leaf symlinks (`Path.is_symlink()` + `O_NOFOLLOW`), and verifies SHA-256 digests against registered manifests.
   - `is_executable_allowed` is constrained to `0` at the SQLite schema level (`CHECK (is_executable_allowed = 0)`).
4. **Authentication & CSRF:**
   - Passwords hashed with PBKDF2-HMAC-SHA256 (`600,000` iterations).
   - Session tokens are stored only as HMAC-SHA256 hashes in SQLite.
   - All state-changing endpoints require a matching `X-CSRF-Token` header.
5. **Log Redaction:**
   - `SecretRedactingFilter` scrubs inline `password=...`, `secret=...`, `token=...`, `Bearer ...`, and `homeagentp_session=...` strings before emitting JSON logs.

---

## 5. Rollback Procedure

1. **Code / Git Rollback (Development Repository):**
   - Close or revert the feature branch PR without merging to `main`, or revert the merge commit via `git revert <commit_sha>`.
2. **Local Staging Container Rollback:**
   - Stop containers: `docker compose -f deploy/docker-compose.dev.yml down`.
   - Restore the previous SQLite backup file from `./data/backups/homeagentp-backup.db` to `./data/homeagentp.db`.
   - Checkout the previous known-good Git tag/commit and rebuild.

---

## 6. Troubleshooting

| Symptom | Likely Cause | Safe Resolution |
| :--- | :--- | :--- |
| `ValidationError: HOMEAGENTP_SECRET_KEY uses a disallowed placeholder value` | `.env` still contains placeholder values from `.env.example`. | Generate a new random secret (`python3 -c "import secrets; print(secrets.token_urlsafe(32))"`) and update `.env`. |
| `401 Unauthorized` on Dashboard or API calls | Session expired or cookie not sent over HTTP when `HOMEAGENTP_COOKIE_SECURE=true`. | For localhost HTTP dev, set `HOMEAGENTP_COOKIE_SECURE=false` in `.env` and sign in again. |
| `403 Forbidden: Missing or invalid CSRF token` | Write request (`POST`/`PATCH`) missing `X-CSRF-Token` header or using an outdated token. | Refresh `/api/v1/auth/me` or sign out and back in so the UI holds the active session's CSRF token. |
| `403 Forbidden: Symlinks are prohibited` or `SHA-256 checksum mismatch` | Script file in `HOMEAGENTP_SCRIPTS_DIR` was replaced with a symlink or edited without updating `manifest.json`. | Remove symlinks, restore the reviewed script file, or update the manifest SHA-256 after human review. |
| `sqlite3.OperationalError: database is locked` | Concurrent write or stale process holding a lock on `homeagentp.db`. | Stop duplicate local `uvicorn` processes; `WAL` mode and `busy_timeout=5000` handle normal concurrency. |

