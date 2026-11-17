-- 003_media_downloads.sql: HomeAgentP B+ Phase 03 Media & Downloads Monitoring Hub Schema

CREATE TABLE IF NOT EXISTS media_metric_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    collected_at TEXT NOT NULL,
    overall_status TEXT NOT NULL CHECK (
        overall_status IN ('online', 'degraded', 'critical', 'stale', 'unavailable')
    ),
    jellyfin_active_streams INTEGER NOT NULL DEFAULT 0,
    jellyfin_transcoding_streams INTEGER NOT NULL DEFAULT 0,
    qb_dl_speed_bytes INTEGER,
    qb_up_speed_bytes INTEGER,
    qb_downloading_count INTEGER,
    qb_stalled_count INTEGER,
    qb_errored_count INTEGER,
    sonarr_queue_count INTEGER,
    radarr_queue_count INTEGER,
    missing_subtitles_count INTEGER,
    pending_requests_count INTEGER,
    services_summary_json TEXT NOT NULL DEFAULT '{}',
    alerts_json TEXT NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_media_metric_snapshots_collected_at
    ON media_metric_snapshots(collected_at DESC);

CREATE TABLE IF NOT EXISTS media_service_states (
    service TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    last_success_at TEXT,
    last_failure_at TEXT,
    last_error_code TEXT,
    last_reason TEXT NOT NULL DEFAULT '',
    last_snapshot_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS media_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_key TEXT NOT NULL,
    code TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('warning', 'critical')),
    category TEXT NOT NULL,
    service TEXT NOT NULL,
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

CREATE INDEX IF NOT EXISTS idx_media_alerts_status_last_seen
    ON media_alerts(status, last_seen_at DESC);

CREATE INDEX IF NOT EXISTS idx_media_alerts_service_code_status
    ON media_alerts(service, code, status);
