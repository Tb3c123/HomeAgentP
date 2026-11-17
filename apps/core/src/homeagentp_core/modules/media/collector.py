"""Unified Media & Downloads collector, consecutive failure state machine, and SQLite persistence.

Invariants:
1. Fault Isolation: Each adapter (`jellyfin`, `qbittorrent`, `sonarr`, `radarr`, `bazarr`,
   `prowlarr`, `seerr`) is polled independently. One failing service never crashes or blocks
   the others.
2. Consecutive Failure Threshold (Anti-Flapping):
   - A single timeout or connection error
     (`consecutive_failures < settings.media_failure_threshold`) does NOT mark a service as
     `offline`. Instead, it reports `status="degraded"` (with cached metrics if available) and a
     transient warning.
   - Once `consecutive_failures >= settings.media_failure_threshold`, the service transitions
     to `status="offline"` and raises a critical `{service}:service.offline` alert.
   - A single successful poll immediately resets `consecutive_failures = 0` and resolves prior
     connectivity/offline alerts.
3. Stale Data Detection:
   - Cached snapshots older than `settings.media_snapshot_stale_seconds` are flagged `stale=True`
     with accurate `age_seconds`.
4. Alert Lifecycle & SSD Write-Throttling:
   - Deduplicates active alerts by `alert_key`, tracks `occurrences`, `first_seen_at`,
     `last_seen_at`, and transitions cleared alerts to `status="resolved"` (`resolved_at`).
   - Enforces `media_min_persist_interval_seconds` and `media_history_retention_limit`.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any

import httpx

from homeagentp_core.config import Settings
from homeagentp_core.modules.media.adapters import build_media_adapters
from homeagentp_core.modules.media.alerts import (
    query_media_alerts as query_media_alerts,
)
from homeagentp_core.modules.media.alerts import (
    sync_media_alert_lifecycle as sync_media_alert_lifecycle,
)
from homeagentp_core.modules.media.persistence import (
    _LAST_MEDIA_PERSIST_EPOCH as _LAST_MEDIA_PERSIST_EPOCH,
)
from homeagentp_core.modules.media.persistence import (
    persist_media_snapshot as persist_media_snapshot,
)
from homeagentp_core.modules.media.persistence import (
    query_media_history as query_media_history,
)
from homeagentp_core.modules.media.state import (
    compute_age_and_staleness as compute_age_and_staleness,
)
from homeagentp_core.modules.media.state import (
    load_service_states as _load_service_states,
)
from homeagentp_core.modules.media.state import (
    update_service_state_and_build_alerts as update_service_state_and_build_alerts,
)

SERVICE_ORDER = (
    "jellyfin",
    "qbittorrent",
    "sonarr",
    "radarr",
    "bazarr",
    "prowlarr",
    "seerr",
)


def compute_overall_media_status(services_map: dict[str, dict[str, Any]]) -> tuple[str, str]:
    """Derive unified status ('online'|'degraded'|'critical'|'stale'|'unavailable')."""
    enabled_services = [s for s in services_map.values() if s.get("enabled")]
    if not enabled_services:
        return (
            "unavailable",
            "No Media or Downloads connectors are currently enabled/configured.",
        )

    statuses = [str(s.get("status", "unavailable")) for s in enabled_services]
    if any(st in {"critical", "offline", "auth_error", "error"} for st in statuses):
        failing = [
            s["service"]
            for s in enabled_services
            if s.get("status") in {"critical", "offline", "auth_error", "error"}
        ]
        return (
            "critical",
            f"Critical/offline state detected in: {', '.join(failing)}.",
        )
    if any(st == "stale" for st in statuses):
        stale_svcs = [s["service"] for s in enabled_services if s.get("status") == "stale"]
        return ("stale", f"Stale telemetry detected in: {', '.join(stale_svcs)}.")
    if any(st in {"degraded", "timeout"} for st in statuses):
        deg_svcs = [
            s["service"]
            for s in enabled_services
            if s.get("status") in {"degraded", "timeout"}
        ]
        return ("degraded", f"Degraded status or warnings in: {', '.join(deg_svcs)}.")
    return (
        "online",
        f"All {len(enabled_services)} configured Media & Downloads service(s) online.",
    )


def build_media_summary(services_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Extract high-level summary metrics across all 7 services for overview & SQLite history."""
    jf = services_map.get("jellyfin", {})
    jf_sess = (
        jf.get("metrics", {}).get("sessions", {})
        if isinstance(jf.get("metrics"), dict)
        else {}
    )
    qb = services_map.get("qbittorrent", {})
    qb_metrics = qb.get("metrics", {}) if isinstance(qb.get("metrics"), dict) else {}
    qb_counts = (
        qb_metrics.get("counts", {}) if isinstance(qb_metrics.get("counts"), dict) else {}
    )
    sonarr = services_map.get("sonarr", {})
    sonarr_m = (
        sonarr.get("metrics", {}) if isinstance(sonarr.get("metrics"), dict) else {}
    )
    radarr = services_map.get("radarr", {})
    radarr_m = (
        radarr.get("metrics", {}) if isinstance(radarr.get("metrics"), dict) else {}
    )
    bazarr = services_map.get("bazarr", {})
    bazarr_m = (
        bazarr.get("metrics", {}) if isinstance(bazarr.get("metrics"), dict) else {}
    )
    prowlarr = services_map.get("prowlarr", {})
    prowlarr_m = (
        prowlarr.get("metrics", {}) if isinstance(prowlarr.get("metrics"), dict) else {}
    )
    seerr = services_map.get("seerr", {})
    seerr_req = (
        seerr.get("metrics", {}).get("requests", {})
        if isinstance(seerr.get("metrics"), dict)
        else {}
    )

    missing_ep_subs = bazarr_m.get("missing_episode_subtitles")
    missing_mv_subs = bazarr_m.get("missing_movie_subtitles")
    total_missing_subs = (
        (int(missing_ep_subs or 0) + int(missing_mv_subs or 0))
        if (missing_ep_subs is not None or missing_mv_subs is not None)
        else None
    )

    configured_count = sum(1 for s in services_map.values() if s.get("configured"))
    online_count = sum(1 for s in services_map.values() if s.get("status") == "online")

    return {
        "configured_services_count": configured_count,
        "online_services_count": online_count,
        "jellyfin_active_streams": int(jf_sess.get("active_count", 0) or 0),
        "jellyfin_direct_play_streams": int(jf_sess.get("direct_play_count", 0) or 0),
        "jellyfin_transcoding_streams": int(jf_sess.get("transcoding_count", 0) or 0),
        "qb_download_speed_bytes": qb_metrics.get("download_speed_bytes"),
        "qb_upload_speed_bytes": qb_metrics.get("upload_speed_bytes"),
        "qb_downloading_count": int(qb_counts.get("downloading", 0) or 0),
        "qb_seeding_count": int(qb_counts.get("seeding", 0) or 0),
        "qb_stalled_count": int(qb_counts.get("stalled", 0) or 0),
        "qb_errored_count": int(qb_counts.get("errored", 0) or 0),
        "sonarr_queue_count": int(sonarr_m.get("queue_total", 0) or 0),
        "sonarr_missing_episodes": sonarr_m.get("missing_count"),
        "radarr_queue_count": int(radarr_m.get("queue_total", 0) or 0),
        "radarr_missing_movies": radarr_m.get("missing_count"),
        "bazarr_missing_subtitles": total_missing_subs,
        "prowlarr_failing_indexers": int(
            prowlarr_m.get("failing_indexers_count", 0) or 0
        ),
        "seerr_pending_requests": seerr_req.get("pending"),
        "seerr_approved_requests": seerr_req.get("approved"),
    }


