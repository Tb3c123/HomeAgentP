-- 005_home_assistant_telegram.sql: Phase 05 Read-Only Home Assistant & Notification Outbox Schema

CREATE TABLE IF NOT EXISTS ha_entity_states (
    entity_id TEXT PRIMARY KEY,
    domain TEXT NOT NULL,
    friendly_name TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL,
    attributes_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL CHECK (status IN ('online', 'stale', 'unavailable')),
    last_changed TEXT,
    collected_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ha_entity_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    collected_at TEXT NOT NULL,
    overall_status TEXT NOT NULL CHECK (overall_status IN ('online', 'stale', 'unavailable', 'degraded')),
    entity_count INTEGER NOT NULL DEFAULT 0,
    summary_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_ha_entity_snapshots_collected_at
    ON ha_entity_snapshots(collected_at DESC);

CREATE TABLE IF NOT EXISTS notification_preferences (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    telegram_enabled INTEGER NOT NULL DEFAULT 0 CHECK (telegram_enabled IN (0, 1)),
    min_severity TEXT NOT NULL CHECK (min_severity IN ('info', 'warning', 'critical')) DEFAULT 'warning',
    notify_on_resolve INTEGER NOT NULL DEFAULT 1 CHECK (notify_on_resolve IN (0, 1)),
    cooldown_seconds INTEGER NOT NULL DEFAULT 900 CHECK (cooldown_seconds >= 0 AND cooldown_seconds <= 86400),
    rate_limit_count INTEGER NOT NULL DEFAULT 10 CHECK (rate_limit_count >= 1 AND rate_limit_count <= 200),
    rate_limit_window_seconds INTEGER NOT NULL DEFAULT 300 CHECK (rate_limit_window_seconds >= 10 AND rate_limit_window_seconds <= 86400),
    updated_by TEXT NOT NULL DEFAULT 'system',
    updated_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS notification_deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_key TEXT NOT NULL,
    source_domain TEXT NOT NULL CHECK (source_domain IN ('nas', 'media', 'home_assistant', 'system')),
    severity TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
    channel TEXT NOT NULL CHECK (channel IN ('telegram')),
    destination_masked TEXT NOT NULL,
    message_redacted TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN (
            'pending',
            'in_flight',
            'sent',
            'suppressed_cooldown',
            'suppressed_rate_limit',
            'suppressed_overflow',
            'failed',
            'dead_letter'
        )
    ) DEFAULT 'pending',
    claimed_by TEXT NOT NULL DEFAULT '',
    lease_expires_at TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TEXT,
    last_error_redacted TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    sent_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_notification_deliveries_claim
    ON notification_deliveries(status, next_attempt_at, id);

CREATE INDEX IF NOT EXISTS idx_notification_deliveries_incident_created
    ON notification_deliveries(incident_key, created_at DESC);
