"""Read-only qBittorrent Web API v2 connector."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from homeagentp_core.modules.media.base import (
    MediaAuthError,
    MediaMalformedResponseError,
    MediaServiceAdapter,
    SafeMediaHttpClient,
    check_semver_major,
)

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
