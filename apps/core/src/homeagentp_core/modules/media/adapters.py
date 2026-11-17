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
from homeagentp_core.modules.media.connectors.jellyfin import (
    JellyfinAdapter as JellyfinAdapter,
)
from homeagentp_core.modules.media.connectors.qbittorrent import (
    QBITTORRENT_CREDENTIAL_NOTICE as QBITTORRENT_CREDENTIAL_NOTICE,
)
from homeagentp_core.modules.media.connectors.qbittorrent import (
    QBittorrentAdapter as QBittorrentAdapter,
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


class _ArrV3BaseAdapter(MediaServiceAdapter):
    """Shared read-only logic for Sonarr v3 and Radarr v3 adapters."""

    item_endpoint: str
    item_label_plural: str

    ALLOWED_GET_PREFIXES = (
        "/api/v3/system/status",
        "/api/v3/health",
        "/api/v3/series",
        "/api/v3/movie",
        "/api/v3/queue",
        "/api/v3/wanted/missing",
        "/api/v3/diskspace",
    )

    def _poll_arr_v3(
        self,
        *,
        base_url: str,
        api_key: str,
        now_iso: str,
    ) -> tuple[str, str | None, dict[str, Any], list[dict[str, Any]], str]:
        client = SafeMediaHttpClient(
            base_url=base_url,
            allowed_hosts=self._settings.media_allowed_hosts,
            timeout_seconds=self._settings.media_http_timeout_seconds,
            max_response_bytes=self._settings.media_max_response_bytes,
            allowed_get_prefixes=self.ALLOWED_GET_PREFIXES,
            default_headers={
                "X-Api-Key": api_key.strip(),
                "Accept": "application/json",
            },
            transport=self._transport,
        )

        sys_status = _require_dict(
            client.get_json("/api/v3/system/status"),
            f"{self.title} /api/v3/system/status",
        )
        version = str(sys_status.get("version") or "").strip()
        if not version:
            raise MediaMalformedResponseError(
                f"{self.title} /api/v3/system/status missing 'version' field."
            )
        check_semver_major(version, min_major=3, service_label=self.title)

        health_items = _require_list(
            client.get_json("/api/v3/health"), f"{self.title} /api/v3/health"
        )
        catalog_items = _require_list(
            client.get_json(self.item_endpoint), f"{self.title} {self.item_endpoint}"
        )
        queue_payload = _require_dict(
            client.get_json("/api/v3/queue", params={"page": 1, "pageSize": 50}),
            f"{self.title} /api/v3/queue",
        )
        missing_payload = _require_dict(
            client.get_json(
                "/api/v3/wanted/missing",
                params={"page": 1, "pageSize": 1, "monitored": "true"},
            ),
            f"{self.title} /api/v3/wanted/missing",
        )

        diskspace_list: list[dict[str, Any]] = []
        try:
            raw_disks = client.get_json("/api/v3/diskspace")
            if isinstance(raw_disks, list):
                for d in raw_disks[:10]:
                    if isinstance(d, dict):
                        diskspace_list.append(
                            {
                                "path": str(d.get("path") or ""),
                                "label": str(d.get("label") or ""),
                                "free_bytes": (
                                    int(d["freeSpace"])
                                    if isinstance(d.get("freeSpace"), int)
                                    else None
                                ),
                                "total_bytes": (
                                    int(d["totalSpace"])
                                    if isinstance(d.get("totalSpace"), int)
                                    else None
                                ),
                            }
                        )
        except Exception:
            diskspace_list = []

        total_items = 0
        monitored_items = 0
        episode_or_file_count = 0
        size_on_disk_bytes = 0
        for entry in catalog_items:
            if not isinstance(entry, dict):
                continue
            total_items += 1
            if entry.get("monitored"):
                monitored_items += 1
            if self.service_name == "sonarr":
                stats = _opt_dict(entry.get("statistics"))
                episode_or_file_count += int(stats.get("episodeFileCount", 0) or 0)
                size_on_disk_bytes += int(stats.get("sizeOnDisk", 0) or 0)
            else:
                if entry.get("hasFile"):
                    episode_or_file_count += 1
                size_on_disk_bytes += int(entry.get("sizeOnDisk", 0) or 0)

        queue_records = _opt_list(queue_payload.get("records"))
        queue_total = int(queue_payload.get("totalRecords", len(queue_records)) or 0)
        queue_items: list[dict[str, Any]] = []
        failed_imports: list[dict[str, Any]] = []

        for q in queue_records[:20]:
            if not isinstance(q, dict):
                continue
            q_title = str(q.get("title") or "Unknown")
            q_status = str(q.get("status") or "unknown")
            tracked_status = str(q.get("trackedDownloadStatus") or "ok").lower()
            tracked_state = str(q.get("trackedDownloadState") or "").lower()
            err_msg = str(q.get("errorMessage") or "").strip()
            status_msgs = q.get("statusMessages")
            messages_flat: list[str] = []
            if isinstance(status_msgs, list):
                for sm in status_msgs:
                    if isinstance(sm, dict) and isinstance(sm.get("messages"), list):
                        messages_flat.extend(str(m) for m in sm["messages"])

            is_failed = (
                tracked_status in {"warning", "error"}
                or q_status.lower() in {"failed", "warning"}
                or tracked_state in {"importblocked", "importfailed", "failedpending"}
                or bool(err_msg)
            )
            item_summary = {
                "id": int(q.get("id", 0) or 0),
                "title": q_title,
                "status": q_status,
                "tracked_download_status": tracked_status,
                "tracked_download_state": tracked_state,
                "error_message": err_msg or ("; ".join(messages_flat) if messages_flat else ""),
                "protocol": str(q.get("protocol") or ""),
                "download_client": str(q.get("downloadClient") or ""),
            }
            queue_items.append(item_summary)
            if is_failed:
                failed_imports.append(item_summary)

        health_warnings: list[dict[str, str]] = []
        has_health_error = False
        for h in health_items:
            if not isinstance(h, dict):
                continue
            h_type = str(h.get("type") or "warning").lower()
            if h_type == "error":
                has_health_error = True
            health_warnings.append(
                {
                    "source": str(h.get("source") or "system"),
                    "type": h_type,
                    "message": str(h.get("message") or ""),
                }
            )

        missing_count = int(missing_payload.get("totalRecords", 0) or 0)

        alerts: list[dict[str, Any]] = []
        svc_status = "online"
        reason = f"{self.title} API v3 online."

        if failed_imports:
            svc_status = "degraded"
            reason = f"{self.title} has {len(failed_imports)} queue import/download failure(s)."
            alerts.append(
                {
                    "alert_key": f"{self.service_name}:queue.import_failed",
                    "code": "queue.import_failed",
                    "severity": "warning",
                    "category": "media",
                    "service": self.service_name,
                    "target": failed_imports[0]["title"],
                    "message": (
                        f"{self.title} queue has {len(failed_imports)} item(s) with "
                        f"import/download warnings or errors "
                        f"(first: {failed_imports[0]['title']})."
                    ),
                    "metric_value": float(len(failed_imports)),
                    "threshold_value": 1.0,
                    "details": {"failed_items": failed_imports[:5]},
                    "status": "active",
                    "created_at": now_iso,
                }
            )

        if health_warnings:
            if has_health_error:
                svc_status = "critical"
            elif svc_status == "online":
                svc_status = "degraded"
            reason = f"{self.title} reported {len(health_warnings)} health issue(s)."
            alerts.append(
                {
                    "alert_key": f"{self.service_name}:health.issue",
                    "code": "health.issue",
                    "severity": "critical" if has_health_error else "warning",
                    "category": "media",
                    "service": self.service_name,
                    "target": self.service_name,
                    "message": (
                        f"{self.title} health check: {health_warnings[0]['message']}"
                    ),
                    "metric_value": float(len(health_warnings)),
                    "threshold_value": 1.0,
                    "details": {"health_warnings": health_warnings[:5]},
                    "status": "active",
                    "created_at": now_iso,
                }
            )

        metrics: dict[str, Any] = {
            "total_count": total_items,
            "monitored_count": monitored_items,
            "available_file_count": episode_or_file_count,
            "size_on_disk_bytes": size_on_disk_bytes,
            "missing_count": missing_count,
            "queue_total": queue_total,
            "queue_failed_count": len(failed_imports),
            "queue_items": queue_items[:10],
            "failed_imports": failed_imports[:10],
            "health_warnings": health_warnings,
            "diskspace": diskspace_list,
        }
        return svc_status, version, metrics, alerts, reason


class SonarrAdapter(_ArrV3BaseAdapter):
    """Read-only Sonarr API v3 adapter."""

    service_name = "sonarr"
    title = "Sonarr TV PVR"
    category: Literal["media", "downloads"] = "media"
    item_endpoint = "/api/v3/series"
    item_label_plural = "series"

    def is_configured(self) -> tuple[bool, str]:
        if not self._settings.sonarr_url.strip():
            return False, "HOMEAGENTP_SONARR_URL is not configured."
        if not self._settings.sonarr_api_key.strip():
            return False, "HOMEAGENTP_SONARR_API_KEY is not configured."
        return True, ""

    def _empty_metrics(self) -> dict[str, Any]:
        return {
            "total_count": None,
            "monitored_count": None,
            "available_file_count": None,
            "size_on_disk_bytes": None,
            "missing_count": None,
            "queue_total": 0,
            "queue_failed_count": 0,
            "queue_items": [],
            "failed_imports": [],
            "health_warnings": [],
            "diskspace": [],
        }

    def _poll_live(
        self, now_iso: str
    ) -> tuple[str, str | None, dict[str, Any], list[dict[str, Any]], str]:
        return self._poll_arr_v3(
            base_url=self._settings.sonarr_url,
            api_key=self._settings.sonarr_api_key,
            now_iso=now_iso,
        )


class RadarrAdapter(_ArrV3BaseAdapter):
    """Read-only Radarr API v3 adapter."""

    service_name = "radarr"
    title = "Radarr Movie PVR"
    category: Literal["media", "downloads"] = "media"
    item_endpoint = "/api/v3/movie"
    item_label_plural = "movies"

    def is_configured(self) -> tuple[bool, str]:
        if not self._settings.radarr_url.strip():
            return False, "HOMEAGENTP_RADARR_URL is not configured."
        if not self._settings.radarr_api_key.strip():
            return False, "HOMEAGENTP_RADARR_API_KEY is not configured."
        return True, ""

    def _empty_metrics(self) -> dict[str, Any]:
        return {
            "total_count": None,
            "monitored_count": None,
            "available_file_count": None,
            "size_on_disk_bytes": None,
            "missing_count": None,
            "queue_total": 0,
            "queue_failed_count": 0,
            "queue_items": [],
            "failed_imports": [],
            "health_warnings": [],
            "diskspace": [],
        }

    def _poll_live(
        self, now_iso: str
    ) -> tuple[str, str | None, dict[str, Any], list[dict[str, Any]], str]:
        return self._poll_arr_v3(
            base_url=self._settings.radarr_url,
            api_key=self._settings.radarr_api_key,
            now_iso=now_iso,
        )


class BazarrAdapter(MediaServiceAdapter):
    """Read-only Bazarr subtitle manager adapter (/api/system/status, /health, /badges)."""

    service_name = "bazarr"
    title = "Bazarr Subtitles"
    category: Literal["media", "downloads"] = "media"

    ALLOWED_GET_PREFIXES = (
        "/api/system/status",
        "/api/system/health",
        "/api/badges",
    )

    def is_configured(self) -> tuple[bool, str]:
        if not self._settings.bazarr_url.strip():
            return False, "HOMEAGENTP_BAZARR_URL is not configured."
        if not self._settings.bazarr_api_key.strip():
            return False, "HOMEAGENTP_BAZARR_API_KEY is not configured."
        return True, ""

    def _empty_metrics(self) -> dict[str, Any]:
        return {
            "missing_episode_subtitles": None,
            "missing_movie_subtitles": None,
            "unhealthy_providers_count": 0,
            "sonarr_signalr": None,
            "radarr_signalr": None,
            "health_issues": [],
        }

    def _poll_live(
        self, now_iso: str
    ) -> tuple[str, str | None, dict[str, Any], list[dict[str, Any]], str]:
        client = SafeMediaHttpClient(
            base_url=self._settings.bazarr_url,
            allowed_hosts=self._settings.media_allowed_hosts,
            timeout_seconds=self._settings.media_http_timeout_seconds,
            max_response_bytes=self._settings.media_max_response_bytes,
            allowed_get_prefixes=self.ALLOWED_GET_PREFIXES,
            default_headers={
                "X-API-KEY": self._settings.bazarr_api_key.strip(),
                "Accept": "application/json",
            },
            transport=self._transport,
        )

        status_raw = _require_dict(
            client.get_json("/api/system/status"), "Bazarr /api/system/status"
        )
        nested_data = _opt_dict(status_raw.get("data"))
        status_data = nested_data if nested_data else status_raw
        version = str(status_data.get("bazarr_version") or "").strip()
        if not version:
            raise MediaMalformedResponseError(
                "Bazarr /api/system/status missing 'bazarr_version' field."
            )
        check_semver_major(version, min_major=1, service_label="Bazarr")

        badges = _require_dict(client.get_json("/api/badges"), "Bazarr /api/badges")
        if "episodes" not in badges and "movies" not in badges:
            raise MediaMalformedResponseError(
                "Bazarr /api/badges missing 'episodes' and 'movies' fields."
            )

        health_raw = client.get_json("/api/system/health")
        health_list_raw: list[Any] = []
        if isinstance(health_raw, dict) and isinstance(health_raw.get("data"), list):
            health_list_raw = health_raw["data"]
        elif isinstance(health_raw, list):
            health_list_raw = health_raw

        health_issues: list[dict[str, str]] = []
        for item in health_list_raw:
            if isinstance(item, dict):
                health_issues.append(
                    {
                        "object": str(item.get("object") or "Bazarr"),
                        "issue": str(item.get("issue") or ""),
                    }
                )

        missing_ep = int(badges.get("episodes", 0) or 0)
        missing_mv = int(badges.get("movies", 0) or 0)
        provider_issues = int(badges.get("providers", 0) or 0)

        alerts: list[dict[str, Any]] = []
        svc_status = "online"
        reason = "Bazarr subtitle API online."

        if health_issues or provider_issues > 0:
            svc_status = "degraded"
            reason = (
                f"Bazarr reported {len(health_issues)} health issue(s) and "
                f"{provider_issues} throttled/failing subtitle provider(s)."
            )
            alerts.append(
                {
                    "alert_key": "bazarr:health.issue",
                    "code": "health.issue",
                    "severity": "warning",
                    "category": "media",
                    "service": "bazarr",
                    "target": "bazarr",
                    "message": (
                        health_issues[0]["issue"]
                        if health_issues
                        else f"{provider_issues} subtitle provider(s) degraded."
                    ),
                    "metric_value": float(len(health_issues) + provider_issues),
                    "threshold_value": 1.0,
                    "details": {
                        "health_issues": health_issues[:5],
                        "unhealthy_providers_count": provider_issues,
                    },
                    "status": "active",
                    "created_at": now_iso,
                }
            )

        metrics = {
            "missing_episode_subtitles": missing_ep,
            "missing_movie_subtitles": missing_mv,
            "unhealthy_providers_count": provider_issues,
            "sonarr_signalr": str(badges.get("sonarr_signalr") or ""),
            "radarr_signalr": str(badges.get("radarr_signalr") or ""),
            "health_issues": health_issues,
        }
        return svc_status, version, metrics, alerts, reason


class ProwlarrAdapter(MediaServiceAdapter):
    """Read-only Prowlarr API v1 adapter (/api/v1/system/status, /health, /indexer)."""

    service_name = "prowlarr"
    title = "Prowlarr Indexer Manager"
    category: Literal["media", "downloads"] = "media"

    ALLOWED_GET_PREFIXES = (
        "/api/v1/system/status",
        "/api/v1/health",
        "/api/v1/indexer",
        "/api/v1/indexerstatus",
    )

    def is_configured(self) -> tuple[bool, str]:
        if not self._settings.prowlarr_url.strip():
            return False, "HOMEAGENTP_PROWLARR_URL is not configured."
        if not self._settings.prowlarr_api_key.strip():
            return False, "HOMEAGENTP_PROWLARR_API_KEY is not configured."
        return True, ""

    def _empty_metrics(self) -> dict[str, Any]:
        return {
            "total_indexers": None,
            "enabled_indexers": None,
            "failing_indexers_count": 0,
            "failing_indexers": [],
            "health_warnings": [],
        }

    def _poll_live(
        self, now_iso: str
    ) -> tuple[str, str | None, dict[str, Any], list[dict[str, Any]], str]:
        client = SafeMediaHttpClient(
            base_url=self._settings.prowlarr_url,
            allowed_hosts=self._settings.media_allowed_hosts,
            timeout_seconds=self._settings.media_http_timeout_seconds,
            max_response_bytes=self._settings.media_max_response_bytes,
            allowed_get_prefixes=self.ALLOWED_GET_PREFIXES,
            default_headers={
                "X-Api-Key": self._settings.prowlarr_api_key.strip(),
                "Accept": "application/json",
            },
            transport=self._transport,
        )

        sys_status = _require_dict(
            client.get_json("/api/v1/system/status"), "Prowlarr /api/v1/system/status"
        )
        version = str(sys_status.get("version") or "").strip()
        if not version:
            raise MediaMalformedResponseError(
                "Prowlarr /api/v1/system/status missing 'version' field."
            )
        check_semver_major(version, min_major=1, service_label="Prowlarr")

        indexers = _require_list(
            client.get_json("/api/v1/indexer"), "Prowlarr /api/v1/indexer"
        )
        indexer_statuses = _require_list(
            client.get_json("/api/v1/indexerstatus"), "Prowlarr /api/v1/indexerstatus"
        )
        health_raw = _require_list(
            client.get_json("/api/v1/health"), "Prowlarr /api/v1/health"
        )

        indexer_name_by_id: dict[int, str] = {}
        total_idx = 0
        enabled_idx = 0
        for idx in indexers:
            if not isinstance(idx, dict):
                continue
            total_idx += 1
            if idx.get("enable"):
                enabled_idx += 1
            if isinstance(idx.get("id"), int):
                indexer_name_by_id[int(idx["id"])] = str(idx.get("name") or f"Indexer #{idx['id']}")

        failing_indexers: list[dict[str, Any]] = []
        for st in indexer_statuses:
            if not isinstance(st, dict):
                continue
            idx_id = int(st.get("indexerId", 0) or 0)
            disabled_till = st.get("disabledTill")
            most_recent_failure = st.get("mostRecentFailure")
            if disabled_till or most_recent_failure:
                failing_indexers.append(
                    {
                        "indexer_id": idx_id,
                        "name": indexer_name_by_id.get(idx_id, f"Indexer #{idx_id}"),
                        "disabled_till": str(disabled_till or ""),
                        "most_recent_failure": str(most_recent_failure or ""),
                    }
                )

        health_warnings: list[dict[str, str]] = []
        for h in health_raw:
            if isinstance(h, dict):
                health_warnings.append(
                    {
                        "source": str(h.get("source") or "Prowlarr"),
                        "type": str(h.get("type") or "warning").lower(),
                        "message": str(h.get("message") or ""),
                    }
                )

        alerts: list[dict[str, Any]] = []
        svc_status = "online"
        reason = "Prowlarr API v1 online."

        if failing_indexers:
            svc_status = "degraded"
            reason = f"Prowlarr has {len(failing_indexers)} failing/disabled indexer(s)."
            alerts.append(
                {
                    "alert_key": "prowlarr:indexer.failing",
                    "code": "indexer.failing",
                    "severity": "warning",
                    "category": "media",
                    "service": "prowlarr",
                    "target": failing_indexers[0]["name"],
                    "message": (
                        f"{len(failing_indexers)} Prowlarr indexer(s) failing or temporarily "
                        f"disabled (first: {failing_indexers[0]['name']})."
                    ),
                    "metric_value": float(len(failing_indexers)),
                    "threshold_value": 1.0,
                    "details": {"failing_indexers": failing_indexers[:10]},
                    "status": "active",
                    "created_at": now_iso,
                }
            )

        if health_warnings:
            if svc_status == "online":
                svc_status = "degraded"
                reason = f"Prowlarr reported {len(health_warnings)} health warning(s)."
            alerts.append(
                {
                    "alert_key": "prowlarr:health.issue",
                    "code": "health.issue",
                    "severity": "warning",
                    "category": "media",
                    "service": "prowlarr",
                    "target": "prowlarr",
                    "message": f"Prowlarr health: {health_warnings[0]['message']}",
                    "metric_value": float(len(health_warnings)),
                    "threshold_value": 1.0,
                    "details": {"health_warnings": health_warnings[:5]},
                    "status": "active",
                    "created_at": now_iso,
                }
            )

        metrics = {
            "total_indexers": total_idx,
            "enabled_indexers": enabled_idx,
            "failing_indexers_count": len(failing_indexers),
            "failing_indexers": failing_indexers[:10],
            "health_warnings": health_warnings,
        }
        return svc_status, version, metrics, alerts, reason


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
