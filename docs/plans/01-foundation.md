# Phase 01 — Foundation (first implementation plan)

Status: PLANNED / NOT_TESTED / NOT_DEPLOYED.

## Goal
Build a small usable HomeAgentP Web + Core using a two-container architecture suitable for Debian/CasaOS.

## Scope
- Source tree: apps/web, apps/core, deploy, config/examples, tests.
- Web routes: login, overview (placeholder states must say unavailable), projects/tasks, scripts/reports.
- Core: health endpoint, auth/session management, SQLite persistence/migrations, task and script metadata APIs, readonly file/manifest viewer with strict path validation.
- Structured logs with secret redaction; configuration validation; minimal example data; Dockerfiles and draft Compose.
- Document localhost setup without touching NAS; port 8310 candidate.

## Non-goals
No real NAS admin integration, Docker socket, root, cron on host, media writes, remote CLI calls, production secrets, arbitrary shell/script execution.

## Implementation tasks
1. Select and document minimal maintained stack and dependency policy; no app is present yet.
2. Define API contracts: /health, /auth, /tasks, /scripts, /reports with schemas and auth.
3. Implement database schema and migrations (projects/tasks/attempts/script manifests/audit). Define safe storage and backup semantics.
4. Implement responsive Dashboard and error/empty/loading states, never fabricate live data.
5. Create healthcheck-capable non-root images, restricted filesystem, resource limits and local dev compose with no privileged mode.
6. Add tests: authorization, traversal/symlink denial, database restart persistence, input validation, config mistakes; CI with lint/typecheck/test.
7. Write startup/shutdown and rollback runbook; provide sample .env with placeholders only.

## Acceptance
- Login required for any private data.
- One task can be created, edited, listed and persisted after restart in isolated local test.
- Script viewer reads only approved directories; cannot write, execute scripts or escape via symlink/path traversal.
- Docker images run unprivileged with no Docker socket and no broad host mounts.
- Unit and integration tests have real logs; failures recorded. Build artifacts reproducible from a pinned commit.
- README explains how to run in local staging, with no NAS execution assumed.

## Delivery
One feature branch, one or more small PRs, description/tests/screenshots if safe/rollback. Owner reviews before merge, then separate deployment authorization.
