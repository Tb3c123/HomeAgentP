# Phase 06 — Pre-production Acceptance & Recovery Evidence Matrix

**Document status:** Template / NOT_TESTED on live NAS. Not an authorization or executable deployment procedure.
**Baseline:** Phase 05 merged at `311b8b33`.

Use `PASS` only with a dated observation and reproducible command/test evidence; `UNKNOWN` is not `PASS`.

| Gate | Required evidence | Current | Stop condition |
|---|---|---|---|
| Host inventory | Live OS, CPU/arch, Docker/Compose, NAS OS, date/time | NOT_TESTED | Any mismatch with deployment plan |
| Existing services | Exact port ownership, Docker networks, storage mounts, processes and service health | NOT_TESTED | Any change to running Jellyfin/*arr/qBittorrent/AdGuard |
| Storage boundary | Canonical mount paths, FS types, read-only bind allowlist, UID/GID and free space | NOT_TESTED | Root/host disk broad mount or unmounted HDD |
| Secrets | Runtime secret source, permissions, non-placeholder values, no logs or git leaks | NOT_TESTED | Secrets in repo/PR/CI or public exposure |
| Network/TLS | Approved ingress, reverse proxy, HTTPS, secure cookies, no unintended egress | NOT_TESTED | Unapproved publicly accessible port |
| Images | Built from reviewed commit, digest pinning, container user/caps/rootfs, provenance | NOT_TESTED | Unverified draft image tag |
| SQLite backup | Online backup, integrity/FK checks, backup checksum and protected destination | NOT_TESTED on NAS | Backup overwritten or cannot verify |
| SQLite restore | Restore **to independent scratch path** and API smoke without touching source DB | NOT_TESTED on NAS | Restore into production by mistake |
| App health | Core/Web health, reboot/restart, auth/CSRF, NAS/media status honesty | NOT_TESTED on NAS | False healthy or unverified host telemetry |
| Phase 05 integrations | HA/Telegram disabled-first; live outbound only after opt-in and separate approval | NOT_TESTED live | Accidental message or device command |
| Rollback | Known-good image, compatible DB snapshot, maintenance window and restore owner | NOT_TESTED | No safe rollback or migration incompatibility |
| Legacy ttyd | Port 7681 exposure, root/docker.sock implications assessed and remediated by host owner | NOT_TESTED current | Unmitigated high-risk access |
| Final signoff | Separate explicit owner-approved deployment plan with ports, mounts, secrets and rollback | NOT APPROVED | No written approval |

## Independent isolated checks already available

- Phase 05 final PR head `2637633`: [Core/Web/Docker GitHub Actions PASS](https://github.com/Tb3c123/HomeAgentP/actions/runs/44228050097), **isolated without NAS**.
- The application already contains `backup_sqlite_database`, `restore_sqlite_database`, `verify_sqlite_integrity` in `apps/core/src/homeagentp_core/db/connection.py`.
- Those facts do **not** establish Phase 06 restore-drill PASS, live backup success, image publish success or NAS deployment readiness.

## Deployment gate

1. Finish Phase 06 design, scoped tests and isolated staging.
2. Review and merge Phase 06 PR separately.
3. Obtain a fresh approved, non-secret host inventory.
4. Prepare a specific deployment proposal with exact proposed mounts/ports/image digests, backup snapshots and rollback verification.
5. **Only after separate explicit approval** may anyone run commands against the NAS. Never execute automatically from CI or Antigravity.
