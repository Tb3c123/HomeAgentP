# HomeAgentP — Scope and architecture baseline

## Goal
Operate a personal home server as a modular, observable, secure home-automation/media/AI workspace platform. **Not just AI software development**.

## Real host facts (observed at a past snapshot, REVALIDATE before deployment)
Debian 12 bookworm; x86_64 Intel N200 (4 logical CPUs); approximately 15 GiB RAM, 187 GiB free SSD (snapshot); Docker Engine 29.9.2, Compose v5.6.1; ext4 HDDs mounted /mnt/disk1, /mnt/disk2. Services reported running: Jellyfin, Sonarr, Radarr, Bazarr, Prowlarr, Seerr, qBittorrent, AdGuard Home, Portainer and an existing Antigravity ttyd container. These are not live measurements. Port 8310 is only a candidate. Do not use this as permission to operate.

## Architecture B+ for MVP
- **HomeAgentP Web**: authenticated Dashboard, NAS/media/download overview, task board, scripts (view only initially), reports, knowledge and artifacts.
- **HomeAgentP Core**: API, persistent SQLite state, policy/approval, telemetry adapters, read-only service health, event scheduler and notifications.
- **Google Antigravity official product**: a user-controlled AI working environment, optionally connected to this GitHub repo using Remote Agents. It does not form a backend of Web/Core; no consumer CLI wrapper.
- **Git and versioned files**: task handoff and artifacts. GitHub PR review before merge.

## Modules (do not omit)
1. NAS Guardian: CPU/RAM/storage/containers/mount integrity, optional SMART with an approved adapter.
2. Media: Jellyfin/Radarr/Sonarr/Bazarr/Prowlarr/Seerr; read-only observations first.
3. Downloads: qBittorrent progress/health, stalled conditions, later policy-based remediation.
4. Home Assistant: read-only events and status first; automation later, carefully authorized.
5. Alerts and Reports: dashboard, incident history, Telegram, scheduled non-AI reports.
6. AI Workspace: task briefs, research notes, knowledge, artifacts, skills metadata, Git handoff.
7. Developer: software project planning, tasks, reviews, repository and build-result links.
8. Security/Recovery: authentication, secrets, minimal privilege, logs, backup/restore drills.

## Release priority
P1 Foundation; P2 NAS Guardian; P3 Media/Downloads; P4 AI Companion/Tasks/Artifacts; P5 Home Assistant/Telegram; P6 Operations/Backups. Each phase requires its own issue/PR and actual tests.

## Preserved constraints
Two-container CasaOS app; default deny, least privilege, no untrusted shell; minimize SSD/IO load and protect existing services. Legacy NEXUS specifications are architecture/planning references and were not executed or verified.

## Out of scope for MVP
Direct AI CLI orchestration; fully autonomous agents via consumer account; production deployment automation; unapproved host operations; uncontrolled scripts; self-improving skills; production write operations on media/HA.
