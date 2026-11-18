# HomeAgentP

HomeAgentP is a personal AI workspace and home NAS operations platform.

## Architecture: B+ (Antigravity-first, Dashboard-light)

- The owner actively uses Antigravity CLI with Remote Control on the NAS for AI coding and work. HomeAgentP does not wrap or programmatically control the CLI or consumer account.
- `homeagentp-web`: NAS dashboard, media/downloads overview, Home Automation overview, task board, read-only script registry, reports/artifacts, and safety settings.
- `homeagentp-core`: authentication, SQLite metadata & migrations, read-only NAS/media monitoring foundation, task/attempt registry, and strict read-only script/report viewer.
- Git and files are the handoff mechanism between AI work and HomeAgentP.

## Development scope

1. **Foundation (Phase 01)**: dashboard, authentication, SQLite metadata, task registry, read-only script viewer, two-container structure.
2. **NAS Guardian (Phase 02)**: metrics, mount checks, service health, read-only alerts.
3. **Media and downloads (Phase 03)**: Jellyfin, Sonarr, Radarr, Bazarr, Prowlarr, Seerr, qBittorrent.
4. **Workspace (Phase 04)**: scripts, tasks, artifacts, Git handoff and task briefs.
5. **Home Assistant & Telegram Notifications (Phase 05)**: opt-in read-only HA status and outbound alerts.
6. **Operations, Backups & Recovery (Phase 06)**: isolated restore drills, non-mutating preflight, staging, operator readiness and explicit deployment gates.

## Safety

- No NAS deployment without explicit approval.
- No host root or Docker socket in HomeAgentP containers.
- No credentials or real `.env` in Git.
- No consumer OAuth proxy to Antigravity.
- Verify security and restore before production use.

## Status

