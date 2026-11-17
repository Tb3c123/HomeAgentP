"""Mocked HTTP transports for Sonarr, Radarr, Bazarr, Prowlarr, and Seerr tests."""

from __future__ import annotations

import httpx


def build_sonarr_transport() -> httpx.MockTransport:
    def handler(req: httpx.Request) -> httpx.Response:
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
                        "statistics": {"episodeFileCount": 9, "sizeOnDisk": 25_000_000_000},
                    },
                    {
                        "id": 2,
                        "title": "Andor",
                        "monitored": True,
                        "statistics": {"episodeFileCount": 12, "sizeOnDisk": 35_000_000_000},
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

    return httpx.MockTransport(handler)


def build_radarr_transport() -> httpx.MockTransport:
    def handler(req: httpx.Request) -> httpx.Response:
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

    return httpx.MockTransport(handler)


def build_bazarr_transport() -> httpx.MockTransport:
    def handler(req: httpx.Request) -> httpx.Response:
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

    return httpx.MockTransport(handler)


def build_prowlarr_transport() -> httpx.MockTransport:
    def handler(req: httpx.Request) -> httpx.Response:
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

    return httpx.MockTransport(handler)


def build_seerr_transport() -> httpx.MockTransport:
    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if path == "/api/v1/status":
            return httpx.Response(
                200,
                json={"version": "1.9.2", "updateAvailable": False, "commitsBehind": 0},
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

    return httpx.MockTransport(handler)
