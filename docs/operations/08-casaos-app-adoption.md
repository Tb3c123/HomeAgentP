# HomeAgentP — CasaOS AppManagement Adoption & Rollback Runbook

**Goal:** Convert the externally created `homeagentp` Docker Compose stack (`deploy/docker-compose.casaos.yml`) into a single CasaOS-managed application (`HomeAgentP`) without losing SQLite data (`homeagentp_homeagentp_core_data`), without creating duplicate containers, and without weakening security constraints.

---

## 1. Why a Dedicated CasaOS Compose File Is Required

1. **No relative `build:` context in CasaOS:** CasaOS v0.4.x copies app Compose files into `/var/lib/casaos/apps/homeagentp/docker-compose.yml`. Relative build paths (`../apps/core`, `../apps/web`) fail in that directory. Therefore, `deploy/docker-compose.casaos-app.yml` omits `build:` and references the locally built images `homeagentp-core:local` and `homeagentp-web:local`.
2. **External SQLite volume:** The existing SQLite database lives in Docker named volume `homeagentp_homeagentp_core_data`. Declaring `external: true` with `name: homeagentp_homeagentp_core_data` guarantees CasaOS attaches to the existing volume instead of creating an empty new volume.
3. **Absolute bind-mount paths:** `HOMEAGENTP_REPO_DIR` defaults to `/home/tb3c/HomeAgentP` so `/config/scripts` and `/config/reports` resolve correctly from `/var/lib/casaos/apps/homeagentp/`.
4. **CasaOS project/container naming:** Using `name: homeagentp` and app ID `homeagentp` keeps container names (`homeagentp-homeagentp-core-1`, `homeagentp-homeagentp-web-1`) and network (`homeagentp_homeagentp_internal`) consistent and avoids duplicate stacks.
5. **Localhost binding (`127.0.0.1:8310`):** `x-casaos` sets `main: homeagentp-web` and `port_map: "8310"`. Because `HOMEAGENTP_BIND_IP=127.0.0.1` by default, opening the tile from a remote LAN browser requires an SSH tunnel (`ssh -L 8310:127.0.0.1:8310 tb3c@<NAS_HOST>`) unless a reverse proxy or LAN binding is separately approved.

---

## 2. Mandatory Pre-Migration SQLite Backup & Scratch Restore

Run on the NAS host **before** stopping the current stack. Never use `docker compose down -v` or `docker volume prune`.

```bash
BACKUP_DIR="/home/tb3c/HomeAgentP/deploy/runtime/backups"
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

# 1. Consistent hot backup of SQLite inside the running Core container
TS=$(date -u +%Y%m%dT%H%M%SZ)
docker exec homeagentp-homeagentp-core-1 python3 -c "
import sqlite3
src = sqlite3.connect('/data/homeagentp.db')
dst = sqlite3.connect('/tmp/homeagentp-backup.db')
src.backup(dst)
dst.close()
src.close()
"
docker cp homeagentp-homeagentp-core-1:/tmp/homeagentp-backup.db "$BACKUP_DIR/homeagentp-${TS}.db"
docker exec homeagentp-homeagentp-core-1 rm -f /tmp/homeagentp-backup.db
chmod 600 "$BACKUP_DIR/homeagentp-${TS}.db"

# 2. Scratch restore verification (integrity check + row count)
sqlite3 "$BACKUP_DIR/homeagentp-${TS}.db" "PRAGMA integrity_check; SELECT COUNT(*) FROM users; SELECT COUNT(*) FROM tasks;"
```

Proceed **only** if `PRAGMA integrity_check` returns `ok`.

---

## 3. Controlled Migration Steps (Requires Owner Approval)

1. **Verify local images exist:**
   ```bash
   docker image inspect homeagentp-core:local homeagentp-web:local >/dev/null
   ```
2. **Stop and remove the external Compose containers/network (KEEPING the volume):**
   ```bash
   cd /home/tb3c/HomeAgentP
   docker compose --env-file deploy/.env -f deploy/docker-compose.casaos.yml down
   # Verify volume still exists:
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
5. **Register/Apply the app in CasaOS AppManagement:**
   ```bash
   sudo casaos-cli app-management apply homeagentp \
     -f /var/lib/casaos/apps/homeagentp/docker-compose.yml
   ```
   *(If `casaos-cli` is unavailable, open CasaOS UI -> App Store -> Custom Install -> Import `deploy/docker-compose.casaos-app.yml`, ensuring `/var/lib/casaos/apps/homeagentp/.env` is present or variables are populated in the UI without exposing them.)*

---

## 4. Post-Migration Verification

1. Confirm only two HomeAgentP containers exist and both are `healthy`:
   ```bash
   docker ps --filter "name=homeagentp" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
   ```
2. Confirm `/api/v1/health` responds `200 OK` on `127.0.0.1:8310`:
   ```bash
   curl -fsS http://127.0.0.1:8310/api/v1/health
   ```
3. Confirm SQLite still points to `homeagentp_homeagentp_core_data` and preserves existing users/tasks.
4. Confirm security posture: non-root (`10001:10001`, `101:101`), `ReadonlyRootfs: true`, `cap_drop: [ALL]`, `no-new-privileges:true`, no Docker socket, no `/mnt/disk1` or `/mnt/disk2` mounts.
5. Confirm all 10 pre-existing NAS containers remain untouched.

---

## 5. Rollback Procedure

If CasaOS adoption fails or behaves unexpectedly:

1. **Stop/uninstall only the CasaOS app entry** (do **not** delete external volume `homeagentp_homeagentp_core_data`):
   ```bash
   sudo docker compose -f /var/lib/casaos/apps/homeagentp/docker-compose.yml down
   ```
2. **Restore original external Compose stack:**
   ```bash
   cd /home/tb3c/HomeAgentP
   docker compose --env-file deploy/.env -f deploy/docker-compose.casaos.yml up -d --no-build --wait
   ```
3. **If SQLite data was altered**, restore from `$BACKUP_DIR/homeagentp-${TS}.db` into `homeagentp_homeagentp_core_data` while Core is stopped, then start Core/Web again.
