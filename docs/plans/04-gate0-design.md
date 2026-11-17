# Phase 04 — Gate 0 Design: Gap Analysis, Schema/API Proposal & Test Matrix

**Branch:** `feature/phase-04-workspace-artifacts` (based on `main` at `6f13fee7`)  
**Draft PR:** [#4 — Phase 04 Workspace, Task Briefs, Artifacts & Git Handoff](https://github.com/Tb3c123/HomeAgentP/pull/4)  
**Status:** `GATE A COMPLETE (P04-F02 + P04-F03) — READY FOR GATE B (P04-F04 + P04-F05)`

---

## 1. Existing Phase 01–03 Inventory (Reuse Without Re-Implementing)

| Area | Existing Implementation | What It Already Provides |
|---|---|---|
| **Projects & Tasks** | `apps/core/src/homeagentp_core/modules/tasks/{router.py,schemas.py}`, `001_initial.sql` | `projects` (`GET/POST /api/v1/projects`), `tasks` (`GET/POST/PATCH /api/v1/tasks` with flat `task_brief_md`, `git_branch`, `pr_url`), `task_attempts` (`POST /api/v1/tasks/{id}/attempts` with `executor_type`, `artifact_rel_path`). |
| **Scripts & Safe Reader** | `modules/scripts/{router.py,safe_reader.py}` | `script_manifests` table, `GET /api/v1/scripts`, `GET /api/v1/scripts/{slug}`, `GET /api/v1/scripts/preview-file`, and `read_allowlisted_text_file()` (traversal, symlink, hardlink, size-cap, SHA-256 verification). |
| **Reports & Audit Logs** | `modules/reports/router.py`, `auth/security.py` | `reports` table, `GET /api/v1/reports`, `GET /api/v1/reports/{slug}`, `GET /api/v1/audit-logs`, `record_audit_log()`, `redact_text()`. |
| **Auth & Migrations** | `auth/security.py`, `db/migrations/{001,002,003}_*.sql` | Session cookie auth (`get_current_principal`), CSRF (`require_csrf`), atomic SQLite migrations with checksum tracking. |
| **Frontend UI** | `apps/web/src/components/sections/{TasksSection.tsx,AdminSections.tsx}`, `hooks/useDashboardData.ts` | Task creation/status board, Script viewer, Report viewer, Overview/NAS Guardian/Media Dashboard tabs. |

---

## 2. Gap Analysis (P04-F01..F05)

1. **P04-F02 — Structured, Versioned Task Briefs & Manual Handoff**:
   - *Gap:* `tasks.task_brief_md` is a single unversioned markdown string with no structured fields (`purpose`, `scope`, `excluded_scope`, `input_references`, `acceptance_checks`, `security_constraints`, `rollback_plan`, `human_status`), no immutable version history, and no deterministic plain-text handoff export for manual copy into the official Google Antigravity app.
2. **P04-F03 — Artifacts & Knowledge Metadata Registry**:
   - *Gap:* `script_manifests` and `reports` only cover scripts/reports, and `task_attempts.artifact_rel_path` is an unindexed string. There is no unified, filterable metadata registry for versioned workspace artifacts, knowledge notes, plans, and runbooks linked to projects/tasks with immutable historical revisions, SHA-256 verification, and safe read-only preview.
3. **P04-F04 — Git Links & Provenance**:
   - *Gap:* `tasks.git_branch`, `tasks.pr_url`, and `projects.repo_url` are unvalidated strings. There is no structured provenance record (`repo_url`, `branch`, `commit_sha`, `pr_url`, `review_status`, `ci_status`, `ci_url`, `verification_source`) with strict HTTPS GitHub URL validation and referential cleanup.
4. **P04-F05 — Modular Workspace UI**:
   - *Gap:* `TasksSection.tsx` lacks a structured Task Brief editor/version viewer + "Copy Handoff Brief" action, an Artifacts & Knowledge browser/previewer, and a Git Provenance panel.

---

## 3. Finalized Gate 0 Architectural Decisions

### 3.1. Explicit Role-Based Authorization (RBAC)
- Authentication (`get_current_principal`) and CSRF (`require_csrf`) alone are **insufficient** for write operations.
- **Policy:**
  - `owner` role: full read and write (`GET`, `POST`, `PATCH`) on `/api/v1/workspace/*` (with valid session + CSRF on mutations).
  - `viewer` role: strictly **read-only** (`GET` allowed; any `POST`/`PATCH`/`DELETE` returns `403 Forbidden` with `"Owner role required for workspace modifications."`, even when a valid CSRF token is supplied).
- Implemented via a dedicated `require_workspace_owner` dependency in `modules/workspace/security.py`.

### 3.2. Atomic Task Brief Version Allocation & Immutability
- **Immutability:** Historical `task_briefs` rows are **immutable**. There is no `PATCH`/`PUT` endpoint to mutate an existing `(task_id, version)` row; any edit creates a new version.
- **Atomic Allocation & Conflict Handling:**
  - `POST /api/v1/workspace/tasks/{task_id}/briefs` accepts an optional `expected_latest_version: int | None` (optimistic concurrency control).
  - Inside `BEGIN IMMEDIATE` (acquiring SQLite's reserved write lock before reading `MAX(version)`):
    1. Verify `task_id` exists (`404 Not Found` if missing).
    2. Read `current_max = COALESCE(MAX(version), 0)`.
    3. If `expected_latest_version is not None` and `expected_latest_version != current_max`, roll back and return `409 Conflict`.
    4. Allocate `next_version = current_max + 1` and insert the new row; if a race still triggers `sqlite3.IntegrityError` on `UNIQUE(task_id, version)`, map to `409 Conflict`.
- **Backward Compatibility:** Existing `tasks.task_brief_md` and `/api/v1/tasks*` contracts remain untouched and functional.

### 3.3. Artifact Identity, Immutable Revisions & SHA-256 Verification
- **Logical Identity + Immutable Revisions:** Each `slug` identifies a logical artifact/knowledge entry, while each revision is stored as an immutable row keyed by `(slug, revision)` (`UNIQUE(slug, revision)` and `UNIQUE(slug, version)`).
- **Lifecycle:**
  - Creating a new artifact with an unused `slug` starts at `revision = 1`.
  - Registering a new version for an existing `slug` (via `POST /api/v1/workspace/artifacts` with `expected_latest_revision` or `POST /api/v1/workspace/artifacts/{slug}/revisions`) atomically allocates `revision = MAX(revision) + 1` inside `BEGIN IMMEDIATE` (`409 Conflict` on stale `expected_latest_revision` or duplicate `(slug, version)`).
  - Historical revisions are never overwritten or deleted in place.
  - `GET /api/v1/workspace/artifacts` returns the **latest** revision per `slug` by default (with `?include_history=true` optional); `GET /api/v1/workspace/artifacts/{slug}` returns the latest revision (or `?revision=<n>` / `?version=<v>`), and `GET /api/v1/workspace/artifacts/{slug}/versions` lists all historical revisions.
- **SHA-256 Verification:**
  - For `source_type` in `('allowlisted_report', 'allowlisted_script')`, `read_allowlisted_text_file()` is executed at registration time (against `settings.reports_dir` or `settings.scripts_dir`, optionally verifying caller-supplied `expected_sha256`) to compute and store the canonical `sha256`.
  - Every subsequent `GET /api/v1/workspace/artifacts/{slug}` preview passes `expected_sha256=row["sha256"]` to `read_allowlisted_text_file()`, failing closed with `403 Forbidden` if the file was tampered with, symlinked, or exceeded size limits.

### 3.4. Secret Handling, Content Limits & Redacted Errors
- **Multi-Layer Secret Detection:** Beyond simple prefix regexes (`ghp_`, `github_pat_`, `glpat-`, `sk-`, `AKIA...`, `BEGIN .*PRIVATE KEY`), `modules/workspace/security.py` checks:
  - Authorization headers (`Bearer <token>`, `Basic <b64>`).
  - Credential assignments (`password|passwd|secret|api_key|apikey|token|access_token|private_key` followed by `:` or `=` and a non-placeholder value of length >= 8).
  - URL embedded userinfo (`https://user:pass@...`).
- **Safe Logging & Redacted Errors:**
  - All rejected inputs raise `400 Bad Request` / `422 Unprocessable Entity` with a **sanitized, generic message** naming only the field (e.g., `"Field 'purpose' contains a disallowed secret or credential pattern."`) — **never** echoing the offending secret value.
  - All audit logs pass through `record_audit_log()` + `redact_structure()`.
- **Content Limits:** Strict Pydantic bounds on all text/list fields (`title <= 200`, `purpose <= 2000`, `scope/excluded_scope/security_constraints/rollback_plan <= 4000`, `summary <= 2000`, `input_references <= 20` items, `acceptance_checks <= 30` items, `tags <= 16` items, `rendered_text <= 24000`), and `safe_reader.py` enforces `MAX_VIEWABLE_BYTES` (`256 KiB`) for file previews.

### 3.5. Git Provenance Referential Integrity & Verification Semantics (Gate B Scope)
- **Referential Integrity & Deletion Behavior:**
  - `git_provenance_links` references either `tasks(id)` (`entity_type = 'task'`) or `workspace_artifacts(id)` (`entity_type = 'artifact'`).
  - On creation, backend verifies the target entity exists (`404 Not Found` if missing).
  - Migration `004` installs SQLite `AFTER DELETE` triggers on `tasks` and `workspace_artifacts` (`trg_cleanup_provenance_on_task_delete`, `trg_cleanup_provenance_on_artifact_delete`) so deleting a task or artifact automatically removes orphaned provenance links.
- **Manual vs. Externally Verified Status:**
  - `git_provenance_links` includes `verification_source TEXT NOT NULL DEFAULT 'manual_unverified' CHECK (verification_source IN ('manual_unverified', 'external_ci_verified'))`.
  - Phase 04 MVP only records `manual_unverified` (since Core never stores GitHub PATs or makes outbound GitHub API requests), ensuring the UI and API never misrepresent manually entered `review_status` or `ci_status` as externally verified.

---

## 4. Proposed Additive SQLite Schema (`004_workspace_artifacts.sql`)

All changes are strictly additive; existing `projects`, `tasks`, `task_attempts`, `script_manifests`, and `reports` tables and APIs remain 100% backward compatible.

1. **`task_briefs`**
   - `id`, `task_id` (FK `tasks(id)` ON DELETE CASCADE), `version` (`INTEGER NOT NULL`), `purpose`, `scope`, `excluded_scope`, `input_references_json`, `acceptance_checks_json`, `security_constraints`, `rollback_plan`, `human_status` (`draft` | `ready_for_handoff` | `handed_off` | `approved` | `archived`), `rendered_text`, `created_by`, `created_at`, `UNIQUE(task_id, version)`.
2. **`workspace_artifacts`**
   - `id`, `slug`, `revision` (`INTEGER NOT NULL`), `version` (`TEXT NOT NULL`), `title`, `kind` (`artifact` | `knowledge` | `plan` | `runbook`), `source_type` (`allowlisted_report` | `allowlisted_script` | `git_reference` | `note`), `rel_path`, `sha256`, `git_url`, `summary`, `tags_json`, `project_id` (FK `projects(id)` ON DELETE SET NULL), `task_id` (FK `tasks(id)` ON DELETE SET NULL), `created_by`, `created_at`, `UNIQUE(slug, revision)`, `UNIQUE(slug, version)`.
3. **`git_provenance_links`** + `AFTER DELETE` cleanup triggers
   - `id`, `entity_type` (`task` | `artifact`), `entity_id`, `repo_url`, `branch`, `commit_sha`, `pr_url`, `review_status` (`none` | `pending` | `approved` | `changes_requested`), `ci_status` (`unknown` | `pending` | `success` | `failure`), `ci_url`, `verification_source` (`manual_unverified` | `external_ci_verified`), `created_at`, `updated_at`.

**Rollback:** Additive tables/triggers only; rolling back `004_workspace_artifacts.sql` leaves Phase 01–03 tables untouched.

---

## 5. Proposed API Surface (`/api/v1/workspace/*`)

| Method & Path | Auth / Role | Purpose |
|---|---|---|
| `GET /api/v1/workspace/tasks/{task_id}/briefs` | `owner` or `viewer` | List all immutable brief versions for a task (newest first). |
| `POST /api/v1/workspace/tasks/{task_id}/briefs` | `owner` + CSRF | Atomically allocate next version (`expected_latest_version` supported) and generate `rendered_text`. |
| `GET /api/v1/workspace/tasks/{task_id}/briefs/{version}/export` | `owner` or `viewer` | Return deterministic plain-text handoff brief for manual copy into Antigravity. |
| `GET /api/v1/workspace/artifacts` | `owner` or `viewer` | List/filter artifacts & knowledge (`kind`, `source_type`, `task_id`, `project_id`, `tag`, `q`, `include_history`). |
| `POST /api/v1/workspace/artifacts` | `owner` + CSRF | Register new artifact or new immutable revision (`expected_latest_revision` supported, SHA-256 verified for allowlisted files). |
| `GET /api/v1/workspace/artifacts/{slug}` | `owner` or `viewer` | Get latest (or `?revision=` / `?version=`) metadata + read-only file preview via `read_allowlisted_text_file()`. |
| `GET /api/v1/workspace/artifacts/{slug}/versions` | `owner` or `viewer` | List all historical revisions for an artifact `slug`. |
| `GET /api/v1/workspace/provenance` *(Gate B)* | `owner` or `viewer` | List Git provenance links (`entity_type`, `entity_id`). |
| `POST /api/v1/workspace/provenance` *(Gate B)* | `owner` + CSRF | Attach validated GitHub HTTPS provenance link (`verification_source = 'manual_unverified'`). |
| `PATCH /api/v1/workspace/provenance/{id}` *(Gate B)* | `owner` + CSRF | Update `review_status`, `ci_status`, `ci_url`, `commit_sha`, or `pr_url`. |

---

## 6. Modular Architecture

- **Backend (`apps/core/src/homeagentp_core/modules/workspace/`)**:
  - `schemas.py` — Pydantic models, length caps, slug/version/GitHub URL validation.
  - `security.py` — `require_workspace_owner` RBAC dependency, multi-layer secret detection, redacted error helpers.
  - `briefs.py` — Atomic versioned Task Brief persistence + deterministic Antigravity handoff formatter (`P04-F02`).
  - `artifacts.py` — Immutable artifact/knowledge revision registry + `safe_reader.py` preview (`P04-F03`).
  - `provenance.py` *(Gate B)* — Git provenance CRUD + entity existence checks (`P04-F04`).
  - `router.py` — FastAPI `/api/v1/workspace/*` router mounted in `main.py`.
- **Frontend (`apps/web/src/`) *(Gate B)***:
  - `api/types/workspace.ts`, `hooks/useWorkspaceData.ts`, `components/workspace/{TaskBriefPanel,ArtifactsKnowledgePanel,GitProvenancePanel,WorkspaceSection}.tsx`.

---

## 7. Test Matrix & Regression Requirements

| Gate | Scope | Planned Tests |
|---|---|---|
| **Gate A** | `P04-F02` + `P04-F03` | Migration `004` idempotency & SQLite restart persistence; owner vs. viewer RBAC (`403` on viewer writes even with CSRF); `401` unauthenticated & `403` missing CSRF; atomic brief version allocation + `expected_latest_version` `409` conflict + concurrent thread race test; immutable historical brief & artifact revisions; deterministic plain-text export; `tasks.task_brief_md` backward compatibility; artifact traversal/symlink/oversized/SHA-256 mismatch rejection; secret-pattern + credential-assignment rejection with redacted error responses. |
| **Gate B** | `P04-F04` + `P04-F05` | Git provenance URL/scheme/userinfo validation; entity existence (`404`) & `AFTER DELETE` trigger cleanup; `verification_source='manual_unverified'` enforcement; Vitest tests for `TaskBriefPanel`, `ArtifactsKnowledgePanel`, `GitProvenancePanel`, and navigation/auth regression; full CI + isolated Docker staging. |

