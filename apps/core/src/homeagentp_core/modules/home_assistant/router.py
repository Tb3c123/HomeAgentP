"""FastAPI router for Phase 05 read-only Home Assistant monitoring (P05-F01)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from homeagentp_core.auth.security import (
    AuthenticatedPrincipal,
    get_current_principal,
    get_settings,
)
from homeagentp_core.config import Settings
from homeagentp_core.db.connection import db_session
from homeagentp_core.modules.home_assistant.collector import (
    collect_ha_telemetry,
    get_ha_overview,
    persist_ha_snapshot,
)
from homeagentp_core.modules.home_assistant.schemas import HaOverviewResponse
from homeagentp_core.modules.workspace.security import require_workspace_owner

router = APIRouter(prefix="/api/v1/home-assistant", tags=["home_assistant"])


@router.get("/overview", response_model=HaOverviewResponse)
def get_home_assistant_overview_endpoint(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> HaOverviewResponse:
    with db_session(settings.db_path) as conn:
        return get_ha_overview(conn, settings)


@router.post("/collect", response_model=HaOverviewResponse)
def collect_home_assistant_endpoint(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_workspace_owner),
    settings: Settings = Depends(get_settings),
) -> HaOverviewResponse:
    snapshot = collect_ha_telemetry(settings)
    with db_session(settings.db_path) as conn:
        if settings.ha_enabled:
            persist_ha_snapshot(
                conn,
                snapshot,
                retention_limit=settings.ha_history_retention_limit,
                min_persist_interval_seconds=0,
                db_key=str(settings.db_path),
                force=True,
            )
            return get_ha_overview(conn, settings)
        return HaOverviewResponse(
            status="unavailable",
            enabled=False,
            reason=str(snapshot.get("reason", "Home Assistant integration is disabled (opt-in).")),
            collected_at=str(snapshot.get("collected_at")),
            entity_count=0,
            entities=[],
        )
