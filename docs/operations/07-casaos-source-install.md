# HomeAgentP — Local-source Docker build and CasaOS installation handoff

**Deployment mode:** Git clone + `docker compose build` on the Debian 12 NAS. **No image publishing to Docker Hub/GHCR is required**; `apps/core/Dockerfile` and `apps/web/Dockerfile` build locally. Dependencies/base images are still pulled from upstream registries when not cached; "no push" does not imply offline builds.

**Owner instruction (2026-11-18):** prepare and push to GitHub; owner will direct Antigravity CLI to perform NAS installation. **This commit does not deploy or authorize any NAS command by this assistant.** Preserve existing Antigravity CLI, Jellyfin, downloads, AdGuard, and Portainer containers. CLI accesses must not be changed.

## Installation architecture

- `deploy/docker-compose.casaos.yml`: two locally built images `homeagentp-core:local` and `homeagentp-web:local`; no GHCR dependency for application images.
- Builds use source paths `../apps/core` and `../apps/web` relative to the Compose file in `deploy`. **Do not paste this YAML into CasaOS Custom Install and expect relative build paths to resolve**; CasaOS versions vary in support for build directives. Preferred initial installation is owner-supervised Docker Compose from the checked-out repo. Verify actual CasaOS visibility/app management separately; do not create duplicate stacks through UI import.
- App name `homeagentp`, network `homeagentp_internal`, SQLite Docker named volume `homeagentp_core_data` (verify Docker data-root SSD placement before starting). Core not published to host; Web on `127.0.0.1:8310` by default.
- Persistent SQLite is in a dedicated volume; reports read-only from `deploy/runtime/reports`, scripts read-only from `config/examples/scripts`. **No NAS media HDD or Docker socket mount.** If the operator wants live workspace artifacts visible in the dashboard, create and separately approve narrowly scoped host directories and read-only mounts first.
- All NAS/media/HA/Telegram schedulers disabled by default. Offline-only dashboard metadata is expected. No hidden installation-time systemd, firewall, tunnel, NAS snapshot or Docker socket modifications.

## Operator preflight checklist — before any NAS-changing action

1. Confirm the NAS truly runs **CasaOS** and identify its version. Earlier host inventory showed Debian 12 and Docker; the existence of a running CasaOS service/UI was **not** proven. If ZimaOS or another frontend is installed, adjust UI instructions after inspection, not the verified Docker Compose semantics.
2. Confirm `docker compose version`, Docker data-root on SSD, at least 1 GiB available for app data/build (actual build needs additional temporary image/layer space), and no existing `homeagentp` app/stack/volume. Confirm loopback TCP 8310 free. No clean-up/removal of unrelated services.
3. Review the exact repository commit or release tag; do not deploy arbitrary `main` HEAD without recording SHA.
4. Decide access route: initial loopback-only using SSH local port forwarding, or separately approve LAN reverse proxy/HTTPS. **Changing `HOMEAGENTP_BIND_IP` to `0.0.0.0` opens the web interface on all host interfaces**; only do that after access control review. For HTTPS access, `HOMEAGENTP_COOKIE_SECURE=true` after verifying proxy headers and TLS.
5. Select backup destination/retention for the named volume; determine desired RPO/RTO. No backup plan means production remains NO-GO.

## Antigravity operator sequence — REQUIRES OWNER APPROVAL FOR NAS EXECUTION

Below are examples for Antigravity to review with the owner on the target NAS, **not commands executed by this assistant**. Paths are illustrative.

```bash
# Clone into a suitable folder on SSD (choose/confirm path first).
git clone https://github.com/Tb3c123/HomeAgentP.git HomeAgentP
cd HomeAgentP
git rev-parse HEAD
docker compose version

# Create local-only configuration; never commit secrets.
cp deploy/.env.casaos.example deploy/.env
chmod 600 deploy/.env
# Edit deploy/.env using an editor and replace BOTH placeholder secrets.
# Prefer cryptographic random values; never paste credentials into chat or logs.
mkdir -p deploy/runtime/reports

# Inspect resolved config WITHOUT printing secrets (quiet mode).
docker compose --env-file deploy/.env -f deploy/docker-compose.casaos.yml config --quiet

# Only after operator validates preflight, service names, and exact targets:
docker compose --env-file deploy/.env -f deploy/docker-compose.casaos.yml build
docker compose --env-file deploy/.env -f deploy/docker-compose.casaos.yml up -d --no-build --wait

# Non-secret health check from NAS localhost:
curl -fsS http://127.0.0.1:8310/api/v1/health
docker compose --env-file deploy/.env -f deploy/docker-compose.casaos.yml ps
```

**Important:** The copied example secrets must be replaced before `build`/`up`; `config --quiet` verifies Compose syntax/substitution but does not validate password strength. The installer must check for placeholder values separately, without exposing the actual secrets. Compose uses `env_file` only for interpolation; the app container receives explicitly allowlisted environment values via `environment`.

For a remote workstation, SSH local forwarding offers a private first login path (replace `NAS_HOST` with approved LAN/VPN name):

```bash
ssh -L 8310:127.0.0.1:8310 NAS_HOST
```

Then open `http://127.0.0.1:8310` on that workstation. Do not alter ttyd 7681, Cloudflare Tunnel or existing SSH access for this procedure.

## Acceptance after deployment

- `/api/v1/health` responds OK and Web loads, Core remains internal-only.
- Log in using owner-set admin password; verify tasks, briefs, artifacts and sample scripts. No demo metadata seeded.
- Verify Web/Core run as fixed non-root, read-only rootfs, `cap_drop: ALL`, no docker.sock, no host network/privileged, no HDD mounts.
- Confirm existing services remain healthy and original ports unchanged.
- Confirm SQLite state persists across a controlled restart (only with explicit operator approval), then make/verify a backup to an **independent** protected path and scratch restore. No live in-place restore.
- Check app is visible/manageable in installed CasaOS version. If not, do **not** import a second duplicate app to force a tile: use the running Compose project, or investigate CasaOS app packaging separately.

## Rollback and update limits

- Build-only (before `up`) can be abandoned without changing existing applications.
- If application health fails after `up`, the operator can stop **only this Compose project** after checking the project name; never use `docker system prune`, `docker compose down -v`, `docker volume rm`, or commands targeting other projects.
- Local `:local` images are mutable tags: rebuilding replaces the tag. **Before any update**, preserve known-good Git commit and image identifiers plus a verified, schema-compatible SQLite backup. Rollback is not guaranteed by `git checkout` alone, because database migrations may be one-way.
- Production use requires backup destination, restore drill, access/TLS policy and owner signoff; initial source build is a staging installation, not a completed production acceptance.

## Practical limitation

CasaOS itself may not build local Dockerfile contexts from an imported YAML (the UI may assume a prebuilt image). The owner-selected no-registry plan is therefore: build/start with `docker compose` under the exact repository checkout, then use CasaOS UI where that version supports viewing/managing externally created Compose projects. **Do not claim CasaOS native app/tile support without verifying the installed version.**
