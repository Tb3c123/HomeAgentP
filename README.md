# HomeAgentP

HomeAgentP is a personal AI workspace and home NAS operations platform.

## Architecture: B+ (Antigravity-first, Dashboard-light)

- Official Google Antigravity is used directly by the owner for AI coding, research and generating scripts. HomeAgentP does not wrap or programmatically control consumer Antigravity CLI.
- `homeagentp-web`: NAS dashboard, media/downloads overview, task board, script registry, reports and artifacts.
- `homeagentp-core`: read-only NAS/media monitoring, scheduled rules, alerts and scoped integrations.
- Git and files are the handoff mechanism between AI work and HomeAgentP.

## Development scope

1. Foundation: dashboard, authentication, SQLite metadata, task registry, two-container structure.
2. NAS Guardian: metrics, mount checks, service health, read-only alerts.
3. Media and downloads: Jellyfin, Sonarr, Radarr, Bazarr, Prowlarr, Seerr, qBittorrent.
4. Workspace: scripts, tasks, artifacts, Git handoff and task briefs.
5. Home Assistant, notifications, backup and operations.

## Safety

- No NAS deployment without explicit approval.
- No host root or Docker socket in HomeAgentP containers.
- No credentials or real `.env` in Git.
- No consumer OAuth proxy to Antigravity.
- Verify security and restore before production use.

## Status

Planning and documentation only. No HomeAgentP application has been deployed.
