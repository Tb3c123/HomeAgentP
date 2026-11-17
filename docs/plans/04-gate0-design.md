# Phase 04 — Gate 0 Design: Gap Analysis, Schema/API Proposal & Test Matrix

**Branch:** `feature/phase-04-workspace-artifacts` (based on `main` at `6f13fee7`)  
**Draft PR:** [#4 — Phase 04 Workspace, Task Briefs, Artifacts & Git Handoff](https://github.com/Tb3c123/HomeAgentP/pull/4)  
**Status:** `GATE 0 DESIGN — AWAITING REVIEW (NOT IMPLEMENTED)`

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
   - *Gap:* `tasks.task_brief_md` is a single unversioned markdown string with no structured fields (`purpose`, `scope`, `excluded_scope`, `input_references`, `acceptance_checks`, `security_constraints`, `rollback_plan`, `human_status`), no version history, and no formatted plain-text handoff export for manual copy into the official Google Antigravity app.
2. **P04-F03 — Artifacts & Knowledge Metadata Registry**:
   - *Gap:* `script_manifests` and `reports` only cover scripts/reports, and `task_attempts.artifact_rel_path` is an unindexed string. There is no unified, filterable metadata registry for versioned workspace artifacts, knowledge notes, plans, and runbooks linked to projects/tasks with safe read-only preview.
3. **P04-F04 — Git Links & Provenance**:
   - *Gap:* `tasks.git_branch`, `tasks.pr_url`, and `projects.repo_url` are unvalidated strings. There is no structured provenance record (`repo_url`, `branch`, `commit_sha`, `pr_url`, `review_status`, `ci_status`, `ci_url`) with strict HTTPS GitHub URL validation.
4. **P04-F05 — Modular Workspace UI**:
   - *Gap:* `TasksSection.tsx` lacks a structured Task Brief editor/version viewer + "Copy Handoff Brief" action, an Artifacts & Knowledge browser/previewer, and a Git Provenance panel.

---

## 3. Proposed Additive SQLite Schema (`004_workspace_artifacts.sql`)

All changes are strictly additive; existing `projects`, `tasks`, `task_attempts`, `script_manifests`, and `reports` tables and APIs remain 100% backward compatible.

1. **`task_briefs`**
   - `id` (`INTEGER PRIMARY KEY AUTOINCREMENT`)
   - `task_id` (`INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE`)
   - `version` (`INTEGER NOT NULL`) — monotonic per `task_id` (`UNIQUE(task_id, version)`)
   - `purpose` (`TEXT NOT NULL`)
   - `scope` (`TEXT NOT NULL DEFAULT ''`)
   - `excluded_scope` (`TEXT NOT NULL DEFAULT ''`)
   - `input_references_json` (`TEXT NOT NULL DEFAULT '[]'`) — JSON array of relative paths / doc refs
   - `acceptance_checks_json` (`TEXT NOT NULL DEFAULT '[]'`) — JSON array of checklist strings
   - `security_constraints` (`TEXT NOT NULL DEFAULT ''`)
   - `rollback_plan` (`TEXT NOT NULL DEFAULT ''`)
   - `human_status` (`TEXT NOT NULL DEFAULT 'draft' CHECK (human_status IN ('draft', 'ready_for_handoff', 'handed_off', 'approved', 'archived'))`)
   - `rendered_text` (`TEXT NOT NULL`) — deterministic plain-text brief for manual Antigravity handoff
   - `created_by` (`TEXT NOT NULL`)
   - `created_at` (`TEXT NOT NULL`)
2. **`workspace_artifacts`**
   - `id` (`INTEGER PRIMARY KEY AUTOINCREMENT`)
   - `slug` (`TEXT UNIQUE NOT NULL`)
   - `title` (`TEXT NOT NULL`)
   - `kind` (`TEXT NOT NULL CHECK (kind IN ('artifact', 'knowledge', 'plan', 'runbook'))`)
   - `source_type` (`TEXT NOT NULL CHECK (source_type IN ('allowlisted_report', 'allowlisted_script', 'git_reference', 'note'))`)
   - `rel_path` (`TEXT NOT NULL DEFAULT ''`) — validated relative path inside `reports_dir` or `scripts_dir` when `allowlisted_*`
   - `sha256` (`TEXT NOT NULL DEFAULT ''`)
   - `git_url` (`TEXT NOT NULL DEFAULT ''`) — validated `https://github.com/...` URL when `git_reference`
   - `summary` (`TEXT NOT NULL DEFAULT ''`)
   - `tags_json` (`TEXT NOT NULL DEFAULT '[]'`)
   - `version` (`TEXT NOT NULL DEFAULT '1.0.0'`)
   - `project_id` (`INTEGER REFERENCES projects(id) ON DELETE SET NULL`)
   - `task_id` (`INTEGER REFERENCES tasks(id) ON DELETE SET NULL`)
   - `created_at` (`TEXT NOT NULL`)
   - `updated_at` (`TEXT NOT NULL`)
3. **`git_provenance_links`**
   - `id` (`INTEGER PRIMARY KEY AUTOINCREMENT`)
   - `entity_type` (`TEXT NOT NULL CHECK (entity_type IN ('task', 'artifact'))`)
   - `entity_id` (`INTEGER NOT NULL`)
   - `repo_url` (`TEXT NOT NULL`)
   - `branch` (`TEXT NOT NULL DEFAULT ''`)
   - `commit_sha` (`TEXT NOT NULL DEFAULT ''`)
   - `pr_url` (`TEXT NOT NULL DEFAULT ''`)
   - `review_status` (`TEXT NOT NULL DEFAULT 'none' CHECK (review_status IN ('none', 'pending', 'approved', 'changes_requested'))`)
   - `ci_status` (`TEXT NOT NULL DEFAULT 'unknown' CHECK (ci_status IN ('unknown', 'pending', 'success', 'failure'))`)
   - `ci_url` (`TEXT NOT NULL DEFAULT ''`)
   - `created_at` (`TEXT NOT NULL`)
   - `updated_at` (`TEXT NOT NULL`)

**Rollback:** Additive tables only; rolling back `004_workspace_artifacts.sql` requires no destructive changes to Phase 01–03 tables (`DROP TABLE IF EXISTS git_provenance_links, workspace_artifacts, task_briefs;` only if reverting Phase 04).

---

## 4. Proposed API Surface (`/api/v1/workspace/*`)

All `GET` routes require `get_current_principal`; all `POST`/`PATCH` routes require `require_csrf`, Pydantic input bounds, and `record_audit_log()`.

| Method & Path | Purpose |
|---|---|
| `GET /api/v1/workspace/tasks/{task_id}/briefs` | List all brief versions for a task (newest first). |
| `POST /api/v1/workspace/tasks/{task_id}/briefs` | Create a new versioned brief (`version = max + 1`), generate `rendered_text`. |
| `GET /api/v1/workspace/tasks/{task_id}/briefs/{version}/export` | Return plain-text handoff brief (`text/plain` or JSON `{rendered_text}`) for manual copy into Antigravity. |
| `GET /api/v1/workspace/artifacts` | List/filter artifacts & knowledge (`kind`, `source_type`, `task_id`, `project_id`, `tag`, `q`). |
| `POST /api/v1/workspace/artifacts` | Register artifact/knowledge metadata (validates `rel_path` or `git_url`; rejects secret patterns). |
| `GET /api/v1/workspace/artifacts/{slug}` | Get artifact metadata + read-only file preview (delegates to `read_allowlisted_text_file()` when `allowlisted_*`). |
| `GET /api/v1/workspace/provenance` | List Git provenance links (`entity_type`, `entity_id`). |
| `POST /api/v1/workspace/provenance` | Attach/register validated GitHub HTTPS provenance link. |
| `PATCH /api/v1/workspace/provenance/{id}` | Update `review_status`, `ci_status`, `ci_url`, `commit_sha`, or `pr_url`. |

---

## 5. Modular Architecture & Security Boundaries

### Backend (`apps/core/src/homeagentp_core/modules/workspace/`)
- `schemas.py` (~160 lines): Pydantic models, input length caps, GitHub HTTPS URL validator (`https://github.com/...` only, no userinfo `@`, no `javascript:`/`file:`/`http://`), and secret-pattern rejection (`ghp_`, `github_pat_`, `BEGIN .*PRIVATE KEY`).
- `briefs.py` (~140 lines): Versioned brief persistence + deterministic plain-text Antigravity handoff formatter.
- `artifacts.py` (~160 lines): Artifact/knowledge CRUD, filtering, and read-only preview via `modules/scripts/safe_reader.py` (`reports_dir` / `scripts_dir` only).
- `provenance.py` (~120 lines): Git provenance CRUD and URL/SHA validation.
- `router.py` (~180 lines): FastAPI endpoints mounted in `main.py`.

### Frontend (`apps/web/src/`)
- `api/types/workspace.ts` (~120 lines, re-exported in `api/types/index.ts`)
- `hooks/useWorkspaceData.ts` (~150 lines)
- `components/workspace/`: `TaskBriefPanel.tsx`, `ArtifactsKnowledgePanel.tsx`, `GitProvenancePanel.tsx`, `WorkspaceSection.tsx` (each ~120–220 lines).

### B+ & Security Constraints
- **No Antigravity consumer CLI integration**: HomeAgentP never invokes `agy`, never stores consumer OAuth tokens, and never submits briefs automatically.
- **No GitHub PATs / no server-side URL fetching**: Provenance URLs are validated syntactically and rendered as outbound links in the UI; Core never fetches external GitHub URLs (prevents SSRF).
- **No arbitrary filesystem writes/uploads**: Artifact previews strictly reuse `read_allowlisted_text_file()` against `reports_dir` and `scripts_dir`.

---

## 6. Test Matrix & Gate Execution Plan

| Gate | Scope | Planned Tests |
|---|---|---|
| **Gate A** | `P04-F02` + `P04-F03` | Migration `004` idempotency & restart persistence; brief versioning + plain-text export; artifact registration/filtering + `safe_reader` preview; traversal/symlink/secret-pattern rejection; `401` unauthenticated & `403` missing CSRF. |
| **Gate B** | `P04-F04` + `P04-F05` | Git provenance URL/scheme/userinfo validation; Vitest tests for `TaskBriefPanel` (copy/versioning), `ArtifactsKnowledgePanel` (filter/preview), `GitProvenancePanel`, and navigation/auth regression; full Ruff/Mypy/Pytest/TSC/Vitest/Vite Build + isolated Docker staging. |
