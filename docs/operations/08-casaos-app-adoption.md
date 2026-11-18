# HomeAgentP — CasaOS AppManagement Adoption & Rollback Runbook

**Goal:** Convert the externally created `homeagentp` Docker Compose stack (`deploy/docker-compose.casaos.yml`) into a single CasaOS-managed application (`HomeAgentP`) without losing SQLite data (`homeagentp_homeagentp_core_data`), without creating duplicate containers, and without weakening security constraints.

---

## 1. Pre-Flight Verification on NAS Host (Read-Only)

Before any migration step, verify the installed CasaOS version and exact `casaos-cli` AppManagement subcommands directly on the NAS host (do **not** assume CLI flags without checking `--help`):

```bash
casaos -v
casaos-cli --help
casaos-cli app-management --help
```

Also verify the running external stack and volume:

```bash
docker ps --filter "name=homeagentp" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
docker volume inspect homeagentp_homeagentp_core_data
```

---

## 2. Why a Dedicated CasaOS Compose File Is Required

1. **No relative `build:` context in CasaOS:** CasaOS v0.4.x stores app Compose files in `/var/lib/casaos/apps/homeagentp/docker-compose.yml`. Relative build paths (`../apps/core`, `../apps/web`) fail from that directory. Therefore, `deploy/docker-compose.casaos-app.yml` omits `build:` and references the locally built images `homeagentp-core:local` and `homeagentp-web:local`.
2. **External SQLite volume protection:** The existing SQLite database lives in Docker named volume `homeagentp_homeagentp_core_data`. Declaring `external: true` with `name: homeagentp_homeagentp_core_data` guarantees Docker Compose attaches to the existing volume even if CasaOS alters the Compose project name.
3. **Project & network naming:** Setting `name: homeagentp` and registering the CasaOS app ID as `homeagentp` preserves consistent container names (`homeagentp-homeagentp-core-1`, `homeagentp-homeagentp-web-1`) and network (`homeagentp_homeagentp_internal`). Stopping the external Compose stack (without `-v`) before registering in CasaOS prevents duplicate stacks and port `8310` conflicts.
4. **Environment variables & secrets (`HOMEAGENTP_SECRET_KEY`, `HOMEAGENTP_ADMIN_PASSWORD`):**
   - `deploy/docker-compose.casaos-app.yml` uses `${HOMEAGENTP_SECRET_KEY:?...}` and `${HOMEAGENTP_ADMIN_PASSWORD:?...}` interpolation so secrets are never stored in Git or Compose YAML.
   - When CasaOS runs `docker compose` inside `/var/lib/casaos/apps/homeagentp/`, Compose automatically loads `/var/lib/casaos/apps/homeagentp/.env` if present. Copy `/home/tb3c/HomeAgentP/deploy/.env` there with `chmod 600` before applying.
   - Note: If you later edit app settings in the CasaOS Web UI, verify that CasaOS does not strip `.env` interpolation or write plaintext secrets into `docker-compose.yml`.
5. **Absolute bind-mount paths & localhost binding:** `HOMEAGENTP_REPO_DIR` defaults to `/home/tb3c/HomeAgentP` so `/config/scripts` and `/config/reports` resolve from `/var/lib/casaos/apps/homeagentp/`. `HOMEAGENTP_BIND_IP` remains `127.0.0.1` (`8310`), so remote access continues to use SSH port forwarding (`ssh -L 8310:127.0.0.1:8310 tb3c@<NAS_HOST>`) unless a reverse proxy is separately approved.

---

## 3. Mandatory Pre-Migration SQLite Backup & Independent Scratch Restore

Run on the NAS host **before** stopping the current stack. Never use `docker compose down -v` or `docker volume prune`.

