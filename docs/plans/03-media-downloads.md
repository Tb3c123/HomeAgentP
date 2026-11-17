# Phase 03 — Media & Downloads Integration (Read-Only Monitoring Hub)

Status: IMPLEMENTED & TESTED (`feature/phase-03-media-downloads`) / BASED ON HARDENED PHASE 02 (`a4e414edd094c016400c0f3cf4a1cb922d0cde18`, PR #2) / CONTAINER RUNTIME `NOT_TESTED` / `NOT_DEPLOYED`.


## 1. Architecture Overview

Phase 03 extends the two-container HomeAgentP B+ platform (`homeagentp-core` + `homeagentp-web`) with a unified, read-only **Media & Downloads Monitoring Hub**.

- **`homeagentp-core`**:
  - Implements a uniform `MediaServiceAdapter` abstraction (`apps/core/src/homeagentp_core/modules/media/base.py`) backed by an SSRF-hardened, size-bounded, read-only HTTP client (`SafeMediaHttpClient`).
  - Provides seven independent service connectors (`apps/core/src/homeagentp_core/modules/media/adapters.py`): **Jellyfin**, **qBittorrent**, **Sonarr**, **Radarr**, **Bazarr**, **Prowlarr**, and **Seerr** (Jellyseerr/Overseerr).
  - Isolates adapter failures so a timeout, authentication error, malformed payload, or offline state in one service never blocks or crashes other adapters or `homeagentp-core`.
  - Runs a non-overlapping background scheduler (`MediaCollectionScheduler`, configurable `60–120s`, default `90s`) with per-cycle timeouts and SQLite write-throttling.
  - Persists compact metric snapshots, per-service consecutive failure counters (`media_service_states`), and stateful alerts (`media_alerts` with `active`/`resolved` lifecycle and deduplication) via migration `003_media_downloads.sql`.
- **`homeagentp-web`**:
  - Renders a responsive Media & Downloads Monitoring Hub displaying:
    1. Media & Downloads Overview (service status matrix, scheduler state, read-only & SSRF boundary indicators)
    2. Jellyfin (Server version/latency, Library counts, Active Sessions, Direct Play / Direct Stream / Transcode breakdown, playback error counts)
    3. qBittorrent (Connection status, Download/Upload speeds, torrent state counts, stalled queue, download/disk errors, client-enforced read-only notice)
    4. Sonarr & Radarr (Version, Series/Movie counts, Queue status, Missing episodes/movies, Import/Download failures, Disk space, Health warnings)
    5. Bazarr, Prowlarr & Seerr (Missing subtitles & subtitle provider health; Indexer status & health warnings; Media request counts & recent pending/approved requests)
    6. Unified Media Alerts (`active` / `resolved` filter, occurrences, first/last seen timestamps)
    7. Recent Collection History
- **B+ Boundaries Preserved**:
  - Official Google Antigravity is used exclusively by the human owner for development; HomeAgentP never wraps or invokes consumer Antigravity CLI.
  - No third container added; no `/var/run/docker.sock`, no `privileged: true`, no host root, and no NAS media filesystem mounts (`/mnt/disk1`, `/mnt/disk2`) inside `homeagentp-core` or `homeagentp-web`.

---

## 2. Integrations & Official API Endpoints

All connectors default to **disabled (`status="unavailable"`)** until explicitly configured via environment variables.

| Service | API Version | Authentication | Allowed Read-Only Endpoints | Prohibited Actions (Never Called) |
| :--- | :--- | :--- | :--- | :--- |
| **Jellyfin** | Official REST v10.8+ | `Authorization: MediaBrowser Token="<key>"` & `X-Emby-Token` | `GET /System/Info`, `GET /Items/Counts`, `GET /Sessions`, `GET /System/ActivityLog/Entries?limit=25` | Stopping sessions, library scans, deleting items, modifying server/user config |
| **qBittorrent** | Web API v2 (`v2.8+`) | `POST /api/v2/auth/login` (`SID` cookie) | `GET /api/v2/app/version`, `GET /api/v2/app/webapiVersion`, `GET /api/v2/transfer/info`, `GET /api/v2/torrents/info` | Adding/deleting torrents or files, pause/resume, force start, recheck, changing preferences |
| **Sonarr** | API v3 (`v3+`) | `X-Api-Key` header | `GET /api/v3/system/status`, `GET /api/v3/health`, `GET /api/v3/series`, `GET /api/v3/queue`, `GET /api/v3/wanted/missing`, `GET /api/v3/diskspace` | Adding/deleting series, triggering searches, manual import, changing quality profiles |
| **Radarr** | API v3 (`v3+`) | `X-Api-Key` header | `GET /api/v3/system/status`, `GET /api/v3/health`, `GET /api/v3/movie`, `GET /api/v3/queue`, `GET /api/v3/wanted/missing`, `GET /api/v3/diskspace` | Adding/deleting movies, triggering searches, manual import, changing quality profiles |
| **Bazarr** | Official `/api/` (`v1.2+`) | `X-API-KEY` header | `GET /api/system/status`, `GET /api/system/health`, `GET /api/badges` | Downloading/deleting subtitles, modifying providers or languages |
| **Prowlarr** | API v1 (`v1+`) | `X-Api-Key` header | `GET /api/v1/system/status`, `GET /api/v1/health`, `GET /api/v1/indexer`, `GET /api/v1/indexerstatus` | Adding/editing/deleting indexers, running indexer tests or searches |
| **Seerr** (Jellyseerr / Overseerr) | API v1 (`v1+`) | `X-Api-Key` header | `GET /api/v1/status`, `GET /api/v1/request/count`, `GET /api/v1/request` | Creating, approving, declining, or deleting media requests |

> **Important Note on qBittorrent Credentials**: qBittorrent Web API does not provide a native read-only user role; an authenticated `SID` session has write permissions on the qBittorrent server. Therefore, HomeAgentP never claims the qBittorrent credential itself is read-only. Instead, `QBittorrentAdapter` enforces a strict client-side endpoint and HTTP method allowlist (`GET` only on the four query endpoints above after `/api/v2/auth/login`) and isolates network access.

---

## 3. Unified Media Monitoring API Contracts

All endpoints require an authenticated session (`get_current_principal`). State-changing collection triggers (`POST /api/v1/media/collect`) additionally require a valid `X-CSRF-Token`.

| Method & Path | Description | Key Response Fields |
| :--- | :--- | :--- |
| `GET /api/v1/media/overview` | Unified overview across all 7 services, scheduler status, active alerts, and safety guarantees | `status`, `adapter_enabled`, `collected_at`, `scheduler`, `summary`, `services`, `alerts`, `safety` |
| `GET /api/v1/media/services` | Compact status list/map for all 7 connectors | `collected_at`, `services` (`jellyfin`, `qbittorrent`, `sonarr`, `radarr`, `bazarr`, `prowlarr`, `seerr`) |
| `GET /api/v1/media/jellyfin` | Detailed Jellyfin server, library, active sessions, transcode & playback error telemetry | `service`, `enabled`, `status`, `latency_ms`, `version`, `collected_at`, `metrics`, `alerts` |
| `GET /api/v1/media/qbittorrent` | Detailed qBittorrent transfer speeds, torrent counts by state, stalled queue & error telemetry | `service`, `enabled`, `status`, `latency_ms`, `version`, `collected_at`, `metrics`, `alerts` |
| `GET /api/v1/media/sonarr` | Detailed Sonarr v3 series, episode, queue, missing content, disk space & health telemetry | `service`, `enabled`, `status`, `latency_ms`, `version`, `collected_at`, `metrics`, `alerts` |
| `GET /api/v1/media/radarr` | Detailed Radarr v3 movie, queue, missing content, disk space & health telemetry | `service`, `enabled`, `status`, `latency_ms`, `version`, `collected_at`, `metrics`, `alerts` |
| `GET /api/v1/media/bazarr` | Detailed Bazarr missing episode/movie subtitles, provider status & health issues | `service`, `enabled`, `status`, `latency_ms`, `version`, `collected_at`, `metrics`, `alerts` |
| `GET /api/v1/media/prowlarr` | Detailed Prowlarr v1 indexer counts, failing/disabled indexers & health warnings | `service`, `enabled`, `status`, `latency_ms`, `version`, `collected_at`, `metrics`, `alerts` |
| `GET /api/v1/media/seerr` | Detailed Seerr v1 request counts (`pending`, `approved`, `processing`, `available`, `declined`) & recent requests | `service`, `enabled`, `status`, `latency_ms`, `version`, `collected_at`, `metrics`, `alerts` |
| `GET /api/v1/media/alerts` | Persisted media & download alerts (`?include_resolved=true\|false&limit=50`) | List of `MediaAlertItem` (`id`, `alert_key`, `code`, `severity`, `service`, `target`, `message`, `status`, `first_seen_at`, `last_seen_at`, `resolved_at`, `occurrences`) |
| `GET /api/v1/media/history` | Recent persisted media metric snapshots (`?limit=20`) | List of `MediaHistoryItem` (`id`, `collected_at`, `overall_status`, `jellyfin_active_streams`, `qb_dl_speed_bytes`, `qb_stalled_count`, etc.) |
| `POST /api/v1/media/collect` | Trigger an immediate read-only collection cycle and persist to SQLite | `snapshot_id` + full `MediaOverviewResponse` |

---

## 4. Configuration Guide

Add the following optional variables in `.env` (never commit real secrets or `.env` to Git):

```dotenv
# Enable Phase 03 Media & Downloads read-only monitoring hub
HOMEAGENTP_MEDIA_ADAPTER_ENABLED=false
HOMEAGENTP_MEDIA_SCHEDULER_ENABLED=false
HOMEAGENTP_MEDIA_COLLECTION_INTERVAL_SECONDS=90
HOMEAGENTP_MEDIA_COLLECTION_TIMEOUT_SECONDS=15.0
HOMEAGENTP_MEDIA_HTTP_TIMEOUT_SECONDS=5.0
HOMEAGENTP_MEDIA_MAX_RESPONSE_BYTES=2097152
HOMEAGENTP_MEDIA_MIN_PERSIST_INTERVAL_SECONDS=30
HOMEAGENTP_MEDIA_HISTORY_RETENTION_LIMIT=120
HOMEAGENTP_MEDIA_SNAPSHOT_STALE_SECONDS=300
HOMEAGENTP_MEDIA_FAILURE_THRESHOLD=3

# SSRF Allowlist: hostnames or IP literals allowed for media service URLs
HOMEAGENTP_MEDIA_ALLOWED_HOSTS=["127.0.0.1","localhost","jellyfin","qbittorrent","sonarr","radarr","bazarr","prowlarr","seerr","jellyseerr","overseerr"]

# Individual Service Endpoints & Scoped Credentials (leave empty to keep disabled)
HOMEAGENTP_JELLYFIN_URL=
HOMEAGENTP_JELLYFIN_API_KEY=

HOMEAGENTP_QBITTORRENT_URL=
HOMEAGENTP_QBITTORRENT_USERNAME=
HOMEAGENTP_QBITTORRENT_PASSWORD=
HOMEAGENTP_QBITTORRENT_STALLED_THRESHOLD_SECONDS=1800

HOMEAGENTP_SONARR_URL=
HOMEAGENTP_SONARR_API_KEY=

HOMEAGENTP_RADARR_URL=
HOMEAGENTP_RADARR_API_KEY=

HOMEAGENTP_BAZARR_URL=
HOMEAGENTP_BAZARR_API_KEY=

HOMEAGENTP_PROWLARR_URL=
HOMEAGENTP_PROWLARR_API_KEY=

HOMEAGENTP_SEERR_URL=
HOMEAGENTP_SEERR_API_KEY=
```

---

## 5. Security Boundaries & Threat Model

1. **SSRF & Redirect Protection (`validate_service_url` & `SafeMediaHttpClient`)**:
   - Only `http://` and `https://` URLs with a hostname explicitly present in `HOMEAGENTP_MEDIA_ALLOWED_HOSTS` are permitted.
   - Rejects URLs containing embedded `username:password@` userinfo, cloud metadata endpoints (`169.254.169.254`), unspecified addresses (`0.0.0.0`), multicast, or arbitrary internet domains.
   - Disables HTTP redirects (`follow_redirects=False`) so a compromised or misconfigured internal service cannot redirect `homeagentp-core` to an unapproved internal or external target.
2. **Response Size & Timeout Caps**:
   - Every HTTP request enforces `media_http_timeout_seconds` (default `5.0s`) and streams responses with a strict byte ceiling (`media_max_response_bytes`, default `2 MiB`) to prevent memory exhaustion.
3. **Strict Read-Only Enforcement**:
   - All media connectors execute `GET` requests only (except qBittorrent's single allowlisted `POST /api/v2/auth/login` session handshake). Any attempt to call a non-allowlisted method or path raises `MediaSecurityError`.
   - Neither `homeagentp-core` nor `homeagentp-web` mounts `/mnt/disk1` or `/mnt/disk2` media directories or crawls media files.
4. **Secret Redaction**:
   - `config.py` (`redacted_summary()`) and `logging.py` (`SecretRedactingFilter`) redact `jellyfin_api_key`, `qbittorrent_password`, `sonarr_api_key`, `radarr_api_key`, `bazarr_api_key`, `prowlarr_api_key`, `seerr_api_key`, `X-Api-Key`, `X-Emby-Token`, `Authorization`, and `SID` cookies.
5. **Consecutive Failure Threshold (Anti-Flapping)**:
   - A single transient timeout or connection error records a degraded poll in `media_service_states` (`consecutive_failures = 1`) without immediately firing a critical `service.offline` alert. Only when `consecutive_failures >= HOMEAGENTP_MEDIA_FAILURE_THRESHOLD` (default `3`) does `service.offline` activate, and a single healthy poll immediately resets `consecutive_failures = 0` and resolves the alert.

---

## 6. Testing Strategy

Automated tests in `tests/core/test_media_downloads.py` and `apps/web/src/__tests__/App.test.tsx` use mocked HTTP transports (`httpx.MockTransport` and `vi.spyOn(globalThis, "fetch")`) and never touch real NAS services or credentials:
- Valid API responses for Jellyfin, qBittorrent, Sonarr, Radarr, Bazarr, Prowlarr, and Seerr.
- Authentication failures (`401 Unauthorized` / `403 Forbidden` / qBittorrent `"Fails."`).
- Network timeouts and connection failures.
- Malformed JSON and oversized HTTP payloads (`> media_max_response_bytes`).
- API version incompatibility (e.g., unsupported major version or unexpected schema).
- Missing fields / partial responses.
- Disabled connectors (`status="unavailable"`, never fabricated as live).
- Stale cached snapshot detection (`age_seconds > media_snapshot_stale_seconds`).
- Multiple simultaneous service failures (fault isolation).
- Consecutive failure threshold (`1..N` failures) and alert activation -> deduplication -> resolution lifecycle.
- Polling scheduler concurrency (`asyncio.Lock` overlap prevention, timeout handling) and SQLite persistence/retention pruning.
- SSRF host allowlist, redirect blocking, and qBittorrent write-endpoint denial.

---

## 7. Acceptance Criteria

- [x] `MediaServiceAdapter` interface and all 7 read-only connectors implemented using official API paths.
- [x] SSRF allowlist, redirect blocking, response size cap, and secret redaction enforced and tested.
- [x] Unified `/api/v1/media/*` endpoints authenticated, schema-validated, and timestamped.
- [x] `003_media_downloads.sql` migration, consecutive failure tracking, alert deduplication/resolution, and non-overlapping `MediaCollectionScheduler` implemented.
- [x] Responsive Media & Downloads Dashboard UI implemented without fabricating live data when connectors are disabled.
- [x] Ruff, Mypy, Pytest, TypeScript (`tsc --noEmit`), Vitest, and Vite build pass with actual evidence.

---

## 8. Deployment Requirements, Troubleshooting & Rollback

### Deployment Requirements (Not Executed in Phase 03)
- Do **not** deploy to the production NAS without completing the Pre-Production Mandatory Checklist in `docs/plans/02-nas-guardian.md` (Docker Compose staging verification, stopped-DB restore drill, and locking down the legacy root + RW Docker Socket `ttyd` container on port `7681`).
- Generate dedicated, minimal-privilege API keys for each service before enabling `HOMEAGENTP_MEDIA_ADAPTER_ENABLED=true`.

### Troubleshooting
- **Service shows `unavailable`**: Verify `HOMEAGENTP_MEDIA_ADAPTER_ENABLED=true` and both `HOMEAGENTP_<SERVICE>_URL` and `HOMEAGENTP_<SERVICE>_API_KEY` (or qBittorrent username/password) are set.
- **Service shows `ssrf_blocked`**: Add the service's container hostname or LAN IP to `HOMEAGENTP_MEDIA_ALLOWED_HOSTS`.
- **Service shows `auth_error`**: Rotate and verify the service API key or qBittorrent credentials; check that no reverse proxy is stripping `X-Api-Key` or `Authorization`.
- **Service shows `stale`**: Check `/api/v1/media/overview` -> `scheduler.last_error` and verify upstream service responsiveness within `HOMEAGENTP_MEDIA_HTTP_TIMEOUT_SECONDS`.

### Rollback Procedure
1. **Configuration-only rollback (instant, zero data loss)**:
   Set `HOMEAGENTP_MEDIA_ADAPTER_ENABLED=false` and `HOMEAGENTP_MEDIA_SCHEDULER_ENABLED=false` in `.env` and restart `homeagentp-core`. All media connectors immediately return passive `unavailable` status with zero outbound HTTP calls.
2. **Code & Database rollback**:
   Stop `homeagentp-core`, restore the pre-Phase-03 SQLite backup verified via `restore_sqlite_database()`, and check out the Phase 02 commit (`a4e414edd094c016400c0f3cf4a1cb922d0cde18`).
