"""Alert lifecycle persistence tests for NAS Guardian."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tests.core.nas.conftest import make_nas_settings

from homeagentp_core.db.connection import db_session
from homeagentp_core.main import initialize_core_state
from homeagentp_core.modules.nas.collector import (
    persist_nas_snapshot,
    query_nas_alerts,
)


def test_p02_f04_alert_lifecycle_dedup_resolve_and_reopen(tmp_path: Path) -> None:
    """Verify P02-F04: alert appearance, deduplication, resolution, and re-occurrence."""
    settings = make_nas_settings(tmp_path, db_name="f04_alerts.db")
    db_file = settings.db_path
    initialize_core_state(settings)

    def _make_snap(ts: str, alerts: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "collected_at": ts,
            "adapter_status": "critical" if alerts else "online",
            "cpu": {"usage_percent": 20.0, "pressure": {}},
            "memory": {"usage_percent": 40.0, "pressure": {}},
            "mounts": {},
            "mounts_list": [],
            "containers": {},
            "alerts": alerts,
        }

    disk_alert = {
        "alert_key": "mount:/mnt/disk2:mount.unmounted_fallback",
        "code": "mount.unmounted_fallback",
        "severity": "critical",
        "category": "mount_guardian",
        "component": "mount:/mnt/disk2",
        "target": "/mnt/disk2",
        "message": "Mount /mnt/disk2 fell back to root filesystem.",
        "metric_value": None,
        "threshold_value": None,
        "details": {"mount_point": "/mnt/disk2"},
    }

    t1 = "2026-11-17T06:00:00+00:00"
    t2 = "2026-11-17T06:01:00+00:00"
    t3 = "2026-11-17T06:02:00+00:00"
    t4 = "2026-11-17T06:03:00+00:00"

    with db_session(db_file) as conn:
        # Step 1: Alert first appears at t1
        persist_nas_snapshot(conn, _make_snap(t1, [dict(disk_alert)]), retention_limit=50)
        active_1 = query_nas_alerts(conn, include_resolved=False)
        assert len(active_1) == 1
        assert active_1[0]["status"] == "active"
        assert active_1[0]["first_seen_at"] == t1
        assert active_1[0]["last_seen_at"] == t1
        assert active_1[0]["resolved_at"] is None
        assert active_1[0]["occurrences"] == 1
        first_id = active_1[0]["id"]

        # Step 2: Same alert persists at t2 -> deduplicated into same row, occurrences == 2
        persist_nas_snapshot(conn, _make_snap(t2, [dict(disk_alert)]), retention_limit=50)
        active_2 = query_nas_alerts(conn, include_resolved=False)
        assert len(active_2) == 1
        assert active_2[0]["id"] == first_id
        assert active_2[0]["first_seen_at"] == t1
        assert active_2[0]["last_seen_at"] == t2
        assert active_2[0]["occurrences"] == 2

        # Step 3: Condition clears at t3 -> row transitions to 'resolved' with resolved_at == t3
        persist_nas_snapshot(conn, _make_snap(t3, []), retention_limit=50)
        active_3 = query_nas_alerts(conn, include_resolved=False)
        assert len(active_3) == 0
        all_3 = query_nas_alerts(conn, include_resolved=True)
        assert len(all_3) == 1
        assert all_3[0]["id"] == first_id
        assert all_3[0]["status"] == "resolved"
        assert all_3[0]["resolved_at"] == t3

        # Step 4: Alert re-occurs at t4 -> new 'active' row created while resolved history stays
        persist_nas_snapshot(conn, _make_snap(t4, [dict(disk_alert)]), retention_limit=50)
        active_4 = query_nas_alerts(conn, include_resolved=False)
        assert len(active_4) == 1
        assert active_4[0]["id"] != first_id
        assert active_4[0]["status"] == "active"
        assert active_4[0]["first_seen_at"] == t4
        assert active_4[0]["occurrences"] == 1
        all_4 = query_nas_alerts(conn, include_resolved=True)
        assert len(all_4) == 2
