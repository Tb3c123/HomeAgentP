"""Read-only Sonarr API v3 connector."""

from __future__ import annotations

from typing import Any, Literal

from homeagentp_core.modules.media.connectors.arr_common import ArrV3BaseAdapter


class SonarrAdapter(ArrV3BaseAdapter):
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
