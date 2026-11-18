# Phase 06 — Debian 12 NAS staging proposal (review only)

**Status 2026-11-18: PROPOSAL / NOT EXECUTED / NOT APPROVED.** This document is not a runnable deployment playbook. The owner has authorized **read-only NAS inspection only**. Do not start Docker services, bind ports, create volumes, edit firewall/Cloudflare, change ttyd or use Docker socket from HomeAgentP.

## Confirmed owner-provided inventory

- Debian 12 / amd64, kernel 6.1.0-27-amd64; 4 logical CPUs; ~15 GiB RAM (~11 GiB available); system root NVMe ext4 with ~187 GiB available.
- Docker Engine 29.9.2 / Compose v5.6.1.
- 10 already-running containers: antigravity-cli, jellyfin, bazarr, radarr, sonarr, qbittorrent, adguard-home, seerr, prowlarr, portainer. Preserve all of them.
- Media volumes on `/mnt/disk1` and `/mnt/disk2` (ext4), do not read/write content or alter mounts; HomeAgentP read-only telemetry through a separately approved host snapshot mechanism.
- TCP 8310/8311 not observed listening. This is **not** a permanent port reservation, ingress approval, or proof of external accessibility.
- SSH and cloudflared systemd services running. Owner accesses Antigravity CLI remotely and explicitly requires no CLI, cloudflared or ttyd change.
- Existing antigravity-cli ttyd/agy processes run as root, writable Docker socket bind, 7681 on all interfaces; **accepted for continued use by owner, risk NOT remediated**. HomeAgentP must not import those privileges. Portainer has independent admin surface and socket; do not alter it.

## Candidate topology for separate approval

```
Existing NAS: Antigravity CLI (unchanged) -- Git / task briefs / artifacts
                  |
             reviewed handoff files (no automatic CLI control)
                  |
       HomeAgentP Web 127.0.0.1:8310 (proposal only)
                  |
            isolated Compose bridge
                  |
       HomeAgentP Core internal-only (no host published 8311)
                  |
       named Docker volume for SQLite on system SSD
```

- Core: fixed non-root UID/GID `10001:10001`, read-only root filesystem, `cap_drop: [ALL]`, `no-new-privileges`, minimal writable volume `/data`, memory limit 256 MiB, CPU limit 0.75; deploy user/volume ownership to be validated before startup.
- Web: fixed non-root UID/GID `101:101`, read-only root, required tmpfs only, `cap_drop: [ALL]`, `no-new-privileges`; loopback-only publication `127.0.0.1:8310`, memory limit 128 MiB, CPU limit 0.50.
- Pin images by *verified immutable* SHA-256 digest, not draft tags. The current `deploy/casaos-compose.draft.yml` contains unverified draft tags and must **not** be used to launch services.
- Do not grant `privileged`, host PID/network, devices, `/var/run/docker.sock`, `/mnt/disk1`, `/mnt/disk2`, or broad host filesystem mounts.
- Initial flags: HA polling, Telegram delivery and optional outbound integrations disabled; NAS and media collectors only after explicit endpoint/credential/host snapshot approval.
- Access via existing Cloudflare infrastructure is an **unapproved future option**. Do not create routes/tokens or publish 8310 externally without independent TLS/auth/session-cookie review.

## Outstanding evidence before staging authorization

1. Show exact reviewed proposed Compose configuration and immutable image digests, with offline preflight report scoped as `offline_config`; treat unverified image origin as UNKNOWN.
2. Confirm real storage ownership on target SSD-backed Docker volume, UID/GID, SQLite WAL durability and space constraints; verify no unintentional media access.
3. Confirm destination for encrypted off-host backup, retention, rotation, checksums, recovery owner, and desired RPO/RTO; **no backups to be performed yet**.
4. Isolated scratch restore drill and same-image/same-schema rollback compatibility; no restore to production/live SQLite; verify recovered API with no outbound network.
5. Confirm public ingress policy (if any), HTTPS, session cookie mode and local SSH break-glass availability; ensure Web loopback remains reachable through approved method.
6. Audit running services for port conflicts **at deployment time** and record known-good Jellyfin/*arr/qBittorrent/AdGuard/Portainer/CLI baseline before and after.
7. Obtain a new explicit owner approval for exact commands, volume names, images/digests, access, rollback, outage window, and who executes it.

## Planned verification after separate authorization (not run)

- Core/Web health + auth/CSRF and session handling, persistence across controlled restart, host telemetry honesty (UNAVAILABLE when no safe snapshot), media integration disabled-first.
- Backup file integrity and independent scratch restore; collect time-bounded RPO/RTO evidence.
- Validate resource budgets, logging/redaction, ingress loopback, no Docker socket/host mounts and unaffected existing container counts.
- Failure handling: disable HomeAgentP only, preserve all existing services, and use verified compatible backup and image for a future rollback. Never remove/mutate media disks or CLI.

## Gate

**NO-GO for NAS staging until explicit change authorization; NO-GO for production until independent production sign-off.** Phase 06 CI PASS means isolated software verification only, not live acceptance.
