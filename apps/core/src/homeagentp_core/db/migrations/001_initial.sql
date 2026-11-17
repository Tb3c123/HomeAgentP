-- 001_initial.sql: HomeAgentP B+ Phase 01 Foundation Schema

CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'owner' CHECK (role IN ('owner', 'viewer')),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    csrf_token TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    ip_address TEXT,
    user_agent TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL CHECK (
        category IN (
            'nas_guardian',
            'media',
            'downloads',
            'home_assistant',
            'monitoring',
            'telegram',
            'scripts',
            'tasks',
            'ai_workspace',
            'developer',
            'security'
        )
    ),
    description TEXT NOT NULL DEFAULT '',
    repo_url TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'tasks' CHECK (
        category IN (
            'nas_guardian',
            'media',
            'downloads',
            'home_assistant',
            'monitoring',
            'telegram',
            'scripts',
            'tasks',
            'ai_workspace',
            'developer',
            'security'
        )
    ),
    status TEXT NOT NULL DEFAULT 'backlog' CHECK (
        status IN ('backlog', 'ready', 'in_progress', 'review', 'done', 'blocked')
    ),
    priority TEXT NOT NULL DEFAULT 'medium' CHECK (
        priority IN ('low', 'medium', 'high', 'critical')
    ),
    task_brief_md TEXT NOT NULL DEFAULT '',
    git_branch TEXT NOT NULL DEFAULT '',
    pr_url TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_category ON tasks(category);

CREATE TABLE IF NOT EXISTS task_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    attempt_number INTEGER NOT NULL,
    executor_type TEXT NOT NULL CHECK (
        executor_type IN ('human', 'antigravity_handoff', 'scheduled_job')
    ),
    status TEXT NOT NULL CHECK (
        status IN ('started', 'succeeded', 'failed', 'cancelled', 'not_tested')
    ),
    summary TEXT NOT NULL DEFAULT '',
    artifact_rel_path TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_task_attempts_task_id ON task_attempts(task_id);

CREATE TABLE IF NOT EXISTS script_manifests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'nas_guardian',
    rel_path TEXT UNIQUE NOT NULL,
    sha256 TEXT NOT NULL,
    review_status TEXT NOT NULL CHECK (
        review_status IN ('draft', 'reviewed', 'allowlisted', 'revoked')
    ),
    is_executable_allowed INTEGER NOT NULL DEFAULT 0 CHECK (is_executable_allowed = 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'nas_guardian',
    summary TEXT NOT NULL DEFAULT '',
    rel_path TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL DEFAULT '',
    details_json TEXT NOT NULL DEFAULT '{}',
    ip_address TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at DESC);
