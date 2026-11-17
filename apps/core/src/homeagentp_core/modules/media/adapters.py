"""Read-only connectors for Jellyfin, qBittorrent, Sonarr, Radarr, Bazarr, Prowlarr, and Seerr.

All adapters inherit from `MediaServiceAdapter` and use `SafeMediaHttpClient` with strict
endpoint allowlists, SSRF protection, redirect blocking, response size limits, and zero write calls.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

import httpx

from homeagentp_core.config import Settings
from homeagentp_core.modules.media.base import (
    MediaAuthError,
    MediaMalformedResponseError,
    MediaServiceAdapter,
    SafeMediaHttpClient,
    check_semver_major,
)
from homeagentp_core.modules.media.connectors.jellyfin import JellyfinAdapter

QBITTORRENT_CREDENTIAL_NOTICE = (
    "qBittorrent Web API sessions possess server-side write capability; "
    "read-only operation is enforced by HomeAgentP's client-side GET endpoint allowlist."
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


class QBittorrentAdapter(MediaServiceAdapter):
    """Read-only qBittorrent Web API v2 adapter with strict GET endpoint allowlist."""

    service_name = "qbittorrent"
    title = "qBittorrent Downloads"
    category: Literal["media", "downloads"] = "downloads"

    ALLOWED_GET_PREFIXES = (
        "/api/v2/app/version",
        "/api/v2/app/webapiVersion",
        "/api/v2/transfer/info",
        "/api/v2/torrents/info",
    )
    ALLOWED_POST_PATHS = ("/api/v2/auth/login",)

    def is_configured(self) -> tuple[bool, str]:
        if not self._settings.qbittorrent_url.strip():
            return False, "HOMEAGENTP_QBITTORRENT_URL is not configured."
        return True, ""

    def _empty_metrics(self) -> dict[str, Any]:
        return {
            "webapi_version": None,
            "connection_status": "unavailable",
            "dht_nodes": None,
            "download_speed_bytes": None,
            "upload_speed_bytes": None,
            "downloaded_session_bytes": None,
            "uploaded_session_bytes": None,
            "counts": {
                "total": 0,
                "downloading": 0,
                "seeding": 0,
                "paused": 0,
                "stalled": 0,
                "stalled_over_threshold": 0,
                "queued": 0,
                "checking": 0,
                "errored": 0,
            },
            "stalled_threshold_seconds": self._settings.qbittorrent_stalled_threshold_seconds,
            "stalled_torrents": [],
            "errored_torrents": [],
            "active_queue": [],
            "credential_scope_notice": QBITTORRENT_CREDENTIAL_NOTICE,
        }

    def _poll_live(
        self, now_iso: str
    ) -> tuple[str, str | None, dict[str, Any], list[dict[str, Any]], str]:
        client = SafeMediaHttpClient(
            base_url=self._settings.qbittorrent_url,
            allowed_hosts=self._settings.media_allowed_hosts,
            timeout_seconds=self._settings.media_http_timeout_seconds,
            max_response_bytes=self._settings.media_max_response_bytes,
            allowed_get_prefixes=self.ALLOWED_GET_PREFIXES,
            allowed_post_paths=self.ALLOWED_POST_PATHS,
            default_headers={"Referer": self._settings.qbittorrent_url.rstrip("/")},
            transport=self._transport,
        )

        # Authenticate via /api/v2/auth/login if username is configured
        username = self._settings.qbittorrent_username.strip()
        password = self._settings.qbittorrent_password
        if username:
            _, login_body, _, cookies = client.request_raw(
                "POST",
                "/api/v2/auth/login",
                form_data={"username": username, "password": password},
            )
            login_text = login_body.decode("utf-8", errors="replace").strip()
            if login_text.lower().startswith("fails") or (
                "sid" not in {k.lower() for k in cookies} and login_text.lower() != "ok."
            ):
                raise MediaAuthError("qBittorrent /api/v2/auth/login rejected credentials.")
            for ck_name, ck_val in cookies.items():
                if ck_name.upper() == "SID":
                    client.set_cookie("SID", ck_val)

        app_version = client.get_text("/api/v2/app/version")
        webapi_version = client.get_text("/api/v2/app/webapiVersion")
        if not webapi_version:
            raise MediaMalformedResponseError(
                "qBittorrent /api/v2/app/webapiVersion returned an empty version string."
            )
        check_semver_major(
            webapi_version, min_major=2, service_label="qBittorrent WebAPI"
        )

        transfer = _require_dict(
            client.get_json("/api/v2/transfer/info"), "qBittorrent /api/v2/transfer/info"
        )
        if "connection_status" not in transfer or "dl_info_speed" not in transfer:
            raise MediaMalformedResponseError(
                "qBittorrent /api/v2/transfer/info missing connection_status or dl_info_speed."
            )

        torrents = _require_list(
            client.get_json("/api/v2/torrents/info"), "qBittorrent /api/v2/torrents/info"
        )

        downloading_states = {"downloading", "metadl", "forceddl", "allocating"}
        seeding_states = {"uploading", "stalledup", "forcedup"}
        paused_states = {"pauseddl", "pausedup", "stoppeddl", "stoppedup"}
        queued_states = {"queueddl", "queuedup"}
        checking_states = {"checkingdl", "checkingup", "checkingresumedata", "moving"}
        error_states = {"error", "missingfiles"}

        counts = {
            "total": 0,
            "downloading": 0,
            "seeding": 0,
            "paused": 0,
            "stalled": 0,
            "stalled_over_threshold": 0,
            "queued": 0,
            "checking": 0,
            "errored": 0,
        }
        stalled_list: list[dict[str, Any]] = []
        errored_list: list[dict[str, Any]] = []
        active_queue: list[dict[str, Any]] = []

        threshold_sec = self._settings.qbittorrent_stalled_threshold_seconds
        now_epoch = int(datetime.now(UTC).timestamp())

        for item in torrents:
            if not isinstance(item, dict):
                continue
            counts["total"] += 1
            raw_state = str(item.get("state") or "unknown")
            state_lower = raw_state.lower()
            name = str(item.get("name") or "unnamed")
            thash = str(item.get("hash") or "")
            progress = round(float(item.get("progress", 0.0) or 0.0) * 100.0, 1)
            dlspeed = int(item.get("dlspeed", 0) or 0)
            upspeed = int(item.get("upspeed", 0) or 0)
            time_active = int(item.get("time_active", 0) or 0)
            last_activity = int(item.get("last_activity", 0) or 0)
            eta = int(item.get("eta", 0) or 0)
            size_bytes = int(item.get("size", 0) or 0)

            idle_seconds = (
                max(0, now_epoch - last_activity)
                if last_activity > 0
                else time_active
            )

            if state_lower in downloading_states:
                counts["downloading"] += 1
                active_queue.append(
                    {
                        "hash": thash,
                        "name": name,
                        "state": raw_state,
                        "progress_percent": progress,
                        "dlspeed_bytes": dlspeed,
                        "upspeed_bytes": upspeed,
                        "eta_seconds": eta,
                        "time_active_seconds": time_active,
                        "size_bytes": size_bytes,
                    }
                )
            elif state_lower in seeding_states:
                counts["seeding"] += 1
            elif state_lower in paused_states:
                counts["paused"] += 1
            elif state_lower == "stalleddl":
                counts["stalled"] += 1
                over_threshold = idle_seconds >= threshold_sec or time_active >= threshold_sec
                if over_threshold:
                    counts["stalled_over_threshold"] += 1
                stalled_entry = {
                    "hash": thash,
                    "name": name,
                    "state": raw_state,
                    "progress_percent": progress,
                    "time_active_seconds": time_active,
                    "idle_seconds": idle_seconds,
                    "exceeds_threshold": over_threshold,
                }
                stalled_list.append(stalled_entry)
                active_queue.append(
                    {
                        "hash": thash,
                        "name": name,
                        "state": raw_state,
                        "progress_percent": progress,
                        "dlspeed_bytes": dlspeed,
                        "upspeed_bytes": upspeed,
                        "eta_seconds": eta,
                        "time_active_seconds": time_active,
                        "size_bytes": size_bytes,
                    }
                )
            elif state_lower in queued_states:
                counts["queued"] += 1
                active_queue.append(
                    {
                        "hash": thash,
                        "name": name,
                        "state": raw_state,
                        "progress_percent": progress,
                        "dlspeed_bytes": dlspeed,
                        "upspeed_bytes": upspeed,
                        "eta_seconds": eta,
                        "time_active_seconds": time_active,
                        "size_bytes": size_bytes,
                    }
                )
            elif state_lower in checking_states:
                counts["checking"] += 1
            elif state_lower in error_states:
                counts["errored"] += 1
                error_kind = (
                    "disk_missing_files" if state_lower == "missingfiles" else "download_error"
                )
                errored_list.append(
                    {
                        "hash": thash,
                        "name": name,
                        "state": raw_state,
                        "error_kind": error_kind,
                        "progress_percent": progress,
                    }
                )

        conn_status = str(transfer.get("connection_status") or "unknown").lower()
        alerts: list[dict[str, Any]] = []
        svc_status = "online"
        reason = "qBittorrent Web API online (client-enforced read-only)."

        if conn_status == "disconnected":
            svc_status = "critical"
            reason = "qBittorrent peer connection status is disconnected."
            alerts.append(
                {
                    "alert_key": "qbittorrent:connection.disconnected",
                    "code": "connection.disconnected",
                    "severity": "critical",
                    "category": "downloads",
                    "service": "qbittorrent",
                    "target": "qbittorrent",
                    "message": "qBittorrent reports connection_status='disconnected'.",
                    "metric_value": 0.0,
                    "threshold_value": 1.0,
                    "details": {"connection_status": conn_status},
                    "status": "active",
                    "created_at": now_iso,
                }
            )
        elif conn_status == "firewalled":
            svc_status = "degraded"
            reason = "qBittorrent peer connection is firewalled."
            alerts.append(
                {
                    "alert_key": "qbittorrent:connection.firewalled",
                    "code": "connection.firewalled",
                    "severity": "warning",
                    "category": "downloads",
                    "service": "qbittorrent",
                    "target": "qbittorrent",
                    "message": "qBittorrent reports connection_status='firewalled'.",
                    "metric_value": None,
                    "threshold_value": None,
                    "details": {"connection_status": conn_status},
                    "status": "active",
                    "created_at": now_iso,
                }
            )

        if errored_list:
            svc_status = "critical"
            reason = f"qBittorrent has {len(errored_list)} torrent(s) in error/missingFiles state."
            alerts.append(
                {
                    "alert_key": "qbittorrent:torrent.error",
                    "code": "torrent.error",
                    "severity": "critical",
                    "category": "downloads",
                    "service": "qbittorrent",
                    "target": errored_list[0]["name"],
                    "message": (
                        f"{len(errored_list)} torrent(s) in error or disk missingFiles state "
                        f"(first: {errored_list[0]['name']} [{errored_list[0]['state']}])."
                    ),
                    "metric_value": float(len(errored_list)),
                    "threshold_value": 1.0,
                    "details": {"errored_torrents": errored_list[:10]},
                    "status": "active",
                    "created_at": now_iso,
                }
            )

        if counts["stalled_over_threshold"] > 0:
            if svc_status == "online":
                svc_status = "degraded"
                reason = (
                    f"{counts['stalled_over_threshold']} torrent(s) stalled beyond "
                    f"{threshold_sec}s threshold."
                )
            alerts.append(
                {
                    "alert_key": "qbittorrent:torrent.stalled",
                    "code": "torrent.stalled",
                    "severity": "warning",
                    "category": "downloads",
                    "service": "qbittorrent",
                    "target": stalled_list[0]["name"] if stalled_list else "qbittorrent",
                    "message": (
                        f"{counts['stalled_over_threshold']} torrent(s) stalled longer than "
                        f"{threshold_sec}s."
                    ),
                    "metric_value": float(counts["stalled_over_threshold"]),
                    "threshold_value": float(threshold_sec),
                    "details": {"stalled_torrents": stalled_list[:10]},
                    "status": "active",
                    "created_at": now_iso,
                }
            )

        metrics = {
            "webapi_version": webapi_version,
            "connection_status": conn_status,
            "dht_nodes": int(transfer.get("dht_nodes", 0) or 0),
            "download_speed_bytes": int(transfer.get("dl_info_speed", 0) or 0),
            "upload_speed_bytes": int(transfer.get("up_info_speed", 0) or 0),
            "downloaded_session_bytes": int(transfer.get("dl_info_data", 0) or 0),
            "uploaded_session_bytes": int(transfer.get("up_info_data", 0) or 0),
            "counts": counts,
            "stalled_threshold_seconds": threshold_sec,
            "stalled_torrents": stalled_list[:15],
            "errored_torrents": errored_list[:15],
            "active_queue": active_queue[:15],
            "credential_scope_notice": QBITTORRENT_CREDENTIAL_NOTICE,
        }
        return svc_status, app_version or webapi_version, metrics, alerts, reason


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
