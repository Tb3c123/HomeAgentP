"""Service state, consecutive failure thresholds, and stale cache fallback for Media Hub."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from homeagentp_core.config import Settings
from homeagentp_core.modules.nas.collector import parse_iso8601_utc


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


def load_service_states(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    """Load persisted per-service state rows from `media_service_states`."""
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

    prev_failures = int(prev_state["consecutive_failures"]) if prev_state else 0
    consecutive = prev_failures + 1
    last_success_at = prev_state.get("last_success_at") if prev_state else None

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