- **Phase 01 Foundation (`feature/phase-01-foundation`, PR #1)**: Implemented, hardened (`F01`–`F04`), and verified with isolated unit/integration tests (`pytest`, `ruff`, `mypy`, `tsc`, `vitest`, `vite build`, `npm audit`).
- **Phase 02 NAS Guardian (`feature/phase-02-nas-guardian`, PR #2)**: Implemented and hardened (`P02-F01`–`P02-F04`) with read-only CPU/RAM/PSI `/proc` parsers, Mount Guardian `/mnt/disk1` & `/mnt/disk2` with unmounted root-filesystem fallback detection, read-only Container Health snapshot adapter without Docker socket, alert lifecycle (`active`/`resolved`), non-overlapping scheduler, and SQLite metric history.
- **Phase 03 Media & Downloads (`feature/phase-03-media-downloads`, PR #3)**: Implemented and verified with isolated unit/integration tests (`pytest`, `ruff`, `mypy`, `tsc`, `vitest`, `vite build`). Includes uniform `MediaServiceAdapter`, SSRF-guarded read-only HTTP client (`SafeMediaHttpClient`), read-only connectors for Jellyfin, qBittorrent (WebUI v2 with strict client-side GET allowlist), Sonarr v3, Radarr v3, Bazarr, Prowlarr v1, and Seerr v1, consecutive-failure threshold state machine (`media_service_states`), unified alert lifecycle (`media_alerts`), non-overlapping `MediaCollectionScheduler`, and the Media & Downloads Monitoring Hub UI.
- **Phase 04 Workspace & Artifacts ([PR #4](https://github.com/Tb3c123/HomeAgentP/pull/4))**: **MERGED** into `main` at `28c11aab`. Versioned Task Briefs, Artifacts/Knowledge metadata, Git Provenance and Workspace UI implemented. Final [Core/Web/isolated Docker CI](https://github.com/Tb3c123/HomeAgentP/actions/runs/44094110523) **PASS**; live NAS still **NOT_TESTED**.
- **Phase 05 Home Assistant & Telegram ([PR #5](https://github.com/Tb3c123/HomeAgentP/pull/5))**: **MERGED** into `main` at `311b8b33`. Read-only HA monitoring and outbound Telegram notification outbox are implemented; critical rate-limit regression fixed. Final [Core/Web/isolated Docker CI](https://github.com/Tb3c123/HomeAgentP/actions/runs/44228050097) **PASS**. Live HA, Telegram and NAS remain **NOT_TESTED**; integrations default disabled until separately authorized.
- **Phase 06 Operations, Backup & Recovery ([PR #7](https://github.com/Tb3c123/HomeAgentP/pull/7))**: **MERGED** at `52ebb0c2`. SQLite backup/scratch restore, offline Compose preflight and isolated recovery CI passed. **NOT DEPLOYED**; live NAS/HA/Telegram **NOT_TESTED**.
- **Production Deployment Status**: **`NOT_DEPLOYED`**. Isolated GitHub Actions Docker staging has PASS evidence for Phase 03–04; this does not validate the real NAS. A live-environment preflight, stopped-DB restore drill, port/network and `ttyd` security hardening, approved credential handling and rollback plan remain required before NAS deployment.

---

## CasaOS installation from checked-out source (no registry push)\n\nThe owner-approved installation path is **build from local Dockerfiles**, not publishing HomeAgentP images to Docker Hub/GHCR. The source-build Compose file is `deploy/docker-compose.casaos.yml`, with a secret-free example `deploy/.env.casaos.example`. Have Antigravity read [CasaOS source-install handoff](docs/operations/07-casaos-source-install.md) before proposing NAS actions. Initial localhost binding and disabled NAS/media/HA/Telegram integrations are deliberate; real NAS install and CasaOS UI integration have not been tested.\n\n## Local Development & Verification Guide (No NAS Access Required)

### 1. Run `homeagentp-core` Tests, Linter & Typecheck

```bash
cd apps/core
uv venv .venv
uv pip install -e ".[dev]"
.venv/bin/pytest -v
.venv/bin/ruff check src ../../tests/core
.venv/bin/mypy src
```

### 2. Run `homeagentp-web` Typecheck, Unit Tests & Production Build

```bash
cd apps/web
npm install
npm run typecheck
npm test
npm run build
```

### 3. Run Local Development Servers (Localhost Only)

1. Copy `config/examples/.env.example` to `.env` at the repository root and set a random `HOMEAGENTP_SECRET_KEY` and strong `HOMEAGENTP_ADMIN_PASSWORD`.
2. Start Core on `127.0.0.1:8311` (from repository root):
   ```bash
   apps/core/.venv/bin/uvicorn homeagentp_core.main:create_app --factory --host 127.0.0.1 --port 8311
   ```
3. Start Web on `127.0.0.1:8310`:
   ```bash
   cd apps/web
   npm run dev
   ```
4. See [docs/operations/01-runbook-and-rollback.md](docs/operations/01-runbook-and-rollback.md), [docs/plans/02-nas-guardian.md](docs/plans/02-nas-guardian.md), and [docs/plans/03-media-downloads.md](docs/plans/03-media-downloads.md) for containerized local staging (`deploy/docker-compose.dev.yml`), Phase 02 NAS Guardian read-only telemetry configuration, Phase 03 Media & Downloads read-only connector configuration, atomic SQLite backup/restore verification, TOCTOU threat model notes, and rollback procedures.

---

## Start here — Antigravity / external implementer (Tiếng Việt)

**Không giao lệnh “cài tất cả HomeAgentP lên NAS” ngay trong prompt đầu tiên.**

1. Đọc [Product scope](docs/00-project-scope.md): HomeAgentP bao gồm NAS, media, downloads, Home Assistant, alerts, AI workspace, developer, security; **không chỉ Dev**.
2. Đọc [AGENTS.md](AGENTS.md): các giới hạn mà AI coding agent và nhà thầu phải tuân thủ.
3. Đọc [Antigravity handoff & ready-to-copy prompts](docs/ANTIGRAVITY_HANDOFF.md): cách kết nối GitHub bằng Antigravity chính thức, quy trình giao việc, PR và deployment authorization.
4. Xem [Phase 01 — Foundation](docs/plans/01-foundation.md), [Phase 02 — NAS Guardian](docs/plans/02-nas-guardian.md), [Phase 03 — Media & Downloads](docs/plans/03-media-downloads.md), [Phase 04 — Workspace & Artifacts](docs/plans/04-workspace-artifacts.md), [Phase 05 Draft PR #5](https://github.com/Tb3c123/HomeAgentP/pull/5) và [Operations Runbook](docs/operations/01-runbook-and-rollback.md).
5. Mỗi Phase bắt buộc có Git branch/PR, evidence thực tế và owner review. Merge code không tự cấp quyền triển khai.
6. Chỉ sau khi các Phase đã được kiểm thử, review và hoàn tất Pre-Production Checklist, xin **phê duyệt triển khai NAS riêng** với commands, ports, volumes, secrets, backup và rollback.

**Safety notice:** Chủ NAS đang dùng Antigravity CLI + Remote Control và yêu cầu giữ nguyên container. Docker socket RW/root/port ttyd là rủi ro đã ghi nhận, chưa khắc phục. Việc cài CasaOS do chủ NAS trực tiếp phê duyệt và giao Antigravity thực hiện. Không lưu credentials trong repo.

