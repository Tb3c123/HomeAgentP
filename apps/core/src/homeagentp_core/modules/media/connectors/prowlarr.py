"""Read-only Prowlarr API v1 connector."""

from __future__ import annotations

from typing import Any, Literal

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
                indexer_name_by_id[int(idx["id"])] = str(
                    idx.get("name") or f"Indexer #{idx['id']}"
                )

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
