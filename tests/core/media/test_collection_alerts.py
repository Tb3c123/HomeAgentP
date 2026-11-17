"""Media collection orchestration, failure thresholds, stale cache, and alert lifecycle tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from tests.core.media.conftest import build_valid_transports, make_media_settings

from homeagentp_core.db.connection import db_session
from homeagentp_core.db.migrator import apply_migrations
from homeagentp_core.modules.media.collector import (
    collect_media_telemetry,
    query_media_alerts,
)


def test_valid_responses_across_all_seven_services(tmp_path: Path) -> None:
    """Verify full parsing and alert extraction across all 7 services with valid responses."""
    settings = make_media_settings(tmp_path)
    transports = build_valid_transports()

    with db_session(settings.db_path) as conn:
        apply_migrations(conn)
        snap = collect_media_telemetry(settings, conn=conn, transports=transports)

    assert snap["services"]["jellyfin"]["status"] == "degraded"
    assert snap["services"]["qbittorrent"]["status"] == "critical"
    assert snap["services"]["sonarr"]["status"] == "degraded"
    assert snap["services"]["radarr"]["status"] == "online"
    assert snap["services"]["bazarr"]["status"] == "degraded"
    assert snap["services"]["prowlarr"]["status"] == "degraded"
    assert snap["services"]["seerr"]["status"] == "online"

    alert_keys = {a["alert_key"] for a in snap["alerts"]}
    assert "jellyfin:playback.error" in alert_keys
    assert "qbittorrent:torrent.error" in alert_keys
    assert "qbittorrent:torrent.stalled" in alert_keys
    assert "sonarr:queue.import_failed" in alert_keys
    assert "bazarr:health.issue" in alert_keys
    assert "prowlarr:indexer.failing" in alert_keys


def test_consecutive_failure_threshold_stale_cache_and_alert_recovery(tmp_path: Path) -> None:
    """Verify single timeout does NOT mark service offline until threshold, then recovers."""
    settings = make_media_settings(
        tmp_path,
        media_failure_threshold=3,
        media_snapshot_stale_seconds=300,
        qbittorrent_url="",
        sonarr_url="",
        radarr_url="",
        bazarr_url="",
        prowlarr_url="",
        seerr_url="",
    )
    valid_transports = build_valid_transports()
    timeout_transports = {
        "jellyfin": httpx.MockTransport(
            lambda req: (_ for _ in ()).throw(httpx.ReadTimeout("timed out", request=req))
        )
    }

    t0 = datetime(2026, 11, 17, 6, 0, 0, tzinfo=UTC)
    with db_session(settings.db_path) as conn:
        apply_migrations(conn)

        snap0 = collect_media_telemetry(
            settings, conn=conn, transports=valid_transports, now=t0
        )
        assert snap0["services"]["jellyfin"]["consecutive_failures"] == 0
        assert snap0["services"]["jellyfin"]["metrics"]["libraries"]["movies"] == 420

        snap1 = collect_media_telemetry(
            settings,
            conn=conn,
            transports=timeout_transports,
            now=t0 + timedelta(seconds=60),
        )
        jf1 = snap1["services"]["jellyfin"]
        assert jf1["consecutive_failures"] == 1
        assert jf1["status"] == "degraded"
        assert jf1["stale"] is False
        assert jf1["metrics"]["libraries"]["movies"] == 420
        active_keys_1 = {a["alert_key"] for a in snap1["alerts"]}
        assert "jellyfin:service.timeout" in active_keys_1
        assert "jellyfin:service.offline" not in active_keys_1

        snap2 = collect_media_telemetry(
            settings,
            conn=conn,
            transports=timeout_transports,
            now=t0 + timedelta(seconds=400),
        )
        jf2 = snap2["services"]["jellyfin"]
        assert jf2["consecutive_failures"] == 2
        assert jf2["status"] == "stale"
        assert jf2["stale"] is True
        active_keys_2 = {a["alert_key"] for a in snap2["alerts"]}
        assert "jellyfin:snapshot.stale" in active_keys_2
        assert "jellyfin:service.offline" not in active_keys_2

        snap3 = collect_media_telemetry(
            settings,
            conn=conn,
            transports=timeout_transports,
            now=t0 + timedelta(seconds=490),
        )
        jf3 = snap3["services"]["jellyfin"]
        assert jf3["consecutive_failures"] == 3
        assert jf3["status"] == "offline"
        active_keys_3 = {a["alert_key"] for a in snap3["alerts"]}
        assert "jellyfin:service.offline" in active_keys_3

        snap4 = collect_media_telemetry(
            settings,
            conn=conn,
            transports=valid_transports,
            now=t0 + timedelta(seconds=550),
        )
        jf4 = snap4["services"]["jellyfin"]
        assert jf4["consecutive_failures"] == 0
        assert jf4["stale"] is False
        active_keys_4 = {a["alert_key"] for a in snap4["alerts"]}
        assert "jellyfin:service.offline" not in active_keys_4
        assert "jellyfin:snapshot.stale" not in active_keys_4

        all_alerts = query_media_alerts(conn, include_resolved=True)
        resolved_offline = [
            a
            for a in all_alerts
            if a["alert_key"] == "jellyfin:service.offline" and a["status"] == "resolved"
        ]
        assert len(resolved_offline) == 1
        assert resolved_offline[0]["resolved_at"] is not None
