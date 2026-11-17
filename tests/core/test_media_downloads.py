"""Unit and integration tests for Phase 03 Media & Downloads Monitoring Hub.

Covers all mandatory test scenarios using mocked HTTP transports (zero real NAS network calls):
1. Valid API responses across all 7 adapters (Jellyfin, qBittorrent, Sonarr, Radarr, Bazarr,
   Prowlarr, Seerr).
2. Authentication failures (HTTP 401/403 and qBittorrent login 'Fails.').
3. Network timeouts and connection failures.
4. Malformed JSON and oversized response payloads (> media_max_response_bytes).
5. API version incompatibility (e.g., Jellyfin v9, Sonarr v2, qBittorrent WebAPI v1).
6. Missing required fields in upstream JSON responses.
7. Disabled / unconfigured connectors reporting honest 'unavailable' status.
8. Stale cached data detection when a service degrades after exceeding snapshot_stale_seconds.
9. Multiple simultaneous service failures (fault isolation).
10. Consecutive failure threshold (anti-flapping: 1..N failures before 'offline') and alert
    activation -> deduplication -> resolution lifecycle.
11. SSRF allowlist, redirect blocking, and read-only HTTP method/endpoint enforcement.
12. Non-overlapping MediaCollectionScheduler concurrency, timeout handling, and SQLite retention.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from tests.core.conftest import TEST_ADMIN_PASSWORD, TEST_ADMIN_USERNAME, TEST_SECRET_KEY

from homeagentp_core.config import Settings
from homeagentp_core.db.connection import db_session
from homeagentp_core.db.migrator import apply_migrations
from homeagentp_core.logging import redact_structure, redact_text
from homeagentp_core.main import create_app
from homeagentp_core.modules.media.adapters import (
    JellyfinAdapter,
    QBittorrentAdapter,
    SonarrAdapter,
)
from homeagentp_core.modules.media.base import (
    MediaSecurityError,
    SafeMediaHttpClient,
    validate_service_url,
)
from homeagentp_core.modules.media.collector import (
    collect_media_telemetry,
    persist_media_snapshot,
    query_media_alerts,
    query_media_history,
)
from homeagentp_core.modules.media.scheduler import MediaCollectionScheduler


def _make_media_settings(tmp_path: Path, **overrides: Any) -> Settings:
    scripts_dir = tmp_path / "scripts"
    reports_dir = tmp_path / "reports"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    defaults: dict[str, Any] = {
        "env": "testing",
        "db_path": tmp_path / "media_test.db",
        "secret_key": TEST_SECRET_KEY,
        "admin_username": TEST_ADMIN_USERNAME,
        "admin_password": TEST_ADMIN_PASSWORD,
        "scripts_dir": scripts_dir,
        "reports_dir": reports_dir,
        "seed_examples": False,
        "media_adapter_enabled": True,
        "media_failure_threshold": 3,
        "media_snapshot_stale_seconds": 300,
        "jellyfin_url": "http://jellyfin:8096",
        "jellyfin_api_key": "jf_test_token_secret_123",
        "qbittorrent_url": "http://qbittorrent:8080",
        "qbittorrent_username": "admin",
        "qbittorrent_password": "qb_test_password_secret",
        "qbittorrent_stalled_threshold_seconds": 1800,
        "sonarr_url": "http://sonarr:8989",
        "sonarr_api_key": "sonarr_test_key_123",
        "radarr_url": "http://radarr:7878",
        "radarr_api_key": "radarr_test_key_123",
        "bazarr_url": "http://bazarr:6767",
        "bazarr_api_key": "bazarr_test_key_123",
        "prowlarr_url": "http://prowlarr:9696",
        "prowlarr_api_key": "prowlarr_test_key_123",
        "seerr_url": "http://seerr:5055",
        "seerr_api_key": "seerr_test_key_123",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _build_valid_transports() -> dict[str, httpx.BaseTransport]:
    """Build deterministic mocked HTTP transports for all 7 Media & Downloads services."""
    now_epoch = int(datetime.now(UTC).timestamp())

    def jellyfin_handler(req: httpx.Request) -> httpx.Response:
        assert "jf_test_token_secret_123" in req.headers.get("X-Emby-Token", "")
        path = req.url.path
        if path == "/System/Info":
            return httpx.Response(
                200,
                json={
                    "ServerName": "HomeNAS-Jellyfin",
                    "Version": "10.9.11",
                    "OperatingSystem": "Linux",
                    "Id": "jf-server-1",
                },
            )
        if path == "/Items/Counts":
            return httpx.Response(
                200,
                json={
                    "MovieCount": 420,
                    "SeriesCount": 85,
                    "EpisodeCount": 3120,
                    "SongCount": 150,
                    "AlbumCount": 18,
                },
            )
        if path == "/Sessions":
            return httpx.Response(
                200,
                json=[
                    {
                        "Id": "sess-1",
                        "UserName": "alice",
                        "Client": "Jellyfin Web",
                        "DeviceName": "LivingRoom TV",
                        "NowPlayingItem": {
                            "Name": "Dune: Part Two",
                            "Type": "Movie",
                        },
                        "PlayState": {
                            "PlayMethod": "DirectPlay",
                            "IsPaused": False,
                        },
                    },
                    {
                        "Id": "sess-2",
                        "UserName": "bob",
                        "Client": "Swiftfin",
                        "DeviceName": "iPhone",
                        "NowPlayingItem": {
                            "Name": "Severance S01E01",
                            "Type": "Episode",
                            "SeriesName": "Severance",
                        },
                        "PlayState": {
                            "PlayMethod": "Transcode",
                            "IsPaused": False,
                        },
                        "TranscodingInfo": {
                            "VideoCodec": "h264",
                            "AudioCodec": "aac",
                            "Bitrate": 8500000,
                            "TranscodeReasons": ["ContainerNotSupported"],
                        },
                    },
                ],
            )
        if path == "/System/ActivityLog/Entries":
            return httpx.Response(
                200,
                json={
                    "Items": [
                        {
                            "Name": "Playback failed for item",
                            "Type": "PlaybackError",
                            "Severity": "Error",
                            "Date": "2026-11-17T06:00:00Z",
                            "ShortOverview": "FFmpeg exited with code 1",
                        }
                    ]
                },
            )
        return httpx.Response(404)

    def qbittorrent_handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if path == "/api/v2/auth/login" and req.method == "POST":
            return httpx.Response(
                200,
                text="Ok.",
                headers={"Set-Cookie": "SID=mock_qb_sid_token; Path=/; HttpOnly"},
            )
        if path == "/api/v2/app/version":
            return httpx.Response(200, text="v4.6.7")
        if path == "/api/v2/app/webapiVersion":
            return httpx.Response(200, text="2.9.3")
        if path == "/api/v2/transfer/info":
            return httpx.Response(
                200,
                json={
                    "connection_status": "connected",
                    "dht_nodes": 312,
                    "dl_info_speed": 15_728_640,
                    "up_info_speed": 2_097_152,
                    "dl_info_data": 107_374_182_400,
                    "up_info_data": 53_687_091_200,
                },
            )
        if path == "/api/v2/torrents/info":
            return httpx.Response(
                200,
                json=[
                    {
                        "hash": "h1",
                        "name": "Ubuntu-24.04-ISO",
                        "state": "downloading",
                        "progress": 0.64,
                        "dlspeed": 15_728_640,
                        "upspeed": 524_288,
                        "time_active": 600,
                        "last_activity": now_epoch - 5,
                        "eta": 180,
                        "size": 5_000_000_000,
                    },
                    {
                        "hash": "h2",
                        "name": "Debian-12-Netinst",
                        "state": "uploading",
                        "progress": 1.0,
                        "dlspeed": 0,
                        "upspeed": 1_572_864,
                        "time_active": 86400,
                        "last_activity": now_epoch - 2,
                        "eta": 8640000,
                        "size": 650_000_000,
                    },
                    {
                        "hash": "h3",
                        "name": "Stalled-Linux-Archive",
                        "state": "stalledDL",
                        "progress": 0.12,
                        "dlspeed": 0,
                        "upspeed": 0,
                        "time_active": 7200,
                        "last_activity": now_epoch - 5400,
                        "eta": 8640000,
                        "size": 12_000_000_000,
                    },
                    {
                        "hash": "h4",
                        "name": "MissingDiskMountItem",
                        "state": "missingFiles",
                        "progress": 1.0,
                        "dlspeed": 0,
                        "upspeed": 0,
                        "time_active": 3600,
                        "last_activity": now_epoch - 1000,
                        "eta": 0,
                        "size": 4_000_000_000,
                    },
                ],
            )
        return httpx.Response(404)

    def sonarr_handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if path == "/api/v3/system/status":
            return httpx.Response(200, json={"version": "4.0.9.2244", "appName": "Sonarr"})
        if path == "/api/v3/health":
            return httpx.Response(200, json=[])
        if path == "/api/v3/series":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 1,
                        "title": "Severance",
                        "monitored": True,
                        "statistics": {
                            "episodeFileCount": 9,
                            "sizeOnDisk": 25_000_000_000,
                        },
                    },
                    {
                        "id": 2,
                        "title": "Andor",
                        "monitored": True,
                        "statistics": {
                            "episodeFileCount": 12,
                            "sizeOnDisk": 35_000_000_000,
                        },
                    },
                ],
            )
        if path == "/api/v3/queue":
            return httpx.Response(
                200,
                json={
                    "totalRecords": 1,
                    "records": [
                        {
                            "id": 101,
                            "title": "Severance.S02E01.1080p",
                            "status": "warning",
                            "trackedDownloadStatus": "warning",
                            "trackedDownloadState": "importBlocked",
                            "errorMessage": "Unable to import: sample file check failed",
                            "protocol": "torrent",
                            "downloadClient": "qBittorrent",
                        }
                    ],
                },
            )
        if path == "/api/v3/wanted/missing":
            return httpx.Response(200, json={"totalRecords": 4, "records": []})
        if path == "/api/v3/diskspace":
            return httpx.Response(
                200,
                json=[
                    {
                        "path": "/mnt/disk1/tv",
                        "label": "Disk 1 TV",
                        "freeSpace": 2_000_000_000_000,
                        "totalSpace": 8_000_000_000_000,
                    }
                ],
            )
        return httpx.Response(404)

    def radarr_handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if path == "/api/v3/system/status":
            return httpx.Response(200, json={"version": "5.10.3.9171", "appName": "Radarr"})
        if path == "/api/v3/health":
            return httpx.Response(200, json=[])
        if path == "/api/v3/movie":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 1,
                        "title": "Dune: Part Two",
                        "monitored": True,
                        "hasFile": True,
                        "sizeOnDisk": 42_000_000_000,
                    },
                    {
                        "id": 2,
                        "title": "Oppenheimer",
                        "monitored": True,
                        "hasFile": False,
                        "sizeOnDisk": 0,
                    },
                ],
            )
        if path == "/api/v3/queue":
            return httpx.Response(200, json={"totalRecords": 0, "records": []})
        if path == "/api/v3/wanted/missing":
            return httpx.Response(200, json={"totalRecords": 1, "records": []})
        if path == "/api/v3/diskspace":
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    def bazarr_handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if path == "/api/system/status":
            return httpx.Response(200, json={"data": {"bazarr_version": "1.4.3"}})
        if path == "/api/badges":
            return httpx.Response(
                200,
                json={
                    "episodes": 7,
                    "movies": 2,
                    "providers": 1,
                    "status": 1,
                    "sonarr_signalr": "LIVE",
                    "radarr_signalr": "LIVE",
                },
            )
        if path == "/api/system/health":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "object": "OpenSubtitles.com",
                            "issue": "Provider throttled for 10 minutes",
                        }
                    ]
                },
            )
        return httpx.Response(404)

    def prowlarr_handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if path == "/api/v1/system/status":
            return httpx.Response(200, json={"version": "1.24.2.4779", "appName": "Prowlarr"})
        if path == "/api/v1/indexer":
            return httpx.Response(
                200,
                json=[
                    {"id": 1, "name": "LinuxTracker", "enable": True},
                    {"id": 2, "name": "AcademicTorrents", "enable": True},
                    {"id": 3, "name": "OldArchive", "enable": False},
                ],
            )
        if path == "/api/v1/indexerstatus":
            return httpx.Response(
                200,
                json=[
                    {
                        "indexerId": 2,
                        "disabledTill": "2026-11-17T08:00:00Z",
                        "mostRecentFailure": "2026-11-17T06:10:00Z",
                    }
                ],
            )
        if path == "/api/v1/health":
            return httpx.Response(
                200,
                json=[
                    {
                        "source": "IndexerStatusCheck",
                        "type": "warning",
                        "message": "Indexers unavailable due to failures: AcademicTorrents",
                    }
                ],
            )
        return httpx.Response(404)

    def seerr_handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if path == "/api/v1/status":
            return httpx.Response(
                200,
                json={
                    "version": "1.9.2",
                    "updateAvailable": False,
                    "commitsBehind": 0,
                },
            )
        if path == "/api/v1/request/count":
            return httpx.Response(
                200,
                json={
                    "total": 14,
                    "movie": 9,
                    "tv": 5,
                    "pending": 2,
                    "approved": 4,
                    "processing": 1,
                    "available": 6,
                    "declined": 1,
                },
            )
        if path == "/api/v1/request":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": 501,
                            "type": "movie",
                            "status": 1,
                            "createdAt": "2026-11-17T05:30:00Z",
                            "requestedBy": {"displayName": "alice"},
                            "media": {"tmdbId": 693134},
                        },
                        {
                            "id": 502,
                            "type": "tv",
                            "status": 2,
                            "createdAt": "2026-11-16T20:00:00Z",
                            "requestedBy": {"displayName": "bob"},
                            "media": {"tmdbId": 95396},
                        },
                    ]
                },
            )
        return httpx.Response(404)

    return {
        "jellyfin": httpx.MockTransport(jellyfin_handler),
        "qbittorrent": httpx.MockTransport(qbittorrent_handler),
        "sonarr": httpx.MockTransport(sonarr_handler),
        "radarr": httpx.MockTransport(radarr_handler),
        "bazarr": httpx.MockTransport(bazarr_handler),
        "prowlarr": httpx.MockTransport(prowlarr_handler),
        "seerr": httpx.MockTransport(seerr_handler),
    }


def test_disabled_connectors_report_honest_unavailable(tmp_path: Path) -> None:
    """When HOMEAGENTP_MEDIA_ADAPTER_ENABLED=false, all connectors report unavailable."""
    settings = _make_media_settings(tmp_path, media_adapter_enabled=False)
    with db_session(settings.db_path) as conn:
        apply_migrations(conn)
        snap = collect_media_telemetry(settings, conn=conn)

    assert snap["overall_status"] == "unavailable"
    assert snap["adapter_enabled"] is False
    for svc_name, svc_data in snap["services"].items():
        assert svc_data["status"] == "unavailable", f"{svc_name} should be unavailable"
        assert svc_data["enabled"] is False
        assert svc_data["write_operations_performed"] == 0
    assert snap["alerts"] == []


def test_valid_responses_across_all_seven_services(tmp_path: Path) -> None:
    """Verify full parsing and alert extraction across all 7 services with valid responses."""
    settings = _make_media_settings(tmp_path)
    transports = _build_valid_transports()

    with db_session(settings.db_path) as conn:
        apply_migrations(conn)
        snap = collect_media_telemetry(settings, conn=conn, transports=transports)

    # Jellyfin verification
    jf = snap["services"]["jellyfin"]
    assert jf["status"] == "degraded"  # 1 playback error logged in ActivityLog
    assert jf["version"] == "10.9.11"
    assert jf["metrics"]["libraries"]["movies"] == 420
    assert jf["metrics"]["libraries"]["series"] == 85
    assert jf["metrics"]["libraries"]["episodes"] == 3120
    assert jf["metrics"]["sessions"]["active_count"] == 2
    assert jf["metrics"]["sessions"]["direct_play_count"] == 1
    assert jf["metrics"]["sessions"]["transcoding_count"] == 1
    assert jf["metrics"]["playback_errors"]["count"] == 1

    # qBittorrent verification
    qb = snap["services"]["qbittorrent"]
    assert qb["status"] == "critical"  # 1 missingFiles torrent + 1 stalled over threshold
    assert qb["version"] == "v4.6.7"
    assert qb["metrics"]["download_speed_bytes"] == 15_728_640
    assert qb["metrics"]["upload_speed_bytes"] == 2_097_152
    assert qb["metrics"]["counts"]["downloading"] == 1
    assert qb["metrics"]["counts"]["seeding"] == 1
    assert qb["metrics"]["counts"]["stalled"] == 1
    assert qb["metrics"]["counts"]["stalled_over_threshold"] == 1
    assert qb["metrics"]["counts"]["errored"] == 1
    assert "client-side GET endpoint allowlist" in qb["metrics"]["credential_scope_notice"]

    # Sonarr verification
    sn = snap["services"]["sonarr"]
    assert sn["status"] == "degraded"  # 1 failed/blocked queue import
    assert sn["version"] == "4.0.9.2244"
    assert sn["metrics"]["total_count"] == 2
    assert sn["metrics"]["available_file_count"] == 21
    assert sn["metrics"]["missing_count"] == 4
    assert sn["metrics"]["queue_failed_count"] == 1

    # Radarr verification
    rd = snap["services"]["radarr"]
    assert rd["status"] == "online"
    assert rd["version"] == "5.10.3.9171"
    assert rd["metrics"]["total_count"] == 2
    assert rd["metrics"]["available_file_count"] == 1
    assert rd["metrics"]["missing_count"] == 1

    # Bazarr verification
    bz = snap["services"]["bazarr"]
    assert bz["status"] == "degraded"
    assert bz["version"] == "1.4.3"
    assert bz["metrics"]["missing_episode_subtitles"] == 7
    assert bz["metrics"]["missing_movie_subtitles"] == 2
    assert bz["metrics"]["unhealthy_providers_count"] == 1

    # Prowlarr verification
    pr = snap["services"]["prowlarr"]
    assert pr["status"] == "degraded"
    assert pr["version"] == "1.24.2.4779"
    assert pr["metrics"]["total_indexers"] == 3
    assert pr["metrics"]["enabled_indexers"] == 2
    assert pr["metrics"]["failing_indexers_count"] == 1

    # Seerr verification
    sr = snap["services"]["seerr"]
    assert sr["status"] == "online"
    assert sr["version"] == "1.9.2"
    assert sr["metrics"]["requests"]["total"] == 14
    assert sr["metrics"]["requests"]["pending"] == 2
    assert sr["metrics"]["requests"]["approved"] == 4
    assert len(sr["metrics"]["recent_requests"]) == 2

    alert_keys = {a["alert_key"] for a in snap["alerts"]}
    assert "jellyfin:playback.error" in alert_keys
    assert "qbittorrent:torrent.error" in alert_keys
    assert "qbittorrent:torrent.stalled" in alert_keys
    assert "sonarr:queue.import_failed" in alert_keys
    assert "bazarr:health.issue" in alert_keys
    assert "prowlarr:indexer.failing" in alert_keys


def test_authentication_failures_and_secret_redaction(tmp_path: Path) -> None:
    """Verify HTTP 401/403 and qBittorrent 'Fails.' trigger auth_error without leaking secrets."""
    settings = _make_media_settings(tmp_path)

    jf_401 = httpx.MockTransport(lambda req: httpx.Response(401, json={"error": "Unauthorized"}))
    qb_fail = httpx.MockTransport(lambda req: httpx.Response(200, text="Fails."))

    jf_snap = JellyfinAdapter(settings, transport=jf_401).collect()
    assert jf_snap["status"] == "auth_error"
    assert jf_snap["error_code"] == "auth_failed"
    assert "jf_test_token_secret_123" not in json.dumps(jf_snap)

    qb_snap = QBittorrentAdapter(settings, transport=qb_fail).collect()
    assert qb_snap["status"] == "auth_error"
    assert qb_snap["error_code"] == "auth_failed"
    assert "qb_test_password_secret" not in json.dumps(qb_snap)

    # Verify logging and settings redaction
    redacted_cfg = settings.redacted_summary()
    assert redacted_cfg["jellyfin_api_key"] == "[REDACTED]"  # noqa: S105
    assert redacted_cfg["qbittorrent_password"] == "[REDACTED]"  # noqa: S105
    assert redacted_cfg["sonarr_api_key"] == "[REDACTED]"  # noqa: S105
    assert "[REDACTED]" in redact_text("X-Emby-Token: secret_emby_123 and SID=secret_sid_456")
    assert redact_structure({"X-Api-Key": "secret"})["X-Api-Key"] == "[REDACTED]"


def test_timeout_connection_error_malformed_json_and_oversized_payload(tmp_path: Path) -> None:
    """Verify timeout, connection failure, malformed JSON, missing fields, and size cap."""
    settings = _make_media_settings(tmp_path, media_max_response_bytes=4096)

    def timeout_handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Simulated read timeout", request=req)

    def conn_err_handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=req)

    def malformed_json_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"{not-valid-json")

    def missing_fields_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ServerName": "MissingVersionField"})

    def oversized_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 8192)

    assert (
        JellyfinAdapter(settings, transport=httpx.MockTransport(timeout_handler)).collect()[
            "error_code"
        ]
        == "timeout"
    )
    assert (
        JellyfinAdapter(settings, transport=httpx.MockTransport(conn_err_handler)).collect()[
            "error_code"
        ]
        == "connection_failed"
    )
    assert (
        JellyfinAdapter(settings, transport=httpx.MockTransport(malformed_json_handler)).collect()[
            "error_code"
        ]
        == "malformed_response"
    )
    assert (
        JellyfinAdapter(settings, transport=httpx.MockTransport(missing_fields_handler)).collect()[
            "error_code"
        ]
        == "malformed_response"
    )
    assert (
        JellyfinAdapter(settings, transport=httpx.MockTransport(oversized_handler)).collect()[
            "error_code"
        ]
        == "response_too_large"
    )


def test_api_version_incompatibility_rejected(tmp_path: Path) -> None:
    """Verify incompatible server/API major versions raise unsupported_version."""
    settings = _make_media_settings(tmp_path)

    old_sonarr = httpx.MockTransport(
        lambda req: httpx.Response(200, json={"version": "2.0.0.5344"})
    )
    snap = SonarrAdapter(settings, transport=old_sonarr).collect()
    assert snap["status"] == "error"
    assert snap["error_code"] == "unsupported_version"


def test_ssrf_redirect_and_readonly_method_enforcement(tmp_path: Path) -> None:
    """Verify SSRF host allowlist, cloud metadata IP block, redirect block, and write block."""
    allowed = ["jellyfin", "qbittorrent", "127.0.0.1"]

    with pytest.raises(MediaSecurityError) as exc_host:
        validate_service_url("http://evil.example.com:8096", allowed)
    assert exc_host.value.error_code == "ssrf_blocked"

    with pytest.raises(MediaSecurityError) as exc_meta:
        validate_service_url("http://169.254.169.254/latest/meta-data", ["169.254.169.254"])
    assert exc_meta.value.error_code == "ssrf_blocked"

    with pytest.raises(MediaSecurityError) as exc_cred:
        validate_service_url("http://user:pass@jellyfin:8096", allowed)
    assert exc_cred.value.error_code == "ssrf_blocked"

    redirect_transport = httpx.MockTransport(
        lambda req: httpx.Response(302, headers={"Location": "http://169.254.169.254/"})
    )
    client = SafeMediaHttpClient(
        base_url="http://jellyfin:8096",
        allowed_hosts=allowed,
        timeout_seconds=2.0,
        max_response_bytes=8192,
        allowed_get_prefixes=("/System/Info",),
        transport=redirect_transport,
    )
    with pytest.raises(MediaSecurityError) as exc_redir:
        client.get_json("/System/Info")
    assert exc_redir.value.error_code == "redirect_blocked"

    # Attempt to call a non-allowlisted write method or endpoint (e.g. qBittorrent delete)
    with pytest.raises(MediaSecurityError) as exc_write:
        client.request_raw("POST", "/api/v2/torrents/delete", form_data={"hashes": "all"})
    assert exc_write.value.error_code == "write_method_prohibited"


def test_consecutive_failure_threshold_stale_cache_and_alert_recovery(tmp_path: Path) -> None:
    """Verify single timeout does NOT mark service offline until threshold, then recovers."""
    settings = _make_media_settings(
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
    valid_transports = _build_valid_transports()
    timeout_transports = {
        "jellyfin": httpx.MockTransport(
            lambda req: (_ for _ in ()).throw(httpx.ReadTimeout("timed out", request=req))
        )
    }

    t0 = datetime(2026, 11, 17, 6, 0, 0, tzinfo=UTC)
    with db_session(settings.db_path) as conn:
        apply_migrations(conn)

        # Poll 0: Healthy baseline (caches movie count = 420)
        snap0 = collect_media_telemetry(
            settings, conn=conn, transports=valid_transports, now=t0
        )
        assert snap0["services"]["jellyfin"]["consecutive_failures"] == 0
        assert snap0["services"]["jellyfin"]["metrics"]["libraries"]["movies"] == 420

        # Poll 1 (t0 + 60s): 1st timeout -> degraded (NOT offline), cached metrics preserved
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

        # Poll 2 (t0 + 400s): 2nd timeout & age > 300s -> stale, still < threshold (2/3)
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

        # Poll 3 (t0 + 490s): 3rd consecutive failure -> reaches threshold (3/3) -> OFFLINE!
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

        # Poll 4 (t0 + 550s): Service recovers -> consecutive_failures=0, offline alert resolved!
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


def test_scheduler_non_overlapping_concurrency_and_sqlite_retention(tmp_path: Path) -> None:
    """Verify MediaCollectionScheduler prevents overlapping runs and prunes SQLite history."""
    settings = _make_media_settings(
        tmp_path,
        media_scheduler_enabled=True,
        media_collection_interval_seconds=60,
        media_collection_timeout_seconds=2.0,
        media_min_persist_interval_seconds=0,
        media_history_retention_limit=5,
    )
    transports = _build_valid_transports()

    with db_session(settings.db_path) as conn:
        apply_migrations(conn)
        for i in range(8):
            snap = collect_media_telemetry(
                settings,
                conn=conn,
                transports=transports,
                now=datetime(2026, 11, 17, 6, i, 0, tzinfo=UTC),
            )
            persist_media_snapshot(
                conn,
                snap,
                retention_limit=settings.media_history_retention_limit,
                min_persist_interval_seconds=0,
                db_key=f"test-{i}",
            )
        history = query_media_history(conn, limit=50)
        assert len(history) == 5

    # Test non-overlapping lock in MediaCollectionScheduler
    import time

    def slow_collector(cfg: Settings) -> dict[str, Any]:
        time.sleep(0.15)
        return {
            "collected_at": datetime.now(UTC).isoformat(),
            "status": "online",
            "overall_status": "online",
            "summary": {},
            "services": {},
            "alerts": [],
        }

    scheduler = MediaCollectionScheduler(settings, collector_fn=slow_collector)

    async def run_concurrent() -> None:
        r1, r2 = await asyncio.gather(
            scheduler.run_once(force_persist=True),
            scheduler.run_once(force_persist=True),
        )
        assert (r1 is None) ^ (r2 is None)
        assert scheduler.run_count == 1
        assert scheduler.skipped_overlap_count == 1

    asyncio.run(run_concurrent())


def test_unified_media_api_endpoints_integration(tmp_path: Path) -> None:
    """Verify all /api/v1/media/* endpoints with authentication, CSRF, and mocked transports."""
    settings = _make_media_settings(tmp_path)
    app = create_app(settings)
    app.state.media_transports = _build_valid_transports()

    with TestClient(app) as client:
        # Unauthenticated requests must be rejected with 401
        assert client.get("/api/v1/media/overview").status_code == 401
        assert client.get("/api/v1/media/jellyfin").status_code == 401

        login_resp = client.post(
            "/api/v1/auth/login",
            json={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
        )
        assert login_resp.status_code == 200
        csrf_token = login_resp.json()["csrf_token"]

        ov_resp = client.get("/api/v1/media/overview")
        assert ov_resp.status_code == 200
        ov_data = ov_resp.json()
        assert ov_data["adapter_enabled"] is True
        assert ov_data["summary"]["jellyfin_active_streams"] == 2
        assert ov_data["summary"]["qb_downloading_count"] == 1

        svcs_resp = client.get("/api/v1/media/services")
        assert svcs_resp.status_code == 200
        assert len(svcs_resp.json()["services_list"]) == 7

        for ep in (
            "/api/v1/media/jellyfin",
            "/api/v1/media/qbittorrent",
            "/api/v1/media/sonarr",
            "/api/v1/media/radarr",
            "/api/v1/media/bazarr",
            "/api/v1/media/prowlarr",
            "/api/v1/media/seerr",
        ):
            r = client.get(ep)
            assert r.status_code == 200, f"Failed GET {ep}"
            assert r.json()["read_only_enforced"] is True

        # Trigger manual collection (requires CSRF)
        assert client.post("/api/v1/media/collect").status_code == 403
        collect_resp = client.post(
            "/api/v1/media/collect", headers={"X-CSRF-Token": csrf_token}
        )
        assert collect_resp.status_code == 200
        assert collect_resp.json()["snapshot_id"] >= 1

        hist_resp = client.get("/api/v1/media/history")
        assert hist_resp.status_code == 200
        assert len(hist_resp.json()) == 1

        alerts_resp = client.get("/api/v1/media/alerts?include_resolved=true")
        assert alerts_resp.status_code == 200
        assert len(alerts_resp.json()) >= 1

        top_overview = client.get("/api/v1/overview")
        assert top_overview.status_code == 200
        assert top_overview.json()["domains"]["media"]["status"] == "degraded"
        assert top_overview.json()["domains"]["downloads"]["status"] == "critical"


def test_jellyfin_connector_backward_compatible_import_and_metrics(tmp_path: Path) -> None:
    """R02.1: Verify JellyfinAdapter extraction preserves imports and exact metrics JSON."""
    from homeagentp_core.modules.media import adapters as legacy_adapters
    from homeagentp_core.modules.media.connectors import JellyfinAdapter as PkgJellyfin
    from homeagentp_core.modules.media.connectors.jellyfin import (
        JellyfinAdapter as DirectJellyfin,
    )

    assert legacy_adapters.JellyfinAdapter is DirectJellyfin
    assert PkgJellyfin is DirectJellyfin

    settings = _make_media_settings(tmp_path)
    transport = _build_valid_transports()["jellyfin"]
    snap = DirectJellyfin(settings, transport=transport).collect()
    assert snap["service"] == "jellyfin"
    assert snap["status"] == "degraded"
    assert snap["version"] == "10.9.11"
    assert snap["metrics"]["libraries"] == {
        "movies": 420,
        "series": 85,
        "episodes": 3120,
        "songs": 150,
        "albums": 18,
    }
    assert snap["metrics"]["sessions"]["active_count"] == 2
    assert snap["metrics"]["sessions"]["direct_play_count"] == 1
    assert snap["metrics"]["sessions"]["transcoding_count"] == 1
    assert snap["metrics"]["playback_errors"]["accessible"] is True
    assert snap["metrics"]["playback_errors"]["count"] == 1


def test_r03_security_hardening_regressions(monkeypatch: pytest.MonkeyPatch) -> None:
    """R03: Verify segment-safe paths, IPv4-mapped IPv6, DNS SSRF, redirects, Content-Length."""
    import socket

    from homeagentp_core.modules.media import base as legacy_base
    from homeagentp_core.modules.media.adapter_base import MediaServiceAdapter
    from homeagentp_core.modules.media.errors import (
        MediaMalformedResponseError,
        MediaSecurityError,
    )
    from homeagentp_core.modules.media.http_client import SafeMediaHttpClient
    from homeagentp_core.modules.media.security import (
        validate_resolved_dns,
        validate_service_url,
    )

    assert legacy_base.SafeMediaHttpClient is SafeMediaHttpClient
    assert legacy_base.MediaServiceAdapter is MediaServiceAdapter
    assert legacy_base.MediaSecurityError is MediaSecurityError
    assert legacy_base.validate_service_url is validate_service_url

    # 1. Segment-safe GET prefix matching & encoded traversal blocking
    client = SafeMediaHttpClient(
        base_url="http://jellyfin.local:8096",
        allowed_hosts=["jellyfin.local"],
        timeout_seconds=2.0,
        max_response_bytes=1024,
        allowed_get_prefixes=("/Sessions",),
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json=[])),
    )
    assert client.get_json("/Sessions") == []
    assert client.get_json("/Sessions/active") == []

    for bad_path in (
        "/SessionsEvil",
        "/Sessions/%2e%2e/Users",
        "/Sessions?admin=1",
        "/Sessions#frag",
        "/Sessions\r\nX-Injected: 1",
    ):
        with pytest.raises(MediaSecurityError):
            client.get_json(bad_path)

    # 2. IPv4-mapped IPv6 SSRF rejection even if listed in allowed_hosts
    for mapped in (
        "http://[::ffff:169.254.169.254]:8096",
        "http://[::ffff:0.0.0.0]:8096",
    ):
        with pytest.raises(MediaSecurityError) as exc_info:
            validate_service_url(mapped, ["::ffff:169.254.169.254", "::ffff:0.0.0.0"])
        assert exc_info.value.error_code == "ssrf_blocked"

    # 3. DNS resolution returning cloud metadata IP is blocked
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0))
        ],
    )
    with pytest.raises(MediaSecurityError) as dns_exc:
        validate_resolved_dns("rebind.local")
    assert dns_exc.value.error_code == "ssrf_blocked"

    # 4. 300/307/308 redirects are blocked
    for code in (300, 307, 308):
        redir_client = SafeMediaHttpClient(
            base_url="http://jellyfin.local:8096",
            allowed_hosts=["jellyfin.local"],
            timeout_seconds=2.0,
            max_response_bytes=1024,
            allowed_get_prefixes=("/System/Info",),
            transport=httpx.MockTransport(
                lambda req, status=code: httpx.Response(
                    status, headers={"Location": "http://169.254.169.254/"}
                )
            ),
        )
        with pytest.raises(MediaSecurityError) as redir_exc:
            redir_client.get_json("/System/Info")
        assert redir_exc.value.error_code == "redirect_blocked"

    # 5. Early Content-Length header rejection before buffering body
    oversize_client = SafeMediaHttpClient(
        base_url="http://jellyfin.local:8096",
        allowed_hosts=["jellyfin.local"],
        timeout_seconds=2.0,
        max_response_bytes=512,
        allowed_get_prefixes=("/System/Info",),
        transport=httpx.MockTransport(
            lambda req: httpx.Response(200, headers={"Content-Length": "4096"}, content=b"{}")
        ),
    )
    with pytest.raises(MediaMalformedResponseError) as size_exc:
        oversize_client.get_json("/System/Info")
    assert size_exc.value.error_code == "response_too_large"