def collect_media_telemetry(
    settings: Settings,
    *,
    conn: sqlite3.Connection | None = None,
    transports: dict[str, httpx.BaseTransport] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Collect read-only telemetry across all 7 Media & Downloads services.

    If `conn` is provided, updates `media_service_states` (consecutive failures & recovery)
    and synchronizes `media_alerts` lifecycle.
    """
    ref_now = now or datetime.now(UTC)
    now_iso = ref_now.isoformat()
    adapters = build_media_adapters(settings, transports=transports)

    prev_states = _load_service_states(conn) if conn is not None else {}
    services_map: dict[str, dict[str, Any]] = {}
    all_evaluated_alerts: list[dict[str, Any]] = []

    for svc_name in SERVICE_ORDER:
        adapter = adapters[svc_name]
        raw_snap = adapter.collect(now=ref_now)
        if conn is not None:
            processed_snap = update_service_state_and_build_alerts(
                conn,
                settings,
                raw_snap,
                prev_state=prev_states.get(svc_name),
                now=ref_now,
            )
        else:
            processed_snap = raw_snap

        services_map[svc_name] = processed_snap
        all_evaluated_alerts.extend(processed_snap.get("alerts", []))

    overall_status, overall_reason = compute_overall_media_status(services_map)
    summary = build_media_summary(services_map)

    if conn is not None:
        active_alerts = sync_media_alert_lifecycle(
            conn,
            all_evaluated_alerts,
            now_iso=now_iso,
            can_resolve_missing=True,
        )
    else:
        active_alerts = all_evaluated_alerts

    return {
        "status": overall_status,
        "overall_status": overall_status,
        "adapter_enabled": settings.media_adapter_enabled,
        "collected_at": now_iso,
        "collection_interval_seconds": settings.media_collection_interval_seconds,
        "history_retention_limit": settings.media_history_retention_limit,
        "failure_threshold": settings.media_failure_threshold,
        "snapshot_stale_seconds": settings.media_snapshot_stale_seconds,
        "reason": overall_reason,
        "summary": summary,
        "services": services_map,
        "alerts": active_alerts,
        "safety": {
            "read_only_enforced": True,
            "write_operations_performed": 0,
            "media_filesystem_mounted": False,
            "docker_socket_used": False,
            "ssrf_allowlist_enforced": True,
            "redirects_blocked": True,
            "qbittorrent_client_allowlist_only": True,
        },
    }


def collect_single_media_service(
    settings: Settings,
    service_name: str,
    *,
    conn: sqlite3.Connection | None = None,
    transports: dict[str, httpx.BaseTransport] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Collect read-only telemetry for a single service and synchronize its state/alerts."""
    ref_now = now or datetime.now(UTC)
    now_iso = ref_now.isoformat()
    adapters = build_media_adapters(settings, transports=transports)
    if service_name not in adapters:
        raise KeyError(f"Unknown media service '{service_name}'.")

    raw_snap = adapters[service_name].collect(now=ref_now)
    if conn is not None:
        prev_states = _load_service_states(conn)
        processed = update_service_state_and_build_alerts(
            conn,
            settings,
            raw_snap,
            prev_state=prev_states.get(service_name),
            now=ref_now,
        )
        svc_alerts = sync_media_alert_lifecycle(
            conn,
            processed.get("alerts", []),
            now_iso=now_iso,
            can_resolve_missing=True,
            service_scope=service_name,
        )
        processed["alerts"] = svc_alerts
        return processed
    return raw_snap


__all__ = [
    "SERVICE_ORDER",
    "_LAST_MEDIA_PERSIST_EPOCH",
    "_load_service_states",
    "build_media_summary",
    "collect_media_telemetry",
    "collect_single_media_service",
    "compute_age_and_staleness",
    "compute_overall_media_status",
    "persist_media_snapshot",
    "query_media_alerts",
    "query_media_history",
    "sync_media_alert_lifecycle",
    "update_service_state_and_build_alerts",
]

