"""Unified Media & Downloads Monitoring API router (/api/v1/media/*)."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, Query, Request

from homeagentp_core.auth.security import (
    AuthenticatedPrincipal,
    get_current_principal,
    get_settings,
    record_audit_log,
    require_csrf,
)
from homeagentp_core.config import Settings
from homeagentp_core.db.connection import db_session
from homeagentp_core.modules.media.collector import (
    collect_media_telemetry,
    collect_single_media_service,
    persist_media_snapshot,
    query_media_alerts,
    query_media_history,
)
from homeagentp_core.modules.media.scheduler import MediaCollectionScheduler

router = APIRouter(prefix="/api/v1/media", tags=["media-downloads"])


def _scheduler_summary(request: Request) -> dict[str, Any]:
    sched: MediaCollectionScheduler | None = getattr(
        request.app.state, "media_scheduler", None
    )
    if sched is None:
        return {"enabled": False, "running": False, "last_status": "unavailable"}
    return sched.status_summary()


def _transports_from_request(request: Request) -> dict[str, httpx.BaseTransport] | None:
    transports: dict[str, httpx.BaseTransport] | None = getattr(
        request.app.state, "media_transports", None
    )
    return transports


@router.get("/overview")
def get_media_overview(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Return unified read-only Media & Downloads overview, scheduler state, and active alerts."""
    transports = _transports_from_request(request)
    with db_session(settings.db_path) as conn:
        snap = collect_media_telemetry(settings, conn=conn, transports=transports)
    snap["scheduler"] = _scheduler_summary(request)
    return snap


@router.get("/services")
def get_media_services(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Return compact status matrix for all 7 Media & Downloads connectors."""
    transports = _transports_from_request(request)
    with db_session(settings.db_path) as conn:
        snap = collect_media_telemetry(settings, conn=conn, transports=transports)

    compact_services: dict[str, dict[str, Any]] = {}
    for name, svc in snap["services"].items():
        compact_services[name] = {
            "service": svc["service"],
            "title": svc["title"],
            "category": svc["category"],
            "enabled": svc["enabled"],
            "configured": svc["configured"],
            "status": svc["status"],
            "error_code": svc["error_code"],
            "reason": svc["reason"],
            "latency_ms": svc["latency_ms"],
            "version": svc["version"],
            "collected_at": svc["collected_at"],
            "stale": svc["stale"],
            "age_seconds": svc["age_seconds"],
            "consecutive_failures": svc["consecutive_failures"],
            "read_only_enforced": svc["read_only_enforced"],
        }

    return {
        "collected_at": snap["collected_at"],
        "overall_status": snap["overall_status"],
        "adapter_enabled": snap["adapter_enabled"],
        "services": compact_services,
        "services_list": list(compact_services.values()),
    }


def _single_service_endpoint(
    request: Request,
    service_name: str,
    settings: Settings,
) -> dict[str, Any]:
    transports = _transports_from_request(request)
    with db_session(settings.db_path) as conn:
        return collect_single_media_service(
            settings, service_name, conn=conn, transports=transports
        )


@router.get("/jellyfin")
def get_jellyfin_status(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Return read-only Jellyfin server, library, active sessions, and transcode telemetry."""
    return _single_service_endpoint(request, "jellyfin", settings)


@router.get("/qbittorrent")
def get_qbittorrent_status(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Return read-only qBittorrent transfer speeds, torrent state counts, and stalled queue."""
    return _single_service_endpoint(request, "qbittorrent", settings)


@router.get("/sonarr")
def get_sonarr_status(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Return read-only Sonarr v3 series, queue, missing episodes, and health telemetry."""
    return _single_service_endpoint(request, "sonarr", settings)


@router.get("/radarr")
def get_radarr_status(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Return read-only Radarr v3 movie, queue, missing movies, and health telemetry."""
    return _single_service_endpoint(request, "radarr", settings)


@router.get("/bazarr")
def get_bazarr_status(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Return read-only Bazarr missing subtitles, provider health, and system issues."""
    return _single_service_endpoint(request, "bazarr", settings)


@router.get("/prowlarr")
def get_prowlarr_status(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Return read-only Prowlarr v1 indexer counts, failing indexers, and health warnings."""
    return _single_service_endpoint(request, "prowlarr", settings)


@router.get("/seerr")
def get_seerr_status(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Return read-only Seerr v1 media request counts and recent requests."""
    return _single_service_endpoint(request, "seerr", settings)


@router.post("/collect")
def trigger_media_collection(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_csrf),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Trigger an immediate read-only Media & Downloads collection and persist to SQLite."""
    client_ip = request.client.host if request.client else "unknown"
    transports = _transports_from_request(request)

    with db_session(settings.db_path) as conn:
        snapshot = collect_media_telemetry(
            settings, conn=conn, transports=transports
        )
        snapshot_id = persist_media_snapshot(
            conn,
            snapshot,
            retention_limit=settings.media_history_retention_limit,
            min_persist_interval_seconds=0,
            db_key=str(settings.db_path),
        )
        record_audit_log(
            conn,
            actor=principal.username,
            action="media.snapshot_collected",
            target_type="media_metric_snapshot",
            target_id=str(snapshot_id),
            details={
                "overall_status": snapshot["overall_status"],
                "alerts_count": len(snapshot["alerts"]),
            },
            ip_address=client_ip,
        )

    snapshot["scheduler"] = _scheduler_summary(request)
    return {"snapshot_id": snapshot_id, **snapshot}


@router.get("/alerts")
def list_media_alerts(
    include_resolved: bool = Query(default=False),
    service: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    """Return persisted Media & Downloads alerts with active/resolved and service filtering."""
    with db_session(settings.db_path) as conn:
        return query_media_alerts(
            conn,
            include_resolved=include_resolved,
            service=service,
            limit=limit,
        )


@router.get("/history")
def list_media_history(
    limit: int = Query(default=20, ge=1, le=200),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    """Return recent persisted Media & Downloads metric snapshots."""
    with db_session(settings.db_path) as conn:
        return query_media_history(conn, limit=limit)
