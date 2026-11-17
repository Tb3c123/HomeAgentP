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

import json
import sqlite3
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from homeagentp_core.config import Settings
from homeagentp_core.modules.media.adapters import build_media_adapters
from homeagentp_core.modules.nas.collector import parse_iso8601_utc

_LAST_MEDIA_PERSIST_EPOCH: dict[str, float] = {}

SERVICE_ORDER = (
    "jellyfin",
    "qbittorrent",
    "sonarr",
    "radarr",
    "bazarr",
    "prowlarr",
    "seerr",
)


def compute_age_and_staleness(
    timestamp_iso: str | None,
    *,
    stale_threshold_seconds: int,
    now: datetime | None = None,
) -> tuple[float | None, bool]:
    """Compute (age_seconds, is_stale) for an ISO-8601 timestamp."""
    if not timestamp_iso or not timestamp_iso.strip():
        return None, False
    try:
        dt = parse_iso8601_utc(timestamp_iso)
    except ValueError:
        return None, True
    ref_now = now or datetime.now(UTC)
    age = round(max(0.0, (ref_now - dt).total_seconds()), 2)
    return age, age > stale_threshold_seconds


def _load_service_states(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    rows = conn.execute("SELECT * FROM media_service_states").fetchall()
    result: dict[str, dict[str, Any]] = {}
    for r in rows:
        result[str(r["service"])] = {
            "service": str(r["service"]),
            "status": str(r["status"]),
            "consecutive_failures": int(r["consecutive_failures"]),
            "last_success_at": r["last_success_at"],
            "last_failure_at": r["last_failure_at"],
            "last_error_code": r["last_error_code"],
            "last_reason": str(r["last_reason"]),
            "last_snapshot_json": str(r["last_snapshot_json"]),
            "updated_at": str(r["updated_at"]),
        }
    return result


def update_service_state_and_build_alerts(
    conn: sqlite3.Connection,
    settings: Settings,
    raw_snap: dict[str, Any],
    *,
    prev_state: dict[str, Any] | None,
    now: datetime,
) -> dict[str, Any]:
    """Apply consecutive failure threshold, stale cache fallback, and service-level alert rules."""
    svc = str(raw_snap["service"])
    title = str(raw_snap["title"])
    now_iso = now.isoformat()
    threshold = settings.media_failure_threshold
    stale_limit = settings.media_snapshot_stale_seconds

    if not raw_snap.get("enabled") or not raw_snap.get("configured"):
        conn.execute(
            """
            INSERT INTO media_service_states (
                service, status, consecutive_failures, last_success_at, last_failure_at,
                last_error_code, last_reason, last_snapshot_json, updated_at
            )
            VALUES (?, 'unavailable', 0, NULL, NULL, NULL, ?, '{}', ?)
            ON CONFLICT(service) DO UPDATE SET
                status = 'unavailable',
                consecutive_failures = 0,
                last_error_code = NULL,
                last_reason = excluded.last_reason,
                updated_at = excluded.updated_at
            """,
            (svc, str(raw_snap.get("reason") or ""), now_iso),
        )
        return raw_snap

    error_code = raw_snap.get("error_code")
    if error_code is None:
        # Successful poll: reset consecutive failures and cache snapshot
        snap_copy = dict(raw_snap)
        snap_copy["consecutive_failures"] = 0
        snap_copy["last_success_at"] = now_iso
        snap_copy["last_failure_at"] = (
            prev_state.get("last_failure_at") if prev_state else None
        )
        snap_copy["stale"] = False
        snap_copy["age_seconds"] = 0.0

        conn.execute(
            """
            INSERT INTO media_service_states (
                service, status, consecutive_failures, last_success_at, last_failure_at,
                last_error_code, last_reason, last_snapshot_json, updated_at
            )
            VALUES (?, ?, 0, ?, ?, NULL, ?, ?, ?)
            ON CONFLICT(service) DO UPDATE SET
                status = excluded.status,
                consecutive_failures = 0,
                last_success_at = excluded.last_success_at,
                last_error_code = NULL,
                last_reason = excluded.last_reason,
                last_snapshot_json = excluded.last_snapshot_json,
                updated_at = excluded.updated_at
            """,
            (
                svc,
                str(snap_copy["status"]),
                now_iso,
                snap_copy["last_failure_at"],
                str(snap_copy.get("reason") or ""),
                json.dumps(snap_copy, ensure_ascii=False),
                now_iso,
            ),
        )
        return snap_copy

    # Poll encountered an error
    prev_failures = int(prev_state["consecutive_failures"]) if prev_state else 0
    consecutive = prev_failures + 1
    last_success_at = prev_state.get("last_success_at") if prev_state else None

    # Check if we have a cached snapshot from a previous successful poll
    cached_metrics: dict[str, Any] | None = None
    cached_version: str | None = None
    if prev_state and prev_state.get("last_snapshot_json"):
        try:
            parsed_cache = json.loads(str(prev_state["last_snapshot_json"]))
            if isinstance(parsed_cache, dict) and isinstance(
                parsed_cache.get("metrics"), dict
            ):
                cached_metrics = parsed_cache["metrics"]
                cached_version = parsed_cache.get("version")
        except json.JSONDecodeError:
            cached_metrics = None

    age_sec, is_stale = compute_age_and_staleness(
        str(last_success_at) if last_success_at else None,
        stale_threshold_seconds=stale_limit,
        now=now,
    )

    snap_out = dict(raw_snap)
    snap_out["consecutive_failures"] = consecutive
    snap_out["last_success_at"] = last_success_at
    snap_out["last_failure_at"] = now_iso
    if cached_metrics is not None:
        snap_out["metrics"] = cached_metrics
    if cached_version is not None and snap_out.get("version") is None:
        snap_out["version"] = cached_version
    snap_out["age_seconds"] = age_sec if age_sec is not None else 0.0
    snap_out["stale"] = bool(is_stale)

    alerts: list[dict[str, Any]] = []
    err_reason = str(raw_snap.get("reason") or "Service request failed.")

    if error_code == "auth_failed":
        effective_status = "auth_error"
        alerts.append(
            {
                "alert_key": f"{svc}:service.auth_failed",
                "code": "service.auth_failed",
                "severity": "critical",
                "category": str(raw_snap["category"]),
                "service": svc,
                "target": svc,
                "message": f"{title} authentication failed: {err_reason}",
                "metric_value": float(consecutive),
                "threshold_value": 1.0,
                "details": {
                    "error_code": error_code,
                    "consecutive_failures": consecutive,
                },
                "status": "active",
                "created_at": now_iso,
            }
        )
    elif error_code in {
        "ssrf_blocked",
        "redirect_blocked",
        "write_method_prohibited",
        "unsupported_version",
        "malformed_response",
        "response_too_large",
    }:
        effective_status = "error"
        alerts.append(
            {
                "alert_key": f"{svc}:service.{error_code}",
                "code": f"service.{error_code}",
                "severity": "warning" if error_code == "malformed_response" else "critical",
                "category": str(raw_snap["category"]),
                "service": svc,
                "target": svc,
                "message": f"{title} error ({error_code}): {err_reason}",
                "metric_value": float(consecutive),
                "threshold_value": 1.0,
                "details": {
                    "error_code": error_code,
                    "consecutive_failures": consecutive,
                },
                "status": "active",
                "created_at": now_iso,
            }
        )
    else:
        # Transient connectivity / timeout / HTTP 5xx error: enforce consecutive failure threshold
        if consecutive >= threshold:
            effective_status = "offline"
            alerts.append(
                {
                    "alert_key": f"{svc}:service.offline",
                    "code": "service.offline",
                    "severity": "critical",
                    "category": str(raw_snap["category"]),
                    "service": svc,
                    "target": svc,
                    "message": (
                        f"{title} is offline after {consecutive} consecutive failed polls "
                        f"({error_code}): {err_reason}"
                    ),
                    "metric_value": float(consecutive),
                    "threshold_value": float(threshold),
                    "details": {
                        "error_code": error_code,
                        "consecutive_failures": consecutive,
                        "failure_threshold": threshold,
                    },
                    "status": "active",
                    "created_at": now_iso,
                }
            )
        else:
            effective_status = "stale" if is_stale else "degraded"
            snap_out["reason"] = (
                f"Transient {error_code} ({consecutive}/{threshold} before offline): {err_reason}"
            )
            if error_code == "timeout":
                alerts.append(
                    {
                        "alert_key": f"{svc}:service.timeout",
                        "code": "service.timeout",
                        "severity": "warning",
                        "category": str(raw_snap["category"]),
                        "service": svc,
                        "target": svc,
                        "message": (
                            f"{title} poll timed out ({consecutive}/{threshold} consecutive): "
                            f"{err_reason}"
                        ),
                        "metric_value": float(consecutive),
                        "threshold_value": float(threshold),
                        "details": {
                            "error_code": error_code,
                            "consecutive_failures": consecutive,
                            "failure_threshold": threshold,
                        },
                        "status": "active",
                        "created_at": now_iso,
                    }
                )

    if is_stale:
        alerts.append(
            {
                "alert_key": f"{svc}:snapshot.stale",
                "code": "snapshot.stale",
                "severity": "warning",
                "category": str(raw_snap["category"]),
                "service": svc,
                "target": svc,
                "message": (
                    f"{title} telemetry is stale (last success age {age_sec}s > "
                    f"{stale_limit}s)."
                ),
                "metric_value": age_sec,
                "threshold_value": float(stale_limit),
                "details": {"last_success_at": last_success_at, "age_seconds": age_sec},
                "status": "active",
                "created_at": now_iso,
            }
        )

    snap_out["status"] = effective_status
    snap_out["alerts"] = alerts

    conn.execute(
        """
        INSERT INTO media_service_states (
            service, status, consecutive_failures, last_success_at, last_failure_at,
            last_error_code, last_reason, last_snapshot_json, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(service) DO UPDATE SET
            status = excluded.status,
            consecutive_failures = excluded.consecutive_failures,
            last_failure_at = excluded.last_failure_at,
            last_error_code = excluded.last_error_code,
            last_reason = excluded.last_reason,
            updated_at = excluded.updated_at
        """,
        (
            svc,
            effective_status,
            consecutive,
            last_success_at,
            now_iso,
            str(error_code),
            snap_out["reason"],
            prev_state["last_snapshot_json"] if prev_state else "{}",
            now_iso,
        ),
    )
    return snap_out


def sync_media_alert_lifecycle(
    conn: sqlite3.Connection,
    evaluated_alerts: list[dict[str, Any]],
    *,
    now_iso: str,
    can_resolve_missing: bool = True,
    service_scope: str | None = None,
) -> list[dict[str, Any]]:
    """Synchronize active/resolved media alerts in SQLite (`media_alerts`)."""
    if service_scope:
        existing_rows = conn.execute(
            "SELECT * FROM media_alerts WHERE status = 'active' AND service = ? ORDER BY id ASC",
            (service_scope,),
        ).fetchall()
    else:
        existing_rows = conn.execute(
            "SELECT * FROM media_alerts WHERE status = 'active' ORDER BY id ASC"
        ).fetchall()

    active_by_key: dict[str, sqlite3.Row] = {str(r["alert_key"]): r for r in existing_rows}
    seen_keys: set[str] = set()

    for alert in evaluated_alerts:
        key = str(alert["alert_key"])
        seen_keys.add(key)
        details_str = json.dumps(alert.get("details", {}), ensure_ascii=False)
        existing = active_by_key.get(key)
        if existing is not None:
            conn.execute(
                """
                UPDATE media_alerts
                SET severity = ?,
                    message = ?,
                    metric_value = ?,
                    threshold_value = ?,
                    details_json = ?,
                    last_seen_at = ?,
                    occurrences = occurrences + 1
                WHERE id = ?
                """,
                (
                    str(alert["severity"]),
                    str(alert["message"]),
                    alert.get("metric_value"),
                    alert.get("threshold_value"),
                    details_str,
                    now_iso,
                    int(existing["id"]),
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO media_alerts (
                    alert_key, code, severity, category, service, target,
                    message, metric_value, threshold_value, details_json,
                    status, first_seen_at, last_seen_at, resolved_at, occurrences
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, NULL, 1)
                """,
                (
                    key,
                    str(alert["code"]),
                    str(alert["severity"]),
                    str(alert.get("category", "media")),
                    str(alert["service"]),
                    str(alert.get("target", alert["service"])),
                    str(alert["message"]),
                    alert.get("metric_value"),
                    alert.get("threshold_value"),
                    details_str,
                    now_iso,
                    now_iso,
                ),
            )

    if can_resolve_missing:
        for key, row in active_by_key.items():
            if key not in seen_keys:
                conn.execute(
                    """
                    UPDATE media_alerts
                    SET status = 'resolved',
                        resolved_at = ?
                    WHERE id = ?
                    """,
                    (now_iso, int(row["id"])),
                )

    return query_media_alerts(
        conn, include_resolved=False, service=service_scope, limit=100
    )


def query_media_alerts(
    conn: sqlite3.Connection,
    *,
    include_resolved: bool = False,
    service: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Query Media & Downloads alerts from SQLite with active/resolved and service filtering."""
    clauses: list[str] = []
    params: list[Any] = []
    if not include_resolved:
        clauses.append("status = 'active'")
    if service:
        clauses.append("service = ?")
        params.append(service)

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)

    rows = conn.execute(
        f"""
        SELECT * FROM media_alerts
        {where_sql}
        ORDER BY CASE WHEN status = 'active' THEN 0 ELSE 1 END, id DESC
        LIMIT ?
        """,  # noqa: S608
        tuple(params),
    ).fetchall()

    return [
        {
            "id": int(r["id"]),
            "alert_key": str(r["alert_key"]),
            "code": str(r["code"]),
            "severity": str(r["severity"]),
            "category": str(r["category"]),
            "service": str(r["service"]),
            "target": str(r["target"]),
            "message": str(r["message"]),
            "metric_value": r["metric_value"],
            "threshold_value": r["threshold_value"],
            "details": json.loads(str(r["details_json"])),
            "status": str(r["status"]),
            "first_seen_at": str(r["first_seen_at"]),
            "last_seen_at": str(r["last_seen_at"]),
            "resolved_at": r["resolved_at"],
            "occurrences": int(r["occurrences"]),
            "created_at": str(r["first_seen_at"]),
        }
        for r in rows
    ]


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


def persist_media_snapshot(
    conn: sqlite3.Connection,
    overview_snapshot: dict[str, Any],
    *,
    retention_limit: int = 120,
    min_persist_interval_seconds: int = 0,
    db_key: str = "default",
) -> int:
    """Persist a Media & Downloads metric snapshot and prune historical rows."""
    now_epoch = time.monotonic()
    last_epoch = _LAST_MEDIA_PERSIST_EPOCH.get(db_key)
    now_iso = str(overview_snapshot["collected_at"])
    overall_status = str(overview_snapshot.get("overall_status") or overview_snapshot["status"])
    if overall_status not in {"online", "degraded", "critical", "stale", "unavailable"}:
        overall_status = "critical"

    if (
        min_persist_interval_seconds > 0
        and last_epoch is not None
        and (now_epoch - last_epoch) < min_persist_interval_seconds
    ):
        latest_row = conn.execute(
            "SELECT id, overall_status FROM media_metric_snapshots ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if latest_row is not None and str(latest_row["overall_status"]) == overall_status:
            return int(latest_row["id"])

    _LAST_MEDIA_PERSIST_EPOCH[db_key] = now_epoch
    summary = overview_snapshot.get("summary", {})
    services_compact = {
        name: {
            "status": svc.get("status"),
            "latency_ms": svc.get("latency_ms"),
            "version": svc.get("version"),
            "consecutive_failures": svc.get("consecutive_failures", 0),
            "error_code": svc.get("error_code"),
        }
        for name, svc in overview_snapshot.get("services", {}).items()
    }

    cursor = conn.execute(
        """
        INSERT INTO media_metric_snapshots (
            collected_at, overall_status,
            jellyfin_active_streams, jellyfin_transcoding_streams,
            qb_dl_speed_bytes, qb_up_speed_bytes,
            qb_downloading_count, qb_stalled_count, qb_errored_count,
            sonarr_queue_count, radarr_queue_count,
            missing_subtitles_count, pending_requests_count,
            services_summary_json, alerts_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            now_iso,
            overall_status,
            int(summary.get("jellyfin_active_streams", 0) or 0),
            int(summary.get("jellyfin_transcoding_streams", 0) or 0),
            summary.get("qb_download_speed_bytes"),
            summary.get("qb_upload_speed_bytes"),
            summary.get("qb_downloading_count"),
            summary.get("qb_stalled_count"),
            summary.get("qb_errored_count"),
            summary.get("sonarr_queue_count"),
            summary.get("radarr_queue_count"),
            summary.get("bazarr_missing_subtitles"),
            summary.get("seerr_pending_requests"),
            json.dumps(services_compact, ensure_ascii=False),
            json.dumps(overview_snapshot.get("alerts", []), ensure_ascii=False),
        ),
    )
    snapshot_id = int(cursor.lastrowid or 0)

    conn.execute(
        """
        DELETE FROM media_metric_snapshots
        WHERE id NOT IN (
            SELECT id FROM media_metric_snapshots ORDER BY id DESC LIMIT ?
        )
        """,
        (retention_limit,),
    )
    conn.execute(
        """
        DELETE FROM media_alerts
        WHERE status = 'resolved'
          AND id NOT IN (
              SELECT id FROM media_alerts WHERE status = 'resolved' ORDER BY id DESC LIMIT ?
          )
        """,
        (retention_limit * 2,),
    )
    return snapshot_id


def query_media_history(
    conn: sqlite3.Connection,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Return recent persisted Media & Downloads metric snapshots."""
    rows = conn.execute(
        "SELECT * FROM media_metric_snapshots ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    history: list[dict[str, Any]] = []
    for r in rows:
        history.append(
            {
                "id": int(r["id"]),
                "collected_at": str(r["collected_at"]),
                "overall_status": str(r["overall_status"]),
                "jellyfin_active_streams": int(r["jellyfin_active_streams"]),
                "jellyfin_transcoding_streams": int(r["jellyfin_transcoding_streams"]),
                "qb_dl_speed_bytes": r["qb_dl_speed_bytes"],
                "qb_up_speed_bytes": r["qb_up_speed_bytes"],
                "qb_downloading_count": r["qb_downloading_count"],
                "qb_stalled_count": r["qb_stalled_count"],
                "qb_errored_count": r["qb_errored_count"],
                "sonarr_queue_count": r["sonarr_queue_count"],
                "radarr_queue_count": r["radarr_queue_count"],
                "missing_subtitles_count": r["missing_subtitles_count"],
                "pending_requests_count": r["pending_requests_count"],
                "services_summary": json.loads(str(r["services_summary_json"])),
                "alerts": json.loads(str(r["alerts_json"])),
            }
        )
    return history
