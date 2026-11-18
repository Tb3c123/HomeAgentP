# Phase 06 — Operations, Backup, Recovery & Deployment Readiness

**Status:** GATE 0 PLANNING ONLY — no Phase 06 runtime implementation or live NAS changes
**Branch:** `feature/phase-06-operations-recovery`
**Baseline:** Phase 05 [PR #5](https://github.com/Tb3c123/HomeAgentP/pull/5) merged into `main` at `311b8b330ecdb3f03bb67e9b6a700c83063e0885`
**Architecture:** B+ — official Google Antigravity is human-operated; HomeAgentP Core/Web remains least-privilege.

## 1. Goal and safety boundary

Make HomeAgentP operationally maintainable and **ready for an explicitly approved production rollout**, without touching the NAS during development. Phase 06 covers reproducible SQLite backup/restore drills, non-destructive preflight, secure configuration handoff, failure-recovery evidence, and operator runbooks. Completing Phase 06 **does not authorize production deployment**.

**Never** run live NAS commands, deploy CasaOS Compose, connect real HA/Telegram, change NAS mounts, expose services, open network ports or install systemd units as a side-effect of this PR. The historical host profile in `docs/00-project-scope.md` is *not* fresh evidence.

## 2. Existing foundation / reuse (verified in repository)

- `apps/core/src/homeagentp_core/db/connection.py`: `backup_sqlite_database()`, `restore_sqlite_database()`, `verify_sqlite_integrity()`, WAL database and checksum-based migrations. Do not create competing backup implementations.
- `docs/operations/01-runbook-and-rollback.md`: local startup, atomic online backup and isolated restore examples, NAS host snapshot security, troubleshooting and rollback notes. Its Phase 01 wording and historical status must be reconciled without erasing engineering detail.
- `deploy/docker-compose.dev.yml`: **local/GitHub staging only**; non-root Core/Web, read-only rootfs, dropped caps, localhost-bound web, no Docker socket/broad HDD mounts.
- `deploy/casaos-compose.draft.yml`: **DRAFT ONLY**, image tags `0.1.0-draft` not a verified release artifact; must not be presented as ready to deploy.
- `.github/workflows/ci.yml`: isolated Docker startup and authenticated smoke tests; not a replacement for a live-host acceptance test.
- Phase 02 snapshots, Phase 03 read-only media connectors, Phase 04 Workspace, Phase 05 HA/Telegram opt-in integrations: preserve their security boundaries and honest unavailable/stale states.

## 3. Work packages / execution gates

### P06-F01 — Gate 0 system inventory, operational threat model, deployment contract
Deliver `docs/plans/06-gate0-design.md` by reviewing live repository paths and planned host inputs. Record production bind mounts, owners/permissions, network/TLS and reverse proxy, secrets origin, feature flags, health/readiness endpoints, backup boundaries and dependency risks. Separate *observed repository evidence* from *future host evidence* and `UNKNOWN` fields. No real credentials or server identifiers in commits.

Decide whether release is a pinned digest/image build from trusted workflow and whether CasaOS is needed versus ordinary Docker Compose on ZimaOS; inspect actual host before choosing. Document rollback compatibility when a new additive migration has already run. Gate 0 approval precedes implementation that changes runtime behavior.

### P06-F02 — SQLite backup/restore test hardening
Reuse the existing SQLite helpers; introduce isolated test cases for WAL+concurrent readers, backup integrity, FK integrity, atomic replacement failure, backup checksum, restore into a **new temporary path**, schema migration compatibility (001–006) and post-restore functional API smoke. Tests must not overwrite the source DB or run against NAS volumes. Avoid dangerous `docker compose down -v` in operating instructions.

### P06-F03 — Non-mutating operational preflight
Design and (after review) implement a **report-only** `preflight`/validator for Compose configuration, non-root users, read-only rootfs, mounts/ports, resources, prerequisites, required env variable presence (never values), health routes and disk capacity. It must never execute shell actions, start containers, change permissions, enable integrations or print secrets. Container/image checks should be based on config and staging evidence; host data remains `NOT_TESTED` until explicitly allowed.

### P06-F04 — Isolated recovery and fault-injection tests
Extend existing GitHub Actions Docker staging with separate, clean tests of container restart persistence and SQLite backup/restore into scratch volumes/paths, application recovery, disabled HA/Telegram behavior, missing/unreachable optional service handling and no unintended outgoing traffic. Keep real NAS/media/HA/Telegram credentials absent. Collect short bounded logs with redaction; artifact retention must not leak secrets. Distinguish true executed PASS from simulated-only or skipped checks.

### P06-F05 — Operator runbook & production deployment review packet
Create `docs/operations/06-production-readiness.md` including a reproducible, *non-executable-by-default* checklist covering:
- Host facts revalidation and storage mount integrity; **never** infer real disk paths from old memory.
- Verify SSD and HDD capacity and backup destination independent of the live DB filesystem; no backup overwrite without retention and restore proof.
- Docker Engine/Compose, architecture, UID/GID, bind mounts and directory permissions; preserve NAS service availability.
- TLS/HTTPS, secure cookies, reverse proxy trust, localhost ingress and remote access policy, network isolation, DNS and no broad egress.
- Strong secrets from a local secret store or protected environment, HA least-privilege token, Telegram allowlisted chat ID; no user-supplied secrets in PR/issues/CI.
- Existing ttyd/Antigravity container exposure, `/var/run/docker.sock`, root privileges and port 7681 review **before** any deployment; do not operate that container from this PR.
- Offline/stopped-DB restore drill, expected data loss window, rollback image + DB consistency, health and post-rollback observation.
- Separate go/no-go signoff, maintenance window, planned ports/volumes/image digests, recovery owner and evidence bundle.
- Phase 05 at-least-once Telegram duplicate-delivery possibility; integrations remain disabled until explicitly enabled.

### P06-F06 — Review and final isolated acceptance
Ruff, Mypy, Pytest, TypeScript, Vitest, Vite build and independent GitHub Actions Docker staging PASS at the PR head. Conduct scoped security review for restore path traversal, atomicity, secret/log leakage and config drift. Report `PASS/FAIL/NOT_TESTED/BLOCKED` truthfully; mark live NAS, HA, Telegram and hardware validation `NOT_TESTED`.

## 4. Acceptance criteria

1. No production NAS interaction, infrastructure mutation or deployment during Phase 06 PR development.
2. No duplicate backup engine: tested existing APIs + bounded restore drill and proof.
3. Database upgrades/rollback documented with an honest schema compatibility strategy and point-in-time consistency.
4. Preflight is read-only/report-only, fails closed on unknown ports/mounts/permissions and never logs secrets.
5. Containerized staging verifies Core/Web health, persistence and restore into scratch storage without `down -v` or live NAS access.
6. Existing Phase 01–05 modules and public API endpoints stay compatible; CI remains green.
7. Final production packet lists exact *to-be-verified* host inventory, rollback and separate explicit owner signoff.
8. Human reviews architecture Gate 0, tests and PR before merge. Code merge is **not** deployment permission.

## 5. Gate 0 questions requiring explicit answers

- Is the actual production host currently Debian/CasaOS, Debian/ZimaOS, or another distribution? Inspect afresh, do not assume.
- Where will durable SQLite and read-only reports/scripts live, and who owns each path?
- What network ingress, TLS termination and approved port will be used?
- Where will encrypted/offsite backups live, how long retained, and what RPO/RTO are required?
- Are HA and Telegram real integrations to remain disabled at the first production start?
- What exact reversible recovery procedure will protect current Jellyfin/*arr/qBittorrent/AdGuard and HDD mounts?

**Current decision:** Only planning and repository-level review are authorized. Implementation waits for Gate 0 design review. Merge and NAS deployment require distinct, explicit approvals.
