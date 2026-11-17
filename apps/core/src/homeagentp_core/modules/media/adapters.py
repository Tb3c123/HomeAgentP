"""Read-only connectors for Jellyfin, qBittorrent, Sonarr, Radarr, Bazarr, Prowlarr, and Seerr.

All adapters inherit from `MediaServiceAdapter` and use `SafeMediaHttpClient` with strict
endpoint allowlists, SSRF protection, redirect blocking, response size limits, and zero write calls.
"""

from __future__ import annotations

from typing import Any, Literal

import httpx

from homeagentp_core.config import Settings
from homeagentp_core.modules.media.base import (
    MediaMalformedResponseError,
    MediaServiceAdapter,
    SafeMediaHttpClient,
    check_semver_major,
)
from homeagentp_core.modules.media.connectors.arr_common import (
    _ArrV3BaseAdapter as _ArrV3BaseAdapter,
)
from homeagentp_core.modules.media.connectors.bazarr import (
    BazarrAdapter as BazarrAdapter,
)
from homeagentp_core.modules.media.connectors.jellyfin import (
    JellyfinAdapter as JellyfinAdapter,
)
from homeagentp_core.modules.media.connectors.prowlarr import (
    ProwlarrAdapter as ProwlarrAdapter,
)
from homeagentp_core.modules.media.connectors.qbittorrent import (
    QBITTORRENT_CREDENTIAL_NOTICE as QBITTORRENT_CREDENTIAL_NOTICE,
)
from homeagentp_core.modules.media.connectors.qbittorrent import (
    QBittorrentAdapter as QBittorrentAdapter,
)
from homeagentp_core.modules.media.connectors.radarr import (
    RadarrAdapter as RadarrAdapter,
)
from homeagentp_core.modules.media.connectors.sonarr import (
    SonarrAdapter as SonarrAdapter,
)


