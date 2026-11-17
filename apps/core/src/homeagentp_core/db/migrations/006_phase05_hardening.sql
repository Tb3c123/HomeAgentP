-- 006_phase05_hardening.sql: Phase 05 Gate A Hardening (atomic dedup index & incident transition state)

CREATE UNIQUE INDEX IF NOT EXISTS idx_notification_deliveries_active_unique
    ON notification_deliveries(incident_key, destination_masked)
    WHERE status IN ('pending', 'in_flight', 'failed');

CREATE TABLE IF NOT EXISTS notification_incident_states (
    incident_base_key TEXT PRIMARY KEY,
    last_state TEXT NOT NULL CHECK (last_state IN ('triggered', 'resolved')),
    transition_seq INTEGER NOT NULL DEFAULT 1,
    last_transition_at TEXT NOT NULL,
    resolved_notified INTEGER NOT NULL DEFAULT 0 CHECK (resolved_notified IN (0, 1))
);
