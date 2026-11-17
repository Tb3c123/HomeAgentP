"""Health, Overview, and Settings endpoints for HomeAgentP Core."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends

from homeagentp_core import __version__
from homeagentp_core.auth.security import (
    AuthenticatedPrincipal,
    get_current_principal,
    get_settings,
)
from homeagentp_core.config import Settings
from homeagentp_core.db.connection import db_session
from homeagentp_core.db.migrator import get_current_schema_version

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
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Return honest system overview across all HomeAgentP domains.

    Never fabricates live NAS, Media, Download, or Home Assistant telemetry.
    Unconfigured Phase 02-05 integrations explicitly report status='unavailable'.
    """
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
        },
        "domains": {
            "nas_guardian": {
                "title": "NAS Guardian",
                "status": "unavailable",
                "phase": "Phase 02",
                "reason": "Read-only NAS telemetry adapter not enabled in Phase 01 Foundation.",
                "metrics": {
                    "cpu_load": "unavailable",
                    "ram_usage": "unavailable",
                    "mounts": {
                        "/mnt/disk1": "unavailable",
                        "/mnt/disk2": "unavailable",
                    },
                    "smart_health": "unavailable",
                    "containers": "unavailable",
                },
            },
            "media": {
                "title": "Media Stack",
                "status": "unavailable",
                "phase": "Phase 03",
                "reason": "Read-only media API connectors are scheduled for Phase 03.",
                "services": {
                    "jellyfin": "unavailable",
                    "sonarr": "unavailable",
                    "radarr": "unavailable",
                    "bazarr": "unavailable",
                    "prowlarr": "unavailable",
                    "seerr": "unavailable",
                },
            },
            "downloads": {
                "title": "Downloads (qBittorrent)",
                "status": "unavailable",
                "phase": "Phase 03",
                "reason": "qBittorrent read-only adapter is scheduled for Phase 03.",
                "metrics": {
                    "active_torrents": "unavailable",
                    "stalled_torrents": "unavailable",
                    "download_speed": "unavailable",
                },
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
