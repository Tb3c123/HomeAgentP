# Phase 01 — Foundation (first implementation plan)

Status: IMPLEMENTED IN BRANCH (`feature/phase-01-foundation`) / LOCAL UNIT & INTEGRATION TESTS PASSED / CONTAINER RUNTIME `NOT_TESTED` (no Docker daemon in isolated dev VM) / `NOT_DEPLOYED`.

## Goal
Build a small usable HomeAgentP Web + Core using a two-container architecture suitable for Debian/CasaOS.

## Scope
- Source tree: `apps/web`, `apps/core`, `deploy`, `config/examples`, `tests`.
- Web routes/sections: login, overview (placeholder states explicitly report `unavailable`), NAS Guardian, Media & Downloads, Home Automation & Telegram, Projects/Tasks & AI Handoff, Scripts (read-only), Reports & Audit, Settings & Safety.
- Core: health endpoint, auth/session management, SQLite persistence/migrations, task and script metadata APIs, readonly file/manifest viewer with strict path validation.
- Structured logs with secret redaction; configuration validation; minimal example data; Dockerfiles and draft Compose.
- Document localhost setup without touching NAS; port 8310 candidate.

## Non-goals
No real NAS admin integration, Docker socket, root, cron on host, media writes, remote CLI calls, production secrets, arbitrary shell/script execution.

## Implementation tasks
1. [x] Select and document minimal maintained stack and dependency policy (`FastAPI` + `SQLite` for `apps/core`; `React 19` + `TypeScript` + `Vite` for `apps/web`).
2. [x] Define API contracts: `/api/v1/health`, `/api/v1/auth/*`, `/api/v1/overview`, `/api/v1/settings`, `/api/v1/projects`, `/api/v1/tasks`, `/api/v1/scripts`, `/api/v1/reports`, `/api/v1/audit-logs`.
3. [x] Implement database schema and migrations (`001_initial.sql`: `users`, `sessions`, `projects`, `tasks`, `task_attempts`, `script_manifests`, `reports`, `audit_logs`) and online backup helper (`backup_sqlite_database`).
4. [x] Implement responsive Dashboard and error/empty/loading states, never fabricating live data.
5. [x] Create healthcheck-capable non-root images (`apps/core/Dockerfile`, `apps/web/Dockerfile`), restricted filesystem, resource limits and local dev compose (`deploy/docker-compose.dev.yml`) with no privileged mode.
6. [x] Add tests: authorization, CSRF, traversal/symlink denial, SHA-256 verification, database restart persistence, input validation, config mistakes, log redaction (`tests/core/`, `apps/web/src/__tests__/App.test.tsx`); CI workflow (`.github/workflows/ci.yml`).
7. [x] Write startup/shutdown and rollback runbook (`docs/operations/01-runbook-and-rollback.md`); provide sample `.env.example` with placeholders only (`config/examples/.env.example`).

## Acceptance
- [x] Login required for any private data (`test_private_endpoints_require_authentication`).
- [x] One task can be created, edited, listed and persisted after restart in isolated local test (`test_task_lifecycle_and_database_restart_persistence`).
- [x] Script viewer reads only approved directories; cannot write, execute scripts or escape via symlink/path traversal (`test_path_traversal_and_absolute_paths_denied`, `test_symlink_escape_denied`, `test_checksum_tampering_detected`).
- [x] Docker images configured to run unprivileged (`10001:10001` and `101:101`) with no Docker socket and no broad host mounts (container build/runtime marked `NOT_TESTED` in isolated VM without Docker daemon).
- [x] Unit and integration tests have real logs (`14 passed` in `pytest`, `2 passed` in `vitest`, `ruff` and `mypy` clean, `vite build` succeeded).
- [x] README explains how to run in local staging, with no NAS execution assumed.

## Delivery
One feature branch (`feature/phase-01-foundation`), PR with description/tests/risks/rollback. Owner reviews before merge, then separate deployment authorization.
