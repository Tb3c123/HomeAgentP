# Phase 05 Security, Threat Notes, Operational Notes & Rollback

## 1. Threat Model & Implemented Controls

### Home Assistant (Read-Only Telemetry)
- **Threat**: SSRF against cloud metadata (`169.254.169.254`), loopback/unexpected LAN hosts, DNS rebinding, or unallowlisted state mutations.
- **Mitigations**:
  - Opt-in only (`HOMEAGENTP_HA_ENABLED=false` by default).
  - Strict `GET` requests only (`/api/` and `/api/states/{entity_id}`), no `POST /api/services/*`.
  - Host allowlist (`HOMEAGENTP_HA_ALLOWED_HOSTS`), `follow_redirects=False` (3xx rejected), and [`SafeDnsPinningBackend`](file:///home/antigravity/Tb3c123/HomeAgentP/apps/core/src/homeagentp_core/net/safe_http.py) blocking unspecified, multicast, link-local/metadata, and IPv4-mapped IPv6 bypasses.
  - Strict entity allowlist (`<= 25` entities), response byte cap (`524_288` bytes), and payload minimization before SQLite persistence.
  - Failed collection marks persisted entity states `unavailable` so historical `online` state is never presented as current truth.

### Telegram Notifications (Outbound-Only)
- **Threat**: Token/URL leakage in logs/SQLite/UI, SSRF/DNS rebinding on egress, inbound command injection, silent critical alert loss, or SQLite lock contention during HTTP I/O.
- **Mitigations**:
  - Opt-in only (`HOMEAGENTP_TELEGRAM_ENABLED=false`, `HOMEAGENTP_NOTIFICATION_SCHEDULER_ENABLED=false` by default).
  - Outbound `POST https://api.telegram.org/bot<token>/sendMessage` only (no `getUpdates`, no webhooks).
  - Public-IP-only DNS pinning (`require_public_ip=True`) + `follow_redirects=False`.
  - Single-destination MVP enforced in `Settings` and `TelegramOutboundSender`; `chat_id` masked (`***1234`) in all persisted history and API responses.
  - `redact_text()` scrubs `bot<id>:<token>` and Bot API URLs from all logs, exceptions, and `last_error_redacted`.
  - Short committed SQLite transactions: `evaluate/enqueue`, `claim`, `complete/fail`, and `prune` commit and close before any outbound HTTP request.
  - Critical alerts bypass per-window non-critical rate limits; non-critical alerts defer with bounded `next_attempt_at` without busy retry loops.

### Authorization & CSRF
- `GET` endpoints require authenticated `owner` or `viewer` session.
- `POST /api/v1/home-assistant/collect`, `PUT /api/v1/notifications/preferences`, and `POST /api/v1/notifications/evaluate` require `owner` role (`403` for `viewer`) and valid `X-CSRF-Token`.

## 2. Operational Notes & Live Testing Status
- **Live Home Assistant**: `NOT_TESTED` (all tests use `httpx.MockTransport` and dummy credentials).
- **Live Telegram Bot API**: `NOT_TESTED` (all tests use `httpx.MockTransport` and fake tokens).
- **Live NAS**: `NOT_TESTED`.

## 3. Rollback Procedure
1. **Immediate Runtime Disable (No Schema Change Required)**:
   - Set `HOMEAGENTP_HA_ENABLED=false`, `HOMEAGENTP_HA_SCHEDULER_ENABLED=false`, `HOMEAGENTP_TELEGRAM_ENABLED=false`, and `HOMEAGENTP_NOTIFICATION_SCHEDULER_ENABLED=false` in `.env` and restart `homeagentp-core`.
2. **Code / Database Rollback**:
   - Migrations `005_home_assistant_telegram.sql` and `006_phase05_hardening.sql` are strictly additive and backward-compatible with Phase 01–04 tables.
   - If full code rollback to `main` is required, restore the pre-upgrade SQLite backup created via `backup_sqlite_database()` before redeploying the previous image.
