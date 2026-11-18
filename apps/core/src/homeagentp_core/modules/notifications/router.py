"""FastAPI router for Phase 05 notification preferences and outbox history (P05-F02)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from homeagentp_core.auth.security import (
    AuthenticatedPrincipal,
    get_current_principal,
    get_settings,
)
from homeagentp_core.config import Settings
from homeagentp_core.db.connection import db_session
from homeagentp_core.modules.notifications.evaluator import evaluate_alerts_to_outbox
from homeagentp_core.modules.notifications.outbox import list_deliveries
from homeagentp_core.modules.notifications.preferences import (
    get_notification_preferences,
    update_notification_preferences,
)
from homeagentp_core.modules.notifications.schemas import (
    DeliveryStatus,
    NotificationDeliveryOut,
    NotificationEvaluateOut,
    NotificationPreferencesOut,
    NotificationPreferencesUpdate,
)
from homeagentp_core.modules.workspace.security import require_workspace_owner

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


@router.get("/preferences", response_model=NotificationPreferencesOut)
def get_notification_preferences_endpoint(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> NotificationPreferencesOut:
    with db_session(settings.db_path) as conn:
        return get_notification_preferences(conn, settings)


@router.put("/preferences", response_model=NotificationPreferencesOut)
def update_notification_preferences_endpoint(
    payload: NotificationPreferencesUpdate,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_workspace_owner),
    settings: Settings = Depends(get_settings),
) -> NotificationPreferencesOut:
    client_ip = request.client.host if request.client else "unknown"
    with db_session(settings.db_path) as conn:
        return update_notification_preferences(
            conn,
            settings,
            payload=payload,
            actor=principal.username,
            ip_address=client_ip,
        )


@router.get("/deliveries", response_model=list[NotificationDeliveryOut])
def list_notification_deliveries_endpoint(
    status: DeliveryStatus | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=10000),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> list[NotificationDeliveryOut]:
    with db_session(settings.db_path) as conn:
        return list_deliveries(conn, limit=limit, offset=offset, status=status)


@router.post("/evaluate", response_model=NotificationEvaluateOut)
def evaluate_notifications_endpoint(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_workspace_owner),
    settings: Settings = Depends(get_settings),
) -> NotificationEvaluateOut:
    with db_session(settings.db_path) as conn:
        return evaluate_alerts_to_outbox(conn, settings)
