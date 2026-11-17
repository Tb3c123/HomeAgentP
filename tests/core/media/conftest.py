"""Shared fixtures and deterministic mocked transports for Phase 03 Media & Downloads tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from tests.core.conftest import TEST_ADMIN_PASSWORD, TEST_ADMIN_USERNAME, TEST_SECRET_KEY

from homeagentp_core.config import Settings


def make_media_settings(tmp_path: Path, **overrides: Any) -> Settings:
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


def build_valid_transports() -> dict[str, httpx.BaseTransport]:
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
