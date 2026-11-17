"""Read-only Bazarr subtitle manager connector."""

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


def _opt_dict(val: Any) -> dict[str, Any]:
    return val if isinstance(val, dict) else {}


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
