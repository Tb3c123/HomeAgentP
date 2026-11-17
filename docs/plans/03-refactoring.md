# Phase 03 — Modular Refactoring Plan & Architecture Map

**Branch:** `feature/phase-03-media-downloads`  
**PR:** [#3 — Phase 03 Media & Downloads](https://github.com/Tb3c123/HomeAgentP/pull/3) (targeting `main`, `OPEN`)  
**Baseline Commit (before R01):** `9e42db940b0df94d3cbb81a66cd473eb8d990682` (synced with `origin/main` at `a2e7ef6`)

---

## 1. Git Ancestry & `origin/main` Synchronization Plan

### Current Git State
- `origin/main` (`a2e7ef6`) now contains **both** merged PR #1 (Phase 01 Foundation) and PR #2 (Phase 02 NAS Guardian).
- `merge-base(origin/main, feature/phase-03-media-downloads)` = `a4e414edd094c016400c0f3cf4a1cb922d0cde18` (`origin/feature/phase-02-nas-guardian`).
- `origin/main` includes two additional hardened Phase 02 commits beyond `a4e414e` (plus merge commits `e9c96ce`, `a2e7ef6`):
  - `b96d1b2` — `feat(nas-guardian): add host_producer CLI, systemd templates, and worker-level timeout overlap guard`
  - `ecd74e0` — `fix(nas-guardian): align host snapshot bind-mount paths, UID 10001 permissions, and bounded scheduler shutdown`
- Diff overlap between `a4e414e..origin/main` and `a4e414e..HEAD` is **only** `config/examples/.env.example` (5 lines added in `origin/main` vs 46 lines in Phase 03).

### Synchronization & Base-Update Plan
1. **No force-push, no history rewrite**: Preserve `feature/phase-03-media-downloads` commit history intact.
2. **Preserve all hardened Phase 02 NAS Guardian fixes**: In particular, `apps/core/src/homeagentp_core/modules/nas/scheduler.py` (`b96d1b2`, `ecd74e0`), `host_producer.py`, `deploy/docker-compose.dev.yml`, `deploy/systemd/*`, and `tests/core/test_nas_guardian.py` must be brought into `feature/phase-03-media-downloads` via a clean `git merge origin/main` (before **R05 — Shared Scheduler**, or as a dedicated sync commit after R01 review) so `R05` builds directly on the hardened `NasCollectionScheduler` (worker-level overlap guard + bounded shutdown).
3. **Update PR #3 base to `main`**: Only execute `gh pr edit 3 --base main` **after** `origin/main` is cleanly merged into `feature/phase-03-media-downloads`, diff against `origin/main` is verified clean (only Phase 03 + shared scheduler extraction), and GitHub Actions CI passes.

---

## 2. R01 Baseline Verification Results (Commit `9e42db9`)

| Check | Command | Result |
|---|---|---|
| Core Pytest | `cd apps/core && .venv/bin/pytest -v` | **PASS** (`37 passed in 12.66s`) |
| Core Ruff | `cd apps/core && .venv/bin/ruff check src ../../tests/core` | **PASS** (`All checks passed!`) |
| Core Mypy | `cd apps/core && .venv/bin/mypy src` | **PASS** (`Success: no issues found in 33 source files`) |
| Web Typecheck | `cd apps/web && npm run typecheck` | **PASS** (`tsc --noEmit` exit `0`) |
| Web Vitest | `cd apps/web && npm test` | **PASS** (`2 passed`) |
| Web Vite Build | `cd apps/web && npm run build` | **PASS** (`vite build` exit `0`, 31 modules) |
| Docker Compose | `docker compose -f deploy/docker-compose.dev.yml up --build` | **`NOT_TESTED`** (no Docker daemon in sandbox) |

---

## 3. Baseline Architecture Map

### 3.1. Backend (`apps/core/src/homeagentp_core/`) & Tests (`tests/core/`)

| File | Lines | Current Responsibilities | Dependencies | Refactor Target |
|---|---|---|---|---|
| `modules/media/__init__.py` | 1 | Empty package marker | — | Keep / optional exports |
| `modules/media/base.py` | 474 | Error hierarchy, URL SSRF validator, semver check, `SafeMediaHttpClient`, `MediaServiceAdapter` ABC | `httpx`, `ipaddress`, `urllib.parse` | **R03**: split into `errors.py`, `security.py`, `http_client.py`, `adapter_base.py` |
| `modules/media/adapters.py` | **1,393** | All 7 adapters (`JellyfinAdapter`, `QBittorrentAdapter`, `_ArrV3BaseAdapter`, `SonarrAdapter`, `RadarrAdapter`, `BazarrAdapter`, `ProwlarrAdapter`, `SeerrAdapter`), JSON helpers, `build_media_adapters` | `base.py`, `config.py`, `httpx` | **R02**: split into per-service modules + `arr_common.py` + `registry.py` |
| `modules/media/collector.py` | **855** | Staleness/age, service state machine (`media_service_states`), alert lifecycle (`media_alerts`), overall status & summary, orchestration (`collect_media_telemetry`, `collect_single_media_service`), SQLite persistence & history | `adapters.py`, `config.py`, `sqlite3` | **R04**: split into `state.py`, `alerts.py`, `persistence.py`, `collector.py` |
| `modules/media/scheduler.py` | 180 | `MediaCollectionScheduler` using `asyncio.wait_for(asyncio.to_thread(...))` (lacks hardened Phase 02 worker-level overlap guard & bounded shutdown) | `collector.py`, `db/connection.py`, `config.py` | **R05**: reuse shared scheduler engine extracted from hardened `NasCollectionScheduler` |
| `modules/media/router.py` | 247 | FastAPI endpoints `/api/v1/media/*` | `collector.py`, `auth`, `db` | Keep (~247 lines, within <=300 target) |
| `modules/nas/scheduler.py` | 170 | `NasCollectionScheduler` (will receive `b96d1b2`/`ecd74e0` hardened worker-level overlap guard & bounded shutdown upon `origin/main` sync) | `collector.py`, `db/connection.py`, `config.py` | **R05**: extract shared base/runner into `modules/shared/scheduler.py` (or `core/scheduler.py`) |
| `tests/core/test_media_downloads.py` | **936** | All Phase 03 unit & integration tests in one file | `media/*`, `main.py`, `httpx.MockTransport` | **R07**: split by service/concern into `tests/core/media/` |

### 3.2. Frontend (`apps/web/src/`)

| File | Lines | Current Responsibilities | Dependencies | Refactor Target |
|---|---|---|---|---|
| `App.tsx` | **1,874** | Auth, navigation shell, Overview, NAS Guardian, **Media & Downloads Hub (~650 lines)**, Home Automation, Tasks, Scripts, Reports, Settings | `api/client.ts`, `api/types.ts`, `StatusBadge.tsx` | **R06**: extract Media Dashboard first (`pages/MediaDashboard.tsx` + subcomponents + hook), then NAS/Tasks/Overview |
| `api/types.ts` | 655 | Shared + NAS + Media TypeScript interfaces | — | **R06**: split domain types (e.g. `api/mediaTypes.ts`, re-exported from `api/types.ts`) |
| `api/client.ts` | 174 | Fetch wrapper + API client methods | `api/types.ts` | Keep (~174 lines) |
| `components/StatusBadge.tsx` | 67 | Status badge component | — | Keep (~67 lines) |
| `__tests__/App.test.tsx` | **902** | Monolithic dashboard UI tests | `App.tsx`, `api/client.ts` | **R06/R07**: modularize media UI tests alongside `App.test.tsx` |

---

## 4. Public Interfaces & Contracts to Preserve

1. **HTTP API Endpoints (must remain 100% backward compatible)**:
   - `GET /api/v1/media/overview`
   - `GET /api/v1/media/services`
   - `GET /api/v1/media/{jellyfin|qbittorrent|sonarr|radarr|bazarr|prowlarr|seerr}`
   - `POST /api/v1/media/collect` (CSRF-protected)
   - `GET /api/v1/media/alerts` (`include_resolved`, `service`, `limit`)
   - `GET /api/v1/media/history` (`limit`)
   - `GET /api/v1/overview` (`domains.media`, `domains.downloads`), `GET /api/v1/settings`, `GET /api/v1/health`
2. **Python Module Contracts (preserve imports via module re-exports where needed)**:
   - `homeagentp_core.modules.media.router.router`
   - `homeagentp_core.modules.media.scheduler.MediaCollectionScheduler`
   - `homeagentp_core.modules.media.collector`: `collect_media_telemetry`, `collect_single_media_service`, `persist_media_snapshot`, `query_media_alerts`, `query_media_history`, `sync_media_alert_lifecycle`, `update_service_state_and_build_alerts`, `compute_overall_media_status`, `build_media_summary`
   - `homeagentp_core.modules.media.adapters`: `JellyfinAdapter`, `QBittorrentAdapter`, `SonarrAdapter`, `RadarrAdapter`, `BazarrAdapter`, `ProwlarrAdapter`, `SeerrAdapter`, `build_media_adapters`
   - `homeagentp_core.modules.media.base`: `MediaServiceAdapter`, `SafeMediaHttpClient`, `validate_service_url`, `check_semver_major`, and all `Media*Error` exception classes
3. **SQLite Schema**: `003_media_downloads.sql` (`media_metric_snapshots`, `media_service_states`, `media_alerts`) — **no breaking schema changes**.
4. **Frontend Contracts**: `apiClient` methods in `apps/web/src/api/client.ts`, exported types in `apps/web/src/api/types.ts`, and `App` component behavior/auth/navigation.

---

## 5. Step-by-Step Refactoring Plan (R01–R07)

- **R01 — Baseline & Architecture Map** *(Current step)*:
  - Verify baseline tests/lint/typecheck/build, inspect `origin/main` ancestry, create `docs/plans/03-refactoring.md`, commit.
- **Sync `origin/main` (between R01 and R02/R05)**:
  - Merge `origin/main` (`a2e7ef6`) into `feature/phase-03-media-downloads` preserving all Phase 02 NAS Guardian fixes (`b96d1b2`, `ecd74e0`) and Phase 03 `.env.example` settings.
- **R02 — Split Media Adapters** *(1 connector per commit)*:
  - Extract `arr_common.py`, `jellyfin.py`, `qbittorrent.py`, `sonarr.py`, `radarr.py`, `bazarr.py`, `prowlarr.py`, `seerr.py`, and `registry.py`; keep `adapters.py` as a slim compatibility re-export or remove after updating callers/tests.
- **R03 — Split HTTP Infrastructure & Security Audit**:
  - Split `base.py` into `errors.py`, `security.py`, `http_client.py`, `adapter_base.py`.
  - Audit endpoint allowlist, SSRF, redirects, DNS/IP policy, secret redaction, timeouts; fix any security findings in a separate commit.
- **R04 — Split Collector**:
  - Split `collector.py` into `state.py`, `alerts.py`, `persistence.py`, and `collector.py` (orchestration + summary).
- **R05 — Shared Scheduler**:
  - Extract hardened single-worker, worker-level overlap guard, timeout, and bounded shutdown from `NasCollectionScheduler` into a shared component; migrate `MediaCollectionScheduler` to it; add regression tests for blocked worker, timeout, shutdown, and restart.
- **R06 — Frontend Decomposition**:
  - Split `App.tsx` (Media Dashboard first, then NAS Guardian, Tasks, Overview) into focused <=250-line components, hooks, and feature types; preserve UI behavior and auth/routing.
- **R07 — Test Decomposition**:
  - Split `tests/core/test_media_downloads.py` into `tests/core/media/test_*.py` by service & concern (`jellyfin`, `qbittorrent`, `arr`, `other_connectors`, `http_security`, `collection_alerts`, `scheduler`, `api_integration`).

---

## 6. Progress & Decisions Log

| Step | Status | Commit SHA | Notes |
|---|---|---|---|
| **R01** | `COMPLETED` | `1d53d18` | Baseline checks all PASS (`37` pytest, `ruff`, `mypy`, `tsc`, `2` vitest, `vite build`). Architecture map & `origin/main` sync plan documented. |
| **Sync `origin/main`** | `COMPLETED` | `1cbccf0` | Merged `origin/main` (`a2e7ef6`) cleanly (`ort`, zero conflicts). Preserved Phase 02 NAS Scheduler (`b96d1b2`, `ecd74e0`) & Host Producer. Updated PR #3 base to `main`. `38` pytest + frontend PASS. |
| **R02.1 (Jellyfin)** | `COMPLETED` | `c895907` | Extracted `JellyfinAdapter` into `modules/media/connectors/jellyfin.py` (275 lines); `adapters.py` reduced `1393 -> 1151` lines with backward-compatible re-export. `39` pytest, `ruff`, `mypy` PASS. |
| **R02.2 (qBittorrent)** | `COMPLETED` | `a1b0f69` | Extracted `QBittorrentAdapter` + `QBITTORRENT_CREDENTIAL_NOTICE` into `connectors/qbittorrent.py` (374 lines). |
| **R02.3 (Arr v3 Base)** | `COMPLETED` | `f28be67` | Extracted shared Sonarr/Radarr v3 base `_ArrV3BaseAdapter` into `connectors/arr_common.py` (275 lines). |
| **R02.4 (Sonarr)** | `COMPLETED` | `c83f2ef` | Extracted `SonarrAdapter` into `connectors/sonarr.py` (48 lines). |
| **R02.5 (Radarr)** | `COMPLETED` | `d8eb58f` | Extracted `RadarrAdapter` into `connectors/radarr.py` (48 lines). |
| **R02.6 (Bazarr & Prowlarr)** | `COMPLETED` | `4ab1974`, `403ea16` | Extracted `BazarrAdapter` (`connectors/bazarr.py`, 154 lines) and `ProwlarrAdapter` (`connectors/prowlarr.py`, 194 lines) in separate commits. |
| **R02.7 (Seerr & Registry)** | `COMPLETED` | `588798e` | Extracted `SeerrAdapter` (`connectors/seerr.py`, 159 lines) and `build_media_adapters` (`connectors/registry.py`, 33 lines); `adapters.py` reduced to `51`-line thin compatibility layer. Full backend & frontend checks PASS. |
| **R03.1 (Base Split)** | `COMPLETED` | `b66ab39` | Split `base.py` (475 lines) into `errors.py` (62), `security.py` (147), `http_client.py` (209), `adapter_base.py` (168); `base.py` reduced to `58`-line compatibility layer. |
| **R03.2 (Security Hardening)** | `COMPLETED` | `a507a89`, `5bfb3df` | Hardened segment-safe path matching, IPv4-mapped IPv6 & DNS resolution SSRF checks, 3xx redirect blocking, early `Content-Length` cap, fail-closed DNS lookup, and single-lookup IP pinning via `SafeDnsPinningBackend` (`test_r03_security_hardening_regressions`, `test_r03_dns_pinning_fail_closed_and_rebinding_protection` PASS). |
| **R04.1 (Media State)** | `COMPLETED` | `909e186` | Extracted service state & failure threshold logic into `media/state.py` (317 lines). |
| **R04.2 (Media Alerts)** | `COMPLETED` | `e9a30ed` | Extracted alert lifecycle & SQLite querying into `media/alerts.py` (154 lines). |
| **R04.3 (Media Persistence)** | `COMPLETED` | `f2a1704` | Extracted SQLite persistence & history into `media/persistence.py` (140 lines); `collector.py` reduced `856 -> 306` lines with compatibility re-exports. |
| **R05 (Shared Scheduler)** | `COMPLETED` | `c0618fe` | Extracted `HardenedPeriodicScheduler` into `homeagentp_core/scheduler.py`; migrated `NasCollectionScheduler` and `MediaCollectionScheduler`; added `test_r05_media_scheduler_hardened_worker_timeout_shutdown_and_restart`. |
| **Gate C Step 1 (HTTP Transport Guard)** | `COMPLETED` | `187a807` | `_build_pinned_transport()` in `media/http_client.py` fails closed with `MediaSecurityError("ssrf_pinning_unavailable")` on incompatible `httpcore.ConnectionPool` internals or failed backend verification; pinned `httpx>=0.27.0,<0.29.0`; added `test_r03_pinned_transport_fails_closed_on_incompatible_internals`. |
| **R06.1 (API Types & Formatters)** | `COMPLETED` | `b2fe520` | Split `apps/web/src/api/types.ts` by domain (`common`, `tasks`, `nas`, `media`, `index`) with compatibility re-export; extracted `src/utils/format.ts`. |
| **R06.2 (Media Cards)** | `COMPLETED` | `f7fa756` | Extracted `MediaOverviewCards`, `MediaFallbackCards`, `JellyfinCard`, `QBittorrentCard`, `ArrSuiteCards`, and `AuxMediaCards` into `src/components/media/`. |
| **R06.3 (Media Dashboard & Alerts)** | `COMPLETED` | `a215e7e` | Extracted `MediaAlertsHistory.tsx` and `MediaDashboard.tsx`; wired into `App.tsx`. |
| **R06.4 (Auth & Data Hooks)** | `COMPLETED` | `d0f5e4c` | Extracted `useAuthSession.ts` and `useDashboardData.ts` into `src/hooks/`. |
| **R06.5 (Page Sections)** | `COMPLETED` | `3f478d0` | Extracted `OverviewSection`, `HomeAutomationSection`, `NasGuardianSection`, `TasksSection`, `ScriptsSection`, `ReportsSection`, and `SettingsSection` into `src/components/sections/`; `App.tsx` reduced `1,875 -> 286` lines. |
| **R06.6 (Media UI Tests)** | `COMPLETED` | `391c123` | Added `src/__tests__/MediaDashboard.test.tsx` covering card rendering, poll snapshot button, busy state, fallback cards, and "Show resolved" toggle (`4` Vitest tests PASS). |
| **R07 (Test Decomposition)** | `COMPLETED` | `d20074f` | Split `tests/core/test_media_downloads.py` (`1,352` lines) into `tests/core/media/` (`conftest.py` + 8 focused test modules); `47` pytest, `ruff`, `mypy` PASS. |
| **R08.1 (Frontend Test Split)** | `COMPLETED` | `bdc0415` | Split `App.test.tsx` (`902` lines) and refactored `MediaDashboard.test.tsx` into 4 feature-scoped test files (`AuthAndNavigation`, `NasGuardianSection`, `TasksAndAdminSections`, `MediaDashboard`) + 5 domain fixture helpers in `src/__tests__/fixtures/`. `9` Vitest tests, `tsc`, `vite build` PASS. |
| **R08.3 (NAS Section Split)** | `COMPLETED` | `01f178e` | Extracted `NasMetricsCards` (136), `NasMountsCard` (46), and `NasContainersAlertsHistory` (144) into `src/components/nas/`; `NasGuardianSection.tsx` reduced `347 -> 69` lines. |
| **R08.2 (Backend Test Split)** | `COMPLETED` | `5d77592`, `298e222` | Extracted media mock transports into `tests/core/media/mocks/` (`conftest.py` `445 -> 69` lines) and split `test_nas_guardian.py` (`1,011` lines) into `tests/core/nas/` (`conftest.py` + 6 focused test modules). `47` pytest, `ruff`, `mypy` PASS. |
| **R08.4 (Architecture Audit)** | `COMPLETED` | — | Verified zero circular imports across `homeagentp_core`, pinned `httpx>=0.27.0,<0.29.0` with fail-closed `SafeDnsPinningBackend`, clean secret scan, and preserved API/SQLite/NAS Guardian contracts. |
| **R08.5 (Docs & PR Sync)** | `COMPLETED` | — | Updated `docs/plans/03-refactoring.md` and PR #3 description with final R01–R08 inventory, verification counts, and rollback notes. |

---

## 7. Final R01–R08 Before/After File-Size Inventory & Verification

| Area | Before (Baseline) | After (R01–R08) |
|---|---|---|
| Media Adapters | `modules/media/adapters.py` (`1,393` lines) | `adapters.py` (`51`-line re-export) + `connectors/{jellyfin,qbittorrent,arr_common,sonarr,radarr,bazarr,prowlarr,seerr,registry}.py` (`33–374` lines each) |
| Media HTTP & Security | `modules/media/base.py` (`474` lines) | `base.py` (`58`-line re-export) + `errors.py` (62), `security.py` (175), `http_client.py` (273), `adapter_base.py` (168) |
| Media Collector & Scheduler | `modules/media/collector.py` (`855` lines), `scheduler.py` (`180`) | `collector.py` (306), `state.py` (317), `alerts.py` (154), `persistence.py` (140), shared `homeagentp_core/scheduler.py` (276) |
| Frontend App & Sections | `apps/web/src/App.tsx` (`1,874` lines), `api/types.ts` (`655`), `NasGuardianSection.tsx` (`347`) | `App.tsx` (`286` lines), `api/types/*` (`22–287`), `hooks/*`, `components/media/*`, `components/nas/*`, `components/sections/*` (`NasGuardianSection.tsx` `69` lines) |
| Backend Tests | `test_media_downloads.py` (`936` -> `1,352` lines), `test_nas_guardian.py` (`1,011` lines) | `tests/core/media/` (`conftest.py` 69 + `mocks/*` + 8 test files), `tests/core/nas/` (`conftest.py` + 6 test files) |
| Frontend Tests | `App.test.tsx` (`902` lines), `MediaDashboard.test.tsx` (`472` lines) | 4 focused test files (`AuthAndNavigation`, `NasGuardianSection`, `TasksAndAdminSections`, `MediaDashboard`) + `src/__tests__/fixtures/*` |

### Final Verification Summary
- **Backend (`apps/core`)**: `.venv/bin/ruff check src ../../tests/core` (**PASS**), `.venv/bin/mypy src` (**PASS**, 52 source files), `.venv/bin/pytest -v` (**PASS**, `47 passed`).
- **Frontend (`apps/web`)**: `npm run typecheck` (**PASS**), `npm test` (**PASS**, 4 files / `9 passed`), `npm run build` (**PASS**).
- **Docker Compose / Live NAS**: **`NOT_TESTED`** (no Docker daemon or production NAS in sandbox).

### Rollback
- PR #3 remains open against `main` (`a2e7ef6`). No NAS or production state was modified.
- To roll back any R08 cleanup commit without touching R01–R07, run `git revert <commit_sha>` on `feature/phase-03-media-downloads`. To discard the entire feature branch, close PR #3 and keep `main` at `a2e7ef6`.


