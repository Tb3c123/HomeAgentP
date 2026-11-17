"""NAS Guardian API router: /api/v1/nas/status, /collect, /history, /alerts."""

from __future__ import annotations

import json
from typing import Any

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
from homeagentp_core.modules.nas.collector import (
    collect_nas_telemetry,
    persist_nas_snapshot,
    query_nas_alerts,
)
from homeagentp_core.modules.nas.scheduler import NasCollectionScheduler

router = APIRouter(prefix="/api/v1/nas", tags=["nas-guardian"])


def _scheduler_summary(request: Request) -> dict[str, Any]:
    sched: NasCollectionScheduler | None = getattr(request.app.state, "nas_scheduler", None)
    if sched is None:
        return {"enabled": False, "running": False, "last_status": "unavailable"}
    return sched.status_summary()


@router.get("/status")
def get_nas_status(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Return current read-only NAS Guardian snapshot, scheduler state, and active alerts."""
    snap = collect_nas_telemetry(settings)
    snap["scheduler"] = _scheduler_summary(request)
    with db_session(settings.db_path) as conn:
        db_active = query_nas_alerts(conn, include_resolved=False, limit=100)
        if db_active:
            snap["alerts"] = db_active
    return snap


@router.post("/collect")
def trigger_nas_collection(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_csrf),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Collect a read-only NAS telemetry snapshot and persist it to SQLite history."""
    client_ip = request.client.host if request.client else "unknown"
    snapshot = collect_nas_telemetry(settings)

    with db_session(settings.db_path) as conn:
        snapshot_id = persist_nas_snapshot(
            conn,
            snapshot,
            retention_limit=settings.nas_history_retention_limit,
            min_persist_interval_seconds=0,
            db_key=str(settings.db_path),
        )
        record_audit_log(
            conn,
            actor=principal.username,
            action="nas.snapshot_collected",
            target_type="nas_metric_snapshot",
            target_id=str(snapshot_id),
            details={
                "adapter_status": snapshot["adapter_status"],
                "alerts_count": len(snapshot["alerts"]),
            },
            ip_address=client_ip,
        )

    snapshot["scheduler"] = _scheduler_summary(request)
    return {"snapshot_id": snapshot_id, **snapshot}


@router.get("/history")
def list_nas_history(
    limit: int = Query(default=20, ge=1, le=200),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    """Return recent persisted NAS telemetry snapshots."""
    with db_session(settings.db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM nas_metric_snapshots ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        history: list[dict[str, Any]] = []
        for r in rows:
            history.append(
                {
                    "id": int(r["id"]),
                    "collected_at": str(r["collected_at"]),
                    "adapter_status": str(r["adapter_status"]),
                    "cpu_usage_percent": r["cpu_usage_percent"],
                    "load_1m": r["load_1m"],
                    "load_5m": r["load_5m"],
                    "load_15m": r["load_15m"],
                    "cpu_cores": r["cpu_cores"],
                    "ram_total_bytes": r["ram_total_bytes"],
                    "ram_available_bytes": r["ram_available_bytes"],
                    "ram_used_bytes": r["ram_used_bytes"],
                    "ram_usage_percent": r["ram_usage_percent"],
                    "swap_total_bytes": r["swap_total_bytes"],
                    "swap_used_bytes": r["swap_used_bytes"],
                    "swap_usage_percent": r["swap_usage_percent"],
                    "mounts": json.loads(str(r["mounts_json"])),
                    "alerts": json.loads(str(r["alerts_json"])),
                }
            )
        return history


@router.get("/alerts")
def list_nas_alerts(
    include_resolved: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    """Return persisted NAS Guardian alerts with active/resolved filtering (`include_resolved`)."""
    with db_session(settings.db_path) as conn:
        return query_nas_alerts(conn, include_resolved=include_resolved, limit=limit)
