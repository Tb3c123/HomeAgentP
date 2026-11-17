"""Shared read-only logic for Sonarr v3 and Radarr v3 connectors."""

from __future__ import annotations

from typing import Any

from homeagentp_core.modules.media.base import (
    MediaMalformedResponseError,
    MediaServiceAdapter,
    SafeMediaHttpClient,
    check_semver_major,
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


class ArrV3BaseAdapter(MediaServiceAdapter):
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


_ArrV3BaseAdapter = ArrV3BaseAdapter