def _require_dict(payload: Any, context: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise MediaMalformedResponseError(
            f"Expected JSON object from {context}, got {type(payload).__name__}."
        )
    return payload


def _require_list(payload: Any, context: str) -> list[Any]:
    if not isinstance(payload, list):
        raise MediaMalformedResponseError(
            f"Expected JSON array from {context}, got {type(payload).__name__}."
        )
    return payload


def _opt_dict(val: Any) -> dict[str, Any]:
    return val if isinstance(val, dict) else {}


def _opt_list(val: Any) -> list[Any]:
    return val if isinstance(val, list) else []


class SeerrAdapter(MediaServiceAdapter):
    """Read-only Seerr (Jellyseerr / Overseerr) API v1 adapter."""

    service_name = "seerr"
    title = "Seerr Media Requests"
    category: Literal["media", "downloads"] = "media"

    ALLOWED_GET_PREFIXES = (
        "/api/v1/status",
        "/api/v1/request/count",
        "/api/v1/request",
    )

    REQUEST_STATUS_MAP = {
        1: "pending",
        2: "approved",
        3: "declined",
        4: "failed",
    }

    def is_configured(self) -> tuple[bool, str]:
        if not self._settings.seerr_url.strip():
            return False, "HOMEAGENTP_SEERR_URL is not configured."
        if not self._settings.seerr_api_key.strip():
            return False, "HOMEAGENTP_SEERR_API_KEY is not configured."
        return True, ""

    def _empty_metrics(self) -> dict[str, Any]:
        return {
            "update_available": None,
            "commits_behind": None,
            "requests": {
                "total": None,
                "movie": None,
                "tv": None,
                "pending": None,
                "approved": None,
                "processing": None,
                "available": None,
                "declined": None,
            },
            "recent_requests": [],
        }

    def _poll_live(
        self, now_iso: str
    ) -> tuple[str, str | None, dict[str, Any], list[dict[str, Any]], str]:
        client = SafeMediaHttpClient(
            base_url=self._settings.seerr_url,
            allowed_hosts=self._settings.media_allowed_hosts,
            timeout_seconds=self._settings.media_http_timeout_seconds,
            max_response_bytes=self._settings.media_max_response_bytes,
            allowed_get_prefixes=self.ALLOWED_GET_PREFIXES,
            default_headers={
                "X-Api-Key": self._settings.seerr_api_key.strip(),
                "Accept": "application/json",
            },
            transport=self._transport,
        )

        status_payload = _require_dict(
            client.get_json("/api/v1/status"), "Seerr /api/v1/status"
        )
        version = str(status_payload.get("version") or "").strip()
        if not version:
            raise MediaMalformedResponseError("Seerr /api/v1/status missing 'version' field.")
        check_semver_major(version, min_major=1, service_label="Seerr")

        counts = _require_dict(
            client.get_json("/api/v1/request/count"), "Seerr /api/v1/request/count"
        )
        if "pending" not in counts and "total" not in counts:
            raise MediaMalformedResponseError(
                "Seerr /api/v1/request/count missing 'pending' and 'total' fields."
            )

        recent_list: list[dict[str, Any]] = []
        try:
            req_page = _require_dict(
                client.get_json(
                    "/api/v1/request",
                    params={"take": 10, "skip": 0, "sort": "added"},
                ),
                "Seerr /api/v1/request",
            )
            results = _opt_list(req_page.get("results"))
            for item in results[:10]:
                if not isinstance(item, dict):
                    continue
                st_code = int(item.get("status", 0) or 0)
                req_by = _opt_dict(item.get("requestedBy"))
                media_obj = _opt_dict(item.get("media"))
                recent_list.append(
                    {
                        "id": int(item.get("id", 0) or 0),
                        "media_type": str(item.get("type") or "unknown"),
                        "status": self.REQUEST_STATUS_MAP.get(st_code, "unknown"),
                        "requested_by": str(
                            req_by.get("displayName")
                            or req_by.get("email")
                            or "user"
                        ),
                        "tmdb_id": (
                            int(media_obj["tmdbId"])
                            if isinstance(media_obj.get("tmdbId"), int)
                            else None
                        ),
                        "created_at": str(item.get("createdAt") or ""),
                    }
                )
        except Exception:
            recent_list = []

        metrics = {
            "update_available": bool(status_payload.get("updateAvailable", False)),
            "commits_behind": int(status_payload.get("commitsBehind", 0) or 0),
            "requests": {
                "total": int(counts.get("total", 0) or 0),
                "movie": int(counts.get("movie", 0) or 0),
                "tv": int(counts.get("tv", 0) or 0),
                "pending": int(counts.get("pending", 0) or 0),
                "approved": int(counts.get("approved", 0) or 0),
                "processing": int(counts.get("processing", 0) or 0),
                "available": int(counts.get("available", 0) or 0),
                "declined": int(counts.get("declined", 0) or 0),
            },
            "recent_requests": recent_list,
        }
        return "online", version, metrics, [], "Seerr API v1 online."


def build_media_adapters(
    settings: Settings,
    *,
    transports: dict[str, httpx.BaseTransport] | None = None,
) -> dict[str, MediaServiceAdapter]:
    """Instantiate all 7 Media & Downloads service adapters in canonical order."""
    t_map = transports or {}
    return {
        "jellyfin": JellyfinAdapter(settings, transport=t_map.get("jellyfin")),
        "qbittorrent": QBittorrentAdapter(settings, transport=t_map.get("qbittorrent")),
        "sonarr": SonarrAdapter(settings, transport=t_map.get("sonarr")),
        "radarr": RadarrAdapter(settings, transport=t_map.get("radarr")),
        "bazarr": BazarrAdapter(settings, transport=t_map.get("bazarr")),
        "prowlarr": ProwlarrAdapter(settings, transport=t_map.get("prowlarr")),
        "seerr": SeerrAdapter(settings, transport=t_map.get("seerr")),
    }
