-- 002_nas_guardian.sql: HomeAgentP B+ Phase 02 NAS Guardian Schema (Hardened P02-F01..F04)

CREATE TABLE IF NOT EXISTS nas_metric_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    collected_at TEXT NOT NULL,
    adapter_status TEXT NOT NULL CHECK (
        adapter_status IN ('online', 'degraded', 'critical', 'stale', 'unavailable')
    ),
    cpu_usage_percent REAL,
    load_1m REAL,
    load_5m REAL,
    load_15m REAL,
    cpu_cores INTEGER,
    cpu_pressure_json TEXT NOT NULL DEFAULT '{}',
    ram_total_bytes INTEGER,
    ram_available_bytes INTEGER,
    ram_used_bytes INTEGER,
    ram_usage_percent REAL,
    swap_total_bytes INTEGER,
    swap_free_bytes INTEGER,
    swap_used_bytes INTEGER,
    swap_usage_percent REAL,
    memory_pressure_json TEXT NOT NULL DEFAULT '{}',
    mounts_json TEXT NOT NULL DEFAULT '[]',
    containers_json TEXT NOT NULL DEFAULT '{}',
    alerts_json TEXT NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_nas_metric_snapshots_collected_at
    ON nas_metric_snapshots(collected_at DESC);

CREATE TABLE IF NOT EXISTS nas_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_key TEXT NOT NULL,
    code TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('warning', 'critical')),
    category TEXT NOT NULL,
    component TEXT NOT NULL,
    target TEXT NOT NULL,
    message TEXT NOT NULL,
    metric_value REAL,
    threshold_value REAL,
    details_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL CHECK (status IN ('active', 'resolved')) DEFAULT 'active',
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    resolved_at TEXT,
    occurrences INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_nas_alerts_status_last_seen
    ON nas_alerts(status, last_seen_at DESC);

CREATE INDEX IF NOT EXISTS idx_nas_alerts_component_code_status
    ON nas_alerts(component, code, status);
