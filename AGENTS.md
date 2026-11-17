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
