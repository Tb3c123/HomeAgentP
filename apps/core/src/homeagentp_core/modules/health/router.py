"""Health, Overview, and Settings endpoints for HomeAgentP Core."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Request

from homeagentp_core import __version__
from homeagentp_core.auth.security import (
    AuthenticatedPrincipal,
    get_current_principal,
    get_settings,
)
from homeagentp_core.config import Settings
from homeagentp_core.db.connection import db_session
from homeagentp_core.db.migrator import get_current_schema_version
from homeagentp_core.modules.media.collector import collect_media_telemetry
from homeagentp_core.modules.nas.collector import collect_nas_telemetry

router = APIRouter(prefix="/api/v1", tags=["health-overview"])


@router.get("/health")
def health_check(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """Unauthenticated minimal liveness and SQLite readiness probe."""
    with db_session(settings.db_path) as conn:
        conn.execute("SELECT 1").fetchone()
        schema_version = get_current_schema_version(conn)
    return {
        "status": "ok",
        "service": "homeagentp-core",
        "version": __version__,
        "schema_version": schema_version,
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/overview")
def get_overview(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Return honest system overview across all HomeAgentP domains.

    Never fabricates live NAS, Media, Download, or Home Assistant telemetry.
    When HOMEAGENTP_NAS_ADAPTER_ENABLED=false or HOMEAGENTP_MEDIA_ADAPTER_ENABLED=false,
    the corresponding domains honestly report status='unavailable'.
    """
    transports = getattr(request.app.state, "media_transports", None)
    with db_session(settings.db_path) as conn:
        total_projects = int(conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0])
        total_tasks = int(conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0])
        open_tasks = int(
            conn.execute("SELECT COUNT(*) FROM tasks WHERE status != 'done'").fetchone()[0]
        )
        in_progress_tasks = int(
            conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'in_progress'").fetchone()[0]
        )
        total_scripts = int(conn.execute("SELECT COUNT(*) FROM script_manifests").fetchone()[0])
        allowlisted_scripts = int(
            conn.execute(
                "SELECT COUNT(*) FROM script_manifests WHERE review_status = 'allowlisted'"
            ).fetchone()[0]
        )
        total_reports = int(conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0])
        total_audit_events = int(conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0])
        nas_snapshots_count = int(
            conn.execute("SELECT COUNT(*) FROM nas_metric_snapshots").fetchone()[0]
        )
        nas_alerts_count = int(conn.execute("SELECT COUNT(*) FROM nas_alerts").fetchone()[0])
        media_snapshots_count = int(
            conn.execute("SELECT COUNT(*) FROM media_metric_snapshots").fetchone()[0]
        )
        media_alerts_count = int(
            conn.execute("SELECT COUNT(*) FROM media_alerts").fetchone()[0]
        )
        media_snap = collect_media_telemetry(
            settings, conn=conn, transports=transports
        )

    nas_snap = collect_nas_telemetry(settings, sample_delay_seconds=0.0)
    mounts_iter = nas_snap.get("mounts_list") or list(nas_snap.get("mounts", {}).values())
    mounts_map = {
        str(m.get("mount_point") or m.get("path")): str(m["status"])
        for m in mounts_iter
        if str(m.get("mount_point") or m.get("path")) in set(settings.nas_required_mounts)
    }
    for req_mp in settings.nas_required_mounts:
        mounts_map.setdefault(req_mp, "unavailable")

    cpu_load_str = (
        f"{nas_snap['cpu']['usage_percent']}%"
        if nas_snap["cpu"]["usage_percent"] is not None
        else (
            f"load {nas_snap['cpu']['load_1m']}"
            if nas_snap["cpu"]["load_1m"] is not None
            else "unavailable"
        )
    )
    ram_usage_str = (
        f"{nas_snap['memory']['usage_percent']}%"
        if nas_snap["memory"]["usage_percent"] is not None
        else "unavailable"
    )

    media_services_map = {
        svc_key: str(media_snap["services"][svc_key]["status"])
        for svc_key in ("jellyfin", "sonarr", "radarr", "bazarr", "prowlarr", "seerr")
    }
    media_only_statuses = list(media_services_map.values())
    if all(st == "unavailable" for st in media_only_statuses):
        media_domain_status = "unavailable"
        media_domain_reason = (
            "Media connectors are not configured (set HOMEAGENTP_MEDIA_ADAPTER_ENABLED=true "
            "and service URLs/API keys)."
        )
    elif any(
        st in {"critical", "offline", "auth_error", "error"}
        for st in media_only_statuses
    ):
        media_domain_status = "critical"
        media_domain_reason = "One or more Media services reported critical/offline status."
    elif any(st in {"degraded", "timeout", "stale"} for st in media_only_statuses):
        media_domain_status = "degraded"
        media_domain_reason = "One or more Media services reported warnings or degraded status."
    else:
        media_domain_status = "online"
        media_domain_reason = "Read-only Media connectors active."

    qb_svc = media_snap["services"]["qbittorrent"]
    qb_status = str(qb_svc["status"])
    qb_metrics_raw = qb_svc.get("metrics", {})
    qb_counts = qb_metrics_raw.get("counts", {}) if isinstance(qb_metrics_raw, dict) else {}
    if qb_status == "unavailable" or not qb_svc.get("enabled"):
        downloads_metrics = {
            "active_torrents": "unavailable",
            "stalled_torrents": "unavailable",
            "download_speed": "unavailable",
        }
    else:
        dl_bps = qb_metrics_raw.get("download_speed_bytes")
        dl_str = (
            f"{(int(dl_bps) / (1024 * 1024)):.2f} MiB/s"
            if isinstance(dl_bps, int)
            else "unavailable"
        )
        downloads_metrics = {
            "active_torrents": str(qb_counts.get("downloading", 0)),
            "stalled_torrents": str(qb_counts.get("stalled", 0)),
            "download_speed": dl_str,
        }

    return {
        "architecture": "B+ (Antigravity-first, Dashboard-light)",
        "generated_at": datetime.now(UTC).isoformat(),
        "workspace_counts": {
            "projects": total_projects,
            "tasks_total": total_tasks,
            "tasks_open": open_tasks,
            "tasks_in_progress": in_progress_tasks,
            "scripts_total": total_scripts,
            "scripts_allowlisted": allowlisted_scripts,
            "reports_total": total_reports,
            "audit_events": total_audit_events,
            "nas_snapshots": nas_snapshots_count,
            "nas_alerts": nas_alerts_count,
            "media_snapshots": media_snapshots_count,
            "media_alerts": media_alerts_count,
        },
        "domains": {
            "nas_guardian": {
                "title": "NAS Guardian",
                "status": nas_snap["adapter_status"],
                "phase": "Phase 02",
                "reason": nas_snap["reason"]
                or "Read-only NAS Guardian telemetry active.",
                "metrics": {
                    "cpu_load": cpu_load_str,
                    "ram_usage": ram_usage_str,
                    "mounts": mounts_map,
                    "smart_health": "unavailable",
                    "containers": nas_snap["containers"]["status"],
                },
            },
            "media": {
                "title": "Media Stack",
                "status": media_domain_status,
                "phase": "Phase 03",
                "reason": media_domain_reason,
                "services": media_services_map,
            },
            "downloads": {
                "title": "Downloads (qBittorrent)",
                "status": qb_status,
                "phase": "Phase 03",
                "reason": str(qb_svc.get("reason") or "qBittorrent read-only adapter."),
                "metrics": downloads_metrics,
            },
            "home_automation": {
                "title": "Home Assistant & Telegram Alerts",
                "status": "unavailable",
                "phase": "Phase 05",
                "reason": (
                    "Home Assistant event listener and Telegram bot adapter "
                    "are scheduled for Phase 05."
                ),
                "integrations": {
                    "home_assistant": "unavailable",
                    "telegram_alerts": "unavailable",
                    "scheduled_reports": "unavailable",
                },
            },
            "ai_workspace": {
                "title": "AI Workspace & Developer Handoff",
                "status": "online",
                "phase": "Phase 01",
                "handoff_mode": (
                    "Git branch/PR & versioned Task Briefs "
                    "(Official Antigravity human-operated)"
                ),
                "consumer_cli_wrapper": "disabled_by_policy",
            },
        },
    }


@router.get("/settings")
def get_redacted_settings(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Return non-sensitive runtime settings and enforced B+ security constraints."""
    return settings.redacted_summary()
