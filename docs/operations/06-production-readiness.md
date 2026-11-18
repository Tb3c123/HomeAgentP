# Phase 06 — Safe Operations Runbook & Deployment Review Packet

**Status:** DEVELOPMENT/STAGING PROCEDURE ONLY. Live NAS, HA and Telegram are `NOT_TESTED`.
**No deployment approval is provided by this document.** Never paste these commands into the NAS without a separately reviewed plan.

## 1. Backup and restore boundary

- `backup_sqlite_database(source, target)` makes a verified online SQLite backup, publishes it via atomic rename and syncs the destination directory after publication.
- `restore_sqlite_database(backup, target)` **only restores into a newly created target path**. It refuses any existing SQLite DB, `-wal`, `-shm` or target symlink. This is intentional: replacing an existing WAL database during active operation is unsafe.
- Do not delete WAL/SHM sidecars of a live database. Do not run `rm`, `cp` or an in-place restore against an open production SQLite file.
- These functions do not constitute a complete offline production cutover. A production cutover needs a stopped service, verified recovery snapshot, ownership/permissions, checked backup RPO/RTO, rollback image, and a separate explicit authorization.

## 2. Isolated scratch-drill example (on a development workstation, not the NAS)

These Python commands act only on a database **already created in a temporary development directory**. Check the paths before use.

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from homeagentp_core.db.connection import (
    backup_sqlite_database,
    restore_sqlite_database,
    verify_sqlite_integrity,
)

with TemporaryDirectory(prefix="homeagentp-phase06-") as workspace:
    root = Path(workspace)
    source = root / "source.db"
    # Initialize and populate source using isolated application test fixtures first.
    # Do not substitute /data/homeagentp.db or any mounted NAS DB here.
    # backup_sqlite_database(source, root / "backup.db")
    # restore_sqlite_database(root / "backup.db", root / "scratch-restored.db")
    # verify_sqlite_integrity(root / "scratch-restored.db")
```

The active end-to-end drill is in `tests/core/test_phase06_recovery.py` and the isolated GitHub Actions Docker staging `Phase 06 isolated SQLite backup and scratch restore drill` step. The staging drill refuses in-place overwrite of its *running* test DB.

## 3. Offline Compose preflight

The only available preflight accepts a user-supplied **already decoded Compose JSON**. It never invokes Docker or starts services:

```bash
python -m homeagentp_core.operations.preflight /path/to/isolated-compose-config.json
```

The path is an input file prepared and approved outside the checker. **Do not pass your live production environment file to CI.** Preflight output never includes raw Compose values, secret values, mount paths, images or URLs. It verifies existence of two required service definitions, non-root UIDs, read-only roots, no privileged/host networking, capability drops, security options, safe mount policies, localhost ingress, and digest-pinned images.

A passing **offline configuration** result is not proof of the state of live containers. Some dev/staging configurations intentionally use local image builds; in that case the image provenance result is `UNKNOWN`, not production-ready.

## 4. Explicit deployment gate (not executed)

Record and independently confirm each item in [the readiness matrix](06-preproduction-checklist.md) before proposing deployment:

1. Fresh current host inventory: Debian/ZimaOS/CasaOS, Docker/Compose, port ownership, DNS/TLS, actual service health.
2. Actual HDD mount UUIDs, FS state, snapshot report paths, and CPU/RAM/SSD capacity. Do not trust old example mount paths.
3. Docker image origin, immutable digest, user/caps, environment, read-only bind mounts, resource limits, and no `docker.sock`.
4. Secret store, authentication/HTTPS, network and firewall policy; do not commit or paste credentials.
5. Readiness and recovery plan for Jellyfin/*arr/qBittorrent/AdGuard and existing ttyd access (especially port 7681).
6. Backup retention, encrypted backup destination, isolated restored copy, RPO/RTO, and a named rollback operator.
7. Initial deployment disables HA/Telegram and all optional outbound integrations; enabling real notifications requires explicit opt-in.
8. Separate dated written approval for exact commands, image digests, ports, mounts, downtime and rollback.

**Unresolved host details:** NAS distribution/current runtime, storage locations, backup destination and retention, allowed HTTPS ingress and port, current ttyd hardening, RPO/RTO. Until evidence exists: `NO-GO` for production.