```bash
BACKUP_DIR="/home/tb3c/HomeAgentP/deploy/runtime/backups"
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

TS=$(date -u +%Y%m%dT%H%M%SZ)
BACKUP_FILE="$BACKUP_DIR/homeagentp-${TS}.db"
SCRATCH_FILE="/tmp/homeagentp-scratch-${TS}.db"

# 1. Consistent online backup using SQLite backup API inside Core container
docker exec homeagentp-homeagentp-core-1 python3 -c "
import sqlite3
src = sqlite3.connect('/data/homeagentp.db')
dst = sqlite3.connect('/tmp/homeagentp-backup.db')
src.backup(dst)
dst.close()
src.close()
"
docker cp homeagentp-homeagentp-core-1:/tmp/homeagentp-backup.db "$BACKUP_FILE"
docker exec homeagentp-homeagentp-core-1 rm -f /tmp/homeagentp-backup.db
chmod 600 "$BACKUP_FILE"

# 2. Restore into an independent scratch database and run full integrity checks
python3 - "$BACKUP_FILE" "$SCRATCH_FILE" <<'PY'
import os, sqlite3, sys

backup_path, scratch_path = sys.argv[1], sys.argv[2]
if os.path.exists(scratch_path):
    os.remove(scratch_path)

src = sqlite3.connect(backup_path)
dst = sqlite3.connect(scratch_path)
src.backup(dst)
src.close()

integrity = dst.execute("PRAGMA integrity_check;").fetchall()
fk_violations = dst.execute("PRAGMA foreign_key_check;").fetchall()
users_cnt = dst.execute("SELECT COUNT(*) FROM users;").fetchone()[0]
tasks_cnt = dst.execute("SELECT COUNT(*) FROM tasks;").fetchone()[0]
dst.close()

print("integrity_check:", integrity)
print("foreign_key_check:", fk_violations)
print("users:", users_cnt, "tasks:", tasks_cnt)

assert integrity == [("ok",)], f"Integrity check failed: {integrity}"
assert fk_violations == [], f"Foreign key violations: {fk_violations}"
PY

rm -f "$SCRATCH_FILE"
```

Proceed **only** if `integrity_check` is `[('ok',)]` and `foreign_key_check` is `[]`.

---

## 4. Controlled Migration Steps (Requires Separate Owner Approval)

1. **Confirm local images exist:**
   ```bash
   docker image inspect homeagentp-core:local homeagentp-web:local >/dev/null
   ```
2. **Stop and remove the external Compose containers/network (KEEPING the volume):**
   ```bash
   cd /home/tb3c/HomeAgentP
   docker compose --env-file deploy/.env -f deploy/docker-compose.casaos.yml down
   docker volume inspect homeagentp_homeagentp_core_data >/dev/null
   ```
3. **Prepare CasaOS app directory and `.env` (never commit `.env`):**
   ```bash
   sudo mkdir -p /var/lib/casaos/apps/homeagentp
   sudo cp /home/tb3c/HomeAgentP/deploy/docker-compose.casaos-app.yml /var/lib/casaos/apps/homeagentp/docker-compose.yml
   sudo cp /home/tb3c/HomeAgentP/deploy/.env /var/lib/casaos/apps/homeagentp/.env
   sudo chmod 600 /var/lib/casaos/apps/homeagentp/.env
   ```
4. **Validate resolved config without printing secrets:**
   ```bash
   sudo docker compose --env-file /var/lib/casaos/apps/homeagentp/.env \
     -f /var/lib/casaos/apps/homeagentp/docker-compose.yml config --quiet
   ```
5. **Apply/install in CasaOS AppManagement using the exact subcommand verified in Section 1:**
   - Use the `casaos-cli app-management ...` command shown by `casaos-cli app-management --help` targeting `/var/lib/casaos/apps/homeagentp/docker-compose.yml` (or use CasaOS Web UI -> App Store -> Custom Install -> Import `deploy/docker-compose.casaos-app.yml` after `.env` is in place).

---

## 5. Post-Migration Verification

1. Confirm only two HomeAgentP containers exist and both are `healthy`:
   ```bash
   docker ps --filter "name=homeagentp" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
   ```
2. Confirm `/api/v1/health` responds `200 OK` on `127.0.0.1:8310`:
   ```bash
   curl -fsS http://127.0.0.1:8310/api/v1/health
   ```
3. Confirm Core still mounts `homeagentp_homeagentp_core_data` at `/data` and preserves `users`/`tasks` counts.
4. Confirm security posture: non-root (`10001:10001`, `101:101`), `ReadonlyRootfs: true`, `cap_drop: [ALL]`, `no-new-privileges:true`, no Docker socket, no `/mnt/disk1` or `/mnt/disk2` mounts.
5. Confirm all 10 pre-existing NAS containers remain untouched.

---

## 6. Rollback Procedure (Preserving SQLite Volume)

If CasaOS adoption fails or behaves unexpectedly:

1. **Stop/remove only the CasaOS app containers** (never pass `-v` or delete `homeagentp_homeagentp_core_data`):
   ```bash
   sudo docker compose --env-file /var/lib/casaos/apps/homeagentp/.env \
     -f /var/lib/casaos/apps/homeagentp/docker-compose.yml down
   docker volume inspect homeagentp_homeagentp_core_data >/dev/null
   ```
2. **Restore the original external Compose stack:**
   ```bash
   cd /home/tb3c/HomeAgentP
   docker compose --env-file deploy/.env -f deploy/docker-compose.casaos.yml up -d --no-build --wait
   ```
3. **If SQLite data was corrupted**, stop Core (`docker compose ... stop homeagentp-core`), restore `$BACKUP_FILE` to `/data/homeagentp.db` inside the volume, and start Core/Web again.
