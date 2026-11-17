-- 002_nas_guardian.sql: HomeAgentP B+ Phase 02 NAS Guardian Schema

CREATE TABLE IF NOT EXISTS nas_metric_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    collected_at TEXT NOT NULL,
    adapter_status TEXT NOT NULL CHECK (
        adapter_status IN ('online', 'degraded', 'unavailable')
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
    code TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('warning', 'critical')),
    component TEXT NOT NULL,
    message TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_nas_alerts_created_at
    ON nas_alerts(created_at DESC);
