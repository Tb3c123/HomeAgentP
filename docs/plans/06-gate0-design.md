# Phase 06 — Gate 0 Architecture, Threat Model & Verification Design

**Status:** DESIGN / REVIEW REQUIRED — not an implementation acceptance or NAS deployment authorization
**Current `main` baseline:** Phase 05 merged in [PR #5](https://github.com/Tb3c123/HomeAgentP/pull/5) as `311b8b33`.

## 1. Repository inventory: facts versus assumptions

| Area | Existing source | Verified design fact | Still unknown |
|---|---|---|---|
| SQLite | `apps/core/src/homeagentp_core/db/connection.py` | WAL, FK enforcement, `db_session`, atomic backup and restore helpers exist | Live DB directory, owner, disk, contention, recovery window |
| Recovery docs | `docs/operations/01-runbook-and-rollback.md` | Isolated restore example documented | Executed Phase 06 restore drill and production RPO/RTO |
| Staging | `deploy/docker-compose.dev.yml`, `.github/workflows/ci.yml` | Isolated Core/Web CI staging exists; non-root and read-only containers | Reproducible restore failure injection and image release provenance |
| Production proposal | `deploy/casaos-compose.draft.yml` | Uses draft GHCR tags and example mount locations; not a tested release | Actual NAS runtime, ingress, TLS, storage, port availability |
| Integrations | Phases 02–05 modules and configs | Read-only NAS/media/HA telemetry with opt-in Telegram delivery | Real endpoints, access rights, emergency operations |
| Legacy ttyd | `docs/00-project-scope.md`, README | Prior snapshot mentions potentially unsafe ttyd/Docker socket access | Current running state, exposure and remediation |

**Hard rule:** past host snapshots are not current host evidence; never run a production command just to populate this table without separate authorization.

## 2. Critical recovery hazards discovered in existing code

### R01 — Live SQLite restore may be unsafe if DB is open (HIGH)
`restore_sqlite_database()` deletes target `-wal`/`-shm` sidecar files **before** `os.replace(tmp_restore_path, target_db_path)`. If target database is actively used by Core, deleting sidecars can invalidate WAL state, yield inconsistent readers, or lose recent writes. The helper does **not** enforce quiescence, process-exclusion or exclusive maintenance lock.

**Gate A acceptance:** choose an explicit *offline restore* contract (stopped service, backup of prior DB/WAL/SHM, no active connections) or implement robust fail-closed exclusive restore protections with tests. Never run restore in production until the contract is checked. A scratch-path restore remains allowed and safe for isolated tests.

### R02 — Atomic rename does not guarantee durable directory entry (MEDIUM)
`backup_sqlite_database()` and `restore_sqlite_database()` call `_fsync_file_and_parent(tmp_*)` **before** `os.replace`, without an explicit post-rename parent directory fsync. Crash/power-loss durability of published filename is therefore not established by current code alone.

**Gate A acceptance:** tests and implementation review for directory fsync after publication where supported; handle unsupported/filesystem errors explicitly. Do not overclaim power-loss durability based on SQLite integrity checks alone.

### R03 — Symlink/path ownership and overwrite boundaries (HIGH)
The helper calls `target_backup_path.parent.mkdir(...)` and `os.replace(..., target)` without a proven allowlist/root ownership policy. This may be valid for trusted operator-only local APIs but must **never** be exposed to arbitrary UI-requested paths or untrusted inputs.

**Gate A acceptance:** allowlisted deployment backup roots and owner-only offline operator flow; test symlink/path traversal and unwritable destination; no direct exposed write API in MVP.

### R04 — Image provenance and rollback with additive migrations (HIGH)
The CasaOS spec contains `ghcr.io/tb3c123/homeagentp-*:0.1.0-draft`, not verified images. Reverting application code while leaving upgraded DB schema may work for additive tables but is **not** a proven tested rollback, especially with active notification outbox data.

**Gate C acceptance:** record reviewed commit, build proof, digest, stopped-DB snapshot and explicit versioned compatibility test.

### R05 — Alert delivery during recovery (MEDIUM)
Phase 05 Telegram is **at-least-once**. Retries after uncertain acceptance may duplicate messages. During disaster recovery do not silently enable Telegram or duplicate outbox workers.

## 3. Proposed interfaces and isolation

1. **No new database mutation endpoint** for Phase 06. Prefer CLI/operator-runbook functions invoked solely in isolated staging or separately authorized maintenance; never from public dashboard.
2. Test existing `backup_sqlite_database`, `restore_sqlite_database`, `verify_sqlite_integrity` with temporary paths; ensure DB source content and sidecars are untouched during *scratch* restore.
3. A report-only preflight may return a typed structure `{check_id, status: PASS|FAIL|UNKNOWN|NOT_TESTED, observed_at, evidence_ref, remediation}`. Never accept shell expressions or arbitrary commands.
4. A preflight report must not imply host access if generated in GitHub Actions. Use explicit `evidence_scope: isolated_ci | staging_host | live_host`.
5. Feature flag and secrets checks must examine configuration presence and validation only, **never** print values or add telemetry that leaks credentials.
6. Keep security boundaries: no docker.sock, privileged mode, root, host network or broad NAS mounts. Never change existing media/HA APIs just for operational convenience.

## 4. Test matrix / development gates

| Stage | Test case | Expected |
|---|---|---|
| A | SQLite WAL concurrent backup and independent scratch restore | Source DB unaffected; restored data consistent; integrity/FK checks pass |
| A | Source missing; invalid backup; integrity/FK failure | Fail closed, do not overwrite prior valid backup |
| A | Overwrite target backup with injected failure before publish | Existing backup survives; temporary files cleaned |
| A | Post-rename directory fsync support/failure | Explicit durable outcome or clearly documented non-guarantee |
| A | Source DB open during restore to same path | Fail closed in operator workflow; never remove active WAL/SHM |
| A | Permission denial, symlink path, invalid backup destination | No unauthorized filesystem modification |
| B | Preflight missing env, draft image tags, unsafe mounts, root, host network | Deterministic FAIL/UNKNOWN without secrets |
| B | Preflight no Docker/host access | Honest NOT_TESTED (not fabricated PASS) |
| C | GitHub Actions isolated Compose startup, restart/persistence, scratch restore and API smoke | PASS evidence on PR HEAD |
| C | Disabled HA/Telegram with dummy env, outbound network mocked | No live outbound requests |
| C | Phase 01–05 regressions + static checks | PASS |
| Final | NAS host inventory, ports, TLS, ttyd, mounts, recovery rehearsal | **NOT_TESTED** pending separate explicit permission |

## 5. Phase 06 workflow

- Gate 0: review this design and the [Phase 06 plan](06-operations-recovery.md) before source implementation.
- Gate A: narrowly scoped backup/restore hardening and isolated tests; separate change for offline restore protection.
- Gate B: non-mutating preflight + typed evidence report.
- Gate C: Docker fault-injection staging, operator runbook, final review.
- After merge: request a **separate** deployment authorization with exact verified host facts, command plan, rollback, downtime and tested backup. This PR alone cannot grant it.

**Merge decision:** Phase 06 Draft PR stays open pending Gate 0 review. No production access or deployment authorized.
