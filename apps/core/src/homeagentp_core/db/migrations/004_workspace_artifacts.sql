-- 004_workspace_artifacts.sql: Phase 04 Workspace, Task Briefs, Artifacts & Git Provenance

CREATE TABLE IF NOT EXISTS task_briefs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    purpose TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT '',
    excluded_scope TEXT NOT NULL DEFAULT '',
    input_references_json TEXT NOT NULL DEFAULT '[]',
    acceptance_checks_json TEXT NOT NULL DEFAULT '[]',
    security_constraints TEXT NOT NULL DEFAULT '',
    rollback_plan TEXT NOT NULL DEFAULT '',
    human_status TEXT NOT NULL DEFAULT 'draft' CHECK (
        human_status IN ('draft', 'ready_for_handoff', 'handed_off', 'approved', 'archived')
    ),
    rendered_text TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(task_id, version)
);

CREATE INDEX IF NOT EXISTS idx_task_briefs_task_version
    ON task_briefs(task_id, version DESC);

CREATE TABLE IF NOT EXISTS workspace_artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL,
    revision INTEGER NOT NULL,
    version TEXT NOT NULL,
    title TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (
        kind IN ('artifact', 'knowledge', 'plan', 'runbook')
    ),
    source_type TEXT NOT NULL CHECK (
        source_type IN ('allowlisted_report', 'allowlisted_script', 'git_reference', 'note')
    ),
    rel_path TEXT NOT NULL DEFAULT '',
    sha256 TEXT NOT NULL DEFAULT '',
    git_url TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    tags_json TEXT NOT NULL DEFAULT '[]',
    project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(slug, revision),
    UNIQUE(slug, version)
);

CREATE INDEX IF NOT EXISTS idx_workspace_artifacts_slug_rev
    ON workspace_artifacts(slug, revision DESC);
CREATE INDEX IF NOT EXISTS idx_workspace_artifacts_kind
    ON workspace_artifacts(kind);
CREATE INDEX IF NOT EXISTS idx_workspace_artifacts_task_id
    ON workspace_artifacts(task_id);
CREATE INDEX IF NOT EXISTS idx_workspace_artifacts_project_id
    ON workspace_artifacts(project_id);

CREATE TABLE IF NOT EXISTS git_provenance_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('task', 'artifact')),
    entity_id INTEGER NOT NULL,
    repo_url TEXT NOT NULL,
    branch TEXT NOT NULL DEFAULT '',
    commit_sha TEXT NOT NULL DEFAULT '',
    pr_url TEXT NOT NULL DEFAULT '',
    review_status TEXT NOT NULL DEFAULT 'none' CHECK (
        review_status IN ('none', 'pending', 'approved', 'changes_requested')
    ),
    ci_status TEXT NOT NULL DEFAULT 'unknown' CHECK (
        ci_status IN ('unknown', 'pending', 'success', 'failure')
    ),
    ci_url TEXT NOT NULL DEFAULT '',
    verification_source TEXT NOT NULL DEFAULT 'manual_unverified' CHECK (
        verification_source IN ('manual_unverified', 'external_ci_verified')
    ),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_git_provenance_entity
    ON git_provenance_links(entity_type, entity_id);

CREATE TRIGGER IF NOT EXISTS trg_cleanup_provenance_on_task_delete
AFTER DELETE ON tasks
BEGIN
    DELETE FROM git_provenance_links
    WHERE entity_type = 'task' AND entity_id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_cleanup_provenance_on_artifact_delete
AFTER DELETE ON workspace_artifacts
BEGIN
    DELETE FROM git_provenance_links
    WHERE entity_type = 'artifact' AND entity_id = OLD.id;
END;
