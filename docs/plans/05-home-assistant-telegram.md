# Phase 05 — Home Assistant, Telegram & Notifications

**Status:** PLANNING ONLY — no Phase 05 implementation, external connections, or NAS deployment  
**Branch:** `feature/phase-05-home-assistant-telegram`  
**Baseline:** Phase 04 merged into `main` at `28c11aab1a65c24db22946d12663cbdae0b602c0`  
**Architecture:** HomeAgentP B+ — human-operated official Antigravity, lightweight Web/Core.

## 1. Purpose and scope

Provide **read-only Home Assistant visibility** and **owner-configured Telegram alert delivery**, backed by local alert history and bounded, policy-driven scheduling. Preserve existing NAS Guardian, Media/Downloads and Workspace features and their security boundaries.

### In scope for Phase 05
- Read-only Home Assistant connection state, selected entity state summaries, explicitly allowlisted event/health data and availability indicators.
- Unified notification rules and local delivery history for already-existing NAS/Media alerts and opted-in Home Assistant observations.
- Telegram **outbound notifications only**, through a dedicated bot token managed as a runtime secret.
- Owner-configurable alert preferences, deduplication, cooldown, per-channel rate limiting, bounded retries and delivery health.
- Feature flags defaulting to **disabled** and honest `unavailable` / `NOT_CONFIGURED` states.
- Isolated test doubles for Home Assistant HTTP/events and Telegram API; optional GitHub-hosted Docker staging with dummy credentials and mock targets.

### Not in scope
- No Home Assistant service calls that change devices, scenes, automations, locks or alarms.
- No Telegram chat-command execution, arbitrary bot command handlers, remote shell, script execution, webhook exposure, or control-plane access.
- No production credentials in Git/CI output, no automatic configuration of user's real Home Assistant/Telegram/NAS, no NAS deployment.
- No unrestricted polling or event subscription with uncontrolled persistence; no uncontrolled network egress, SSRF or metadata access.
- No Antigravity CLI or consumer OAuth integration. No Docker socket, privileged containers, or broad host mounts.

## 2. Gate 0 — mandatory inventory and design

Before implementation, inspect live code for:
1. `apps/core/src/homeagentp_core/modules/nas/` alert lifecycle, persistence, scheduler;
2. `apps/core/src/homeagentp_core/modules/media/` connectors, SSRF protections, alert lifecycle and rate/state handling;
3. `apps/core/src/homeagentp_core/config.py`, `db/migrations/`, `main.py`, audit/auth/CSRF and shared scheduler;
4. Web dashboard/data hooks/sections, existing notification placeholders and API clients;
5. Previous migrations `001`–`004` and protected Docker Compose settings.

Deliver `docs/plans/05-gate0-design.md` with:
- Gap analysis, re-use boundaries, data-flow diagram and threat model.
- Minimal API shapes, SQLite additive migration proposal (`005_*` only if justified), entity allowlist and notification preferences schema.
- Explicit HA auth method/permissions; polling vs events decision, replay/dedup semantics, timeouts, payload-size limits and bounded retention.
- Telegram destination allowlist, secret handling, outbound-only scope, redaction, message formatting and anti-spam policy.
- SSRF and TLS policy for Home Assistant endpoint and Telegram outbound endpoint; protect against DNS rebinding, redirects and redirect-to-metadata.
- Failure/isolation behavior: unreachable HA and Telegram never block NAS/Media collection, website health or SQLite.
- Backpressure, queue size, concurrency/retry/cooldown, idempotency and shutdown/restart behavior.
- Deterministic regression/security test matrix plus Docker staging strategy and rollback.
- Decisions requiring human approval before enabling real-world outbound messages.

**Gate 0 ends with design-only review. Do not implement features until the design is reviewed.**

## 3. Planned implementation packages (not yet authorized)

### P05-F01 — Read-only Home Assistant adapter
Create an opt-in adapter with strictly allowlisted URLs/entities, protected credentials, bounded HTTP responses/timeouts, masked diagnostics, health/status reporting, and simulated event/state tests. Reuse existing safe HTTP patterns where appropriate without weakening SSRF/network policy. Do not call any HA state-changing endpoints.

### P05-F02 — Notification policy and persistence
Add small focused modules to map NAS/Media/HA events to owner-defined alert preferences. Define per-incident keys, deduplication, priority, cooldown, retention, and SQLite delivery status/history. All writes must be local application metadata, not device/system mutations.

### P05-F03 — Telegram outbound sender
Opt-in outbound-only bot notifications, explicit allowlisted destination chat IDs, secure secret injection, bounded message size, sanitized formatting, anti-spam limits, backoff for 429/5xx, and no retry storm. Never accept Telegram inbound commands or open a webhook listener.

### P05-F04 — Shared periodic delivery orchestration
Reuse hardened scheduler patterns, prevent overlapping workers, bound resource usage and shutdown, record delivery states safely. Never obstruct existing NAS/Media polling. Test partial outages and restart safety.

### P05-F05 — Web configuration and alert history
Build focused Home Assistant overview and Notifications components/hooks; distinguish configured, disconnected, stale and unavailable states. Owner-only configuration mutations with CSRF; viewer is read-only. UI must label mock/recorded statuses accurately and never pretend manual/unverified records are live truth.

### P05-F06 — Security, integration & Docker staging
Test HA read-only controls, SSRF/DNS pinning/TLS, Telegram outbound allowlist, secrets/redaction, duplicate suppression, 429 backoff, queue overflow, DB restart, scheduler concurrency, RBAC/CSRF, existing Phase 01–04 contracts, and isolated Docker startup/health. Live HA/Telegram/NAS tests remain `NOT_TESTED` until separately authorized.

## 4. Acceptance criteria

1. Existing NAS Guardian, Media, Workspace and core API behavior remain backward compatible, and all prior regressions PASS.
2. Disabled integrations report clear `unavailable` status, with zero live network attempts when disabled.
3. HA connector never mutates HA state; only approved read-only API endpoints/entities may be queried.
4. Telegram sends only explicitly approved outbound messages to configured destinations, honoring cooldown/rate limits and bounded retries.
5. Secrets never enter repository files, PR comments, rendered UI, logs, alerts or test reports.
6. Credential/URL handling is fail-closed; invalid or private destinations cannot bypass egress policy.
7. Delivery and alert history is bounded and auditable, with restart-safe idempotency.
8. Owner-only configuration writes require authentication, authorization and CSRF; viewer remains read-only.
9. Components remain modular; ~300 Python / ~250 React lines are review heuristics, not reasons for arbitrary splits.
10. Ruff, Mypy, Pytest, TypeScript, Vitest and Vite Build succeed; GitHub Actions Docker staging runs with dummy endpoints when implementation exists.
11. PR documents real evidence and `PASS`/`FAIL`/`NOT_TESTED` accurately, plus rollback and known limitations.
12. No merge, remote HA/Telegram connection, live NAS integration or deployment without explicit owner approval.

## 5. Execution and review gates

- **Gate 0: Design only** — code inventory, policy choices, threats, API/schema proposal, test matrix; stop for human review.
- **Gate A: HA read-only + notifications model** — P05-F01/F02 with isolated tests and small commits, after explicit design approval.
- **Gate B: Telegram sender + scheduling** — P05-F03/F04 with security and reliability tests, after Gate A review.
- **Gate C: UI, integration & isolated staging** — P05-F05/F06, CI and runtime evidence, then final review before merge.

**Current decision:** Initialize this Phase 05 plan as a Draft PR. No implementation or NAS/production interaction is authorized.
