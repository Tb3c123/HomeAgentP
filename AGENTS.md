# Agent instructions — HomeAgentP

Applies to every AI coding assistant, human contractor and automation working on this repo.

## Product mission
HomeAgentP is a home NAS operations and personal AI workspace. Do not reduce it to a developer-only project. Features: NAS monitoring, storage/mount alerts, media/downloads, Home Assistant, scheduler/Telegram, projects/tasks, scripts/artifacts/knowledge, developer workflow, security/recovery.

## B+ boundaries
Google Antigravity is used **directly by the human** in its official App/CLI/Remote Agents with their existing Google AI Pro account. HomeAgentP NEVER wraps, triggers, embeds, proxies, scrapes or rotates an Antigravity consumer login/CLI; Git/files/task brief is handoff. HomeAgentP itself is a lightweight two-service Web/Core platform operating NAS-safe scheduled non-AI tasks.

## First action
Read README.md, docs/00-project-scope.md, docs/ANTIGRAVITY_HANDOFF.md and relevant docs/plans. Summarize plan before writing code. Do one scoped task at a time.

## Hard constraints
- No unapproved NAS operations, no automated deployment, no production modifications.
- No `privileged: true`, host network, raw Docker socket, root access, wide mounts or secrets embedded in images/git.
- Production APIs initially read-only; any write action requires narrowly scoped approval, policy and test.
- No arbitrary execution of AI-written scripts. Scripts must be versioned, reviewed and allowlisted.
- No claims of passing tests without actual evidence.
- Protect Jellyfin, AdGuard, *arr services, qBittorrent and NAS HDD mounts.
- Work on feature branch, open PR, do not merge/deploy without explicit human approval.
- If runtime or permissions are uncertain, write BLOCKED and propose a safe alternative.

## Deliverables per task
Implement only agreed scope, include tests, example config, threat notes, operational notes, rollback and pull request summary. Preserve old decisions where applicable, but B+ overrides direct CLI orchestration for MVP.

## AI coding workflow — modular, bounded and verification-gated
- **Plan once, execute small steps.** For a human-approved multi-step scope (for example, R02–R03), the agent may complete its explicitly authorized substeps sequentially without asking for approval after every mechanical extraction. Do not interpret this as permission to expand scope, merge a PR, deploy, access production systems, or make destructive changes.
- **One responsibility per module.** Prefer feature/domain packages and small, cohesive files over monolithic `App.tsx`, `adapters.py`, or `collector.py`. Suggested review thresholds: Python modules about 300 lines and React components about 250 lines; these are heuristics, not mandatory splits. Explain justified exceptions.
- **Bound context and diffs.** Inspect the relevant symbols, interfaces, tests, and short architecture map before editing. Avoid repeatedly reading or rewriting entire large files or the whole repository. Keep each substep to one concern and normally 3–5 changed files; exceed this only when required for a safe, behavior-preserving extraction.
- **Keep mechanical refactors separate from behavior changes.** Preserve public API routes, response shapes, imports (with compatibility re-exports as needed), authentication, database migrations and UI behavior. Security fixes and behavioral changes require their own clearly described commits and targeted regression tests.
- **Verification gate per substep.** Run relevant focused tests plus the applicable lint/type checks; fix failures before advancing. Commit each successful concern separately with an informative message. At each agreed milestone, run the full available backend/frontend checks and confirm GitHub Actions on the pushed SHA. Report unrun checks as `NOT_TESTED`, never `PASS`.
- **Self-review before moving on.** Check for accidental scope changes, leaked secrets, unsafe operations, lost Phase 02 hardening, breaking imports, and test regressions. Maintain a concise progress log with completed steps, commit SHAs, verification evidence and known limitations; do not dump huge files into handoff summaries.
- **Human review at milestones, not every connector.** Within a pre-approved scope, continue autonomously through passing mechanical substeps. Stop and request direction for security-sensitive decisions, incompatible API/schema changes, ambiguous architecture, unresolved conflicts, repeated test failures, missing permissions, or any NAS/production-impacting action.
- **Git safety remains mandatory.** Work only on the intended feature branch, fetch and integrate current `main` without losing changes, do not force-push or rewrite shared history, and leave PRs open until an explicit human merge instruction.
