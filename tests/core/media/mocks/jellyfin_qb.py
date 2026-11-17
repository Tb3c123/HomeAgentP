"""Mocked HTTP transports for Jellyfin and qBittorrent unit/integration tests."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx


def build_jellyfin_transport() -> httpx.MockTransport:
    def handler(req: httpx.Request) -> httpx.Response:
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
                        "NowPlayingItem": {"Name": "Dune: Part Two", "Type": "Movie"},
                        "PlayState": {"PlayMethod": "DirectPlay", "IsPaused": False},
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
                        "PlayState": {"PlayMethod": "Transcode", "IsPaused": False},
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

    return httpx.MockTransport(handler)


def build_qbittorrent_transport() -> httpx.MockTransport:
    now_epoch = int(datetime.now(UTC).timestamp())

    def handler(req: httpx.Request) -> httpx.Response:
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

    return httpx.MockTransport(handler)
