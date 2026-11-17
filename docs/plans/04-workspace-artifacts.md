# Phase 04 — Workspace, Task Briefs, Artifacts & Git Handoff

**Status:** PLANNING / NOT IMPLEMENTED  
**Branch:** `feature/phase-04-workspace-artifacts` (based on merged Phase 03 `main`, `6f13fee7`)  
**Architecture:** HomeAgentP B+ (Antigravity-first, Dashboard-light)

## 1. Goals and non-goals

Create a practical owner-controlled workspace for organizing AI/developer tasks, handoff briefs, read-only versioned artifacts, reviewed script metadata, and repository/PR references. Preserve NAS Guardian and Media & Downloads as first-class dashboard modules.

- The human uses the **official Google Antigravity application** directly; HomeAgentP only prepares task briefs and stores metadata/links.
- **No** direct invocation, API proxying, token extraction, automated execution, or scraping of Antigravity consumer clients.
- **No** code execution, shell, sudo, GitHub credential storage, direct repository writes by HomeAgentP, or production NAS mutations.
- **No** unrestricted mounts, Docker socket, broad access to NAS disks, or secret values in task briefs/artifacts.

## 2. Existing foundation to reuse

- Phase 01: authenticated sessions, CSRF, SQLite migrations, projects/tasks/task attempts, read-only script registry and reports.
- Phase 02: hardened NAS Guardian and shared scheduler.
- Phase 03: modular media connectors, read-only dashboard, isolation/security tests, isolated GitHub Actions Docker staging.
- Study `AGENTS.md`, `docs/00-project-scope.md`, `docs/ANTIGRAVITY_HANDOFF.md`, and existing routes/schemas before proposing changes. **Do not duplicate existing CRUD or artifact viewers**.

## 3. Work packages — one concern/commit

### P04-F01 — Architecture, schema and threat model
Inventory existing project/task/script/report APIs and frontend components; define the minimal missing fields and optional additive migration (`004_workspace_artifacts.sql` only if justified). Specify size/extension/path restrictions, access control and retention. Deliver design and acceptance tests before implementation.

### P04-F02 — Task Brief templates & human handoff
Provide versioned, editable task brief metadata bound to an existing task/project. Brief fields: purpose, scope, excluded scope, input references, acceptance checks, security constraints, rollback, and human status. Implement copy/export of a **text brief** for manual use in Antigravity; never submit it to the Antigravity app automatically. Test authentication, CSRF, versioning, input limits and JSON compatibility.

### P04-F03 — Artifacts & knowledge metadata (read-only content)
Allow users to register/list/filter/inspect versioned artifact and knowledge metadata, with relative allowlisted paths or explicitly provided Git links. If content preview is needed, reuse hardened existing read-only file viewing with no symlink/path traversal. No arbitrary uploads or unrestricted filesystem writes in the MVP without a new approval decision. Guard against HTML/script injection, traversal, oversized content, and secret exposure.

### P04-F04 — Git links and provenance
Associate optional validated GitHub HTTPS links (repository, branch, commit, PR, review, CI result) with tasks and artifacts. Display outbound links and provenance but **no GitHub personal access tokens** and no automatic GitHub write/merge actions from Core. Validate allowed schemes and URLs, do not fetch arbitrary URLs server-side (SSRF risk).

### P04-F05 — Dashboard and integration tests
Build compact Task Brief / Artifacts / Git Handoff UI using feature components and hooks, preserving auth/navigation and NAS/media pages. Test forms, empty/error states, responsive layout and read-only boundaries; test SQLite restart persistence and migrations. Maintain small cohesive modules and domain-scoped fixtures.

## 4. Explicit engineering constraints

- Prefer a small number of well-scoped modules over monolithic `App.tsx` or `router.py`; about 250–300 lines is a review heuristic, not a hard threshold.
- Make changes in sequential small commits; focused tests + typecheck after each; complete Core/Web CI at each gate.
- Keep existing public APIs compatible; additive schema only with tested upgrade and rollback plan.
- Credentials stay in environment/secret management, never Git, logs, or artifacts.
- Never promise or perform production deployment; isolated Docker GitHub Actions tests do **not** prove live NAS compatibility.

## 5. Acceptance criteria

1. All new API endpoints require authentication; state-changing endpoints require CSRF and input validation.
2. Existing projects/tasks/scripts/reports contracts remain compatible; NAS and media regression tests PASS.
3. Task briefs can be created/updated/versioned and copied to use manually; HomeAgentP does not invoke Antigravity.
4. Artifact/knowledge metadata is persistent with explicit provenance; read-only previews remain allowlisted and traversal-safe.
5. Git URLs are validated and presented without backend git credentials or outbound arbitrary requests.
6. Sensitive fields are redacted, constraints enforced, and attempts/audit changes captured where appropriate.
7. Ruff, Mypy, Pytest, TypeScript, Vitest and Vite Build PASS on the PR head.
8. Isolated Docker staging PASS before merge; live NAS tests remain NOT_TESTED until separately authorized.
9. PR contains testing evidence, threat notes, migration notes and rollback plan.
10. **No merge or NAS deployment without explicit owner approval.**

## 6. Execution order and review gates

- **Gate 0: Design approval** — produce gap analysis, API/schema proposal, test matrix. No feature implementation before review.
- **Gate A: F02 + F03** — Task Briefs and artifact metadata; test/commit per concern.
- **Gate B: F04 + F05** — Git links/UI/integration; tests and isolated staging.
- **Final review** — security/API/rollback and merge-readiness checks, human approval.

**Current decision:** Phase 04 planning branch initialized. Only this plan is created; all implementation, merge and NAS deployment remain pending.
