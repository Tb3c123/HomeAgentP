"""Bounded Home Assistant telemetry collector, persistence, and overview builder (P05-F01)."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

import httpx

from homeagentp_core.config import Settings
from homeagentp_core.modules.home_assistant.client import (
    HaClientError,
    HomeAssistantReadOnlyClient,
)
from homeagentp_core.modules.home_assistant.schemas import (
    HaEntityStateOut,
    HaOverviewResponse,
)
from homeagentp_core.modules.home_assistant.security import (
    HaSecurityError,
    minimize_ha_state_payload,
    validate_ha_allowlist,
)

_LAST_PERSIST_BY_DB: dict[str, float] = {}


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _parse_iso_age_seconds(iso_ts: str | None) -> float | None:
    if not iso_ts:
        return None
    try:
        dt = datetime.fromisoformat(iso_ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return max(0.0, (_utc_now() - dt).total_seconds())
    except ValueError:
        return None


def collect_ha_telemetry(
    settings: Settings,
    *,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    """Collect read-only Home Assistant states for allowlisted entities."""
    now_iso = _utc_now_iso()
    if not settings.ha_enabled:
        return {
            "status": "unavailable",
            "enabled": False,
            "reason": "Home Assistant integration is disabled (opt-in).",
            "collected_at": now_iso,
            "entities": [],
        }

    if not settings.home_assistant_url.strip() or not settings.ha_token.strip():
        return {
            "status": "unavailable",
            "enabled": True,
            "reason": "Home Assistant URL or token is not configured.",
            "collected_at": now_iso,
            "entities": [],
        }

    try:
        allowlist = validate_ha_allowlist(settings.ha_allowed_entities)
        client = HomeAssistantReadOnlyClient(
            base_url=settings.home_assistant_url,
            token=settings.ha_token,
            allowed_hosts=settings.ha_allowed_hosts,
            timeout_seconds=settings.ha_http_timeout_seconds,
            max_response_bytes=settings.ha_max_response_bytes,
            transport=transport,
        )
        client.check_health()
    except (HaSecurityError, HaClientError) as exc:
        return {
            "status": "unavailable",
            "enabled": True,
            "reason": str(exc),
            "collected_at": now_iso,
            "entities": [],
        }

    entities: list[dict[str, Any]] = []
    errors: list[str] = []
    for entity_id in allowlist:
        try:
            raw = client.get_entity_state(entity_id)
            state, friendly_name, attrs, last_changed = minimize_ha_state_payload(
                raw, expected_entity_id=entity_id
            )
            entities.append(
                {
                    "entity_id": entity_id,
                    "domain": entity_id.split(".", 1)[0],
                    "friendly_name": friendly_name,
                    "state": state,
                    "attributes": attrs,
                    "status": "online",
                    "last_changed": last_changed,
                    "collected_at": now_iso,
                }
            )
        except HaClientError as exc:
            errors.append(f"{entity_id}: {exc.code}")
            entities.append(
                {
                    "entity_id": entity_id,
                    "domain": entity_id.split(".", 1)[0],
                    "friendly_name": entity_id,
                    "state": "unavailable",
                    "attributes": {},
                    "status": "unavailable",
                    "last_changed": None,
                    "collected_at": now_iso,
                }
            )

    overall_status = "degraded" if errors else "online"
    reason = (
        f"Collected {len(entities) - len(errors)}/{len(entities)} allowlisted entities."
        if entities
        else "Connected to Home Assistant (no allowlisted entities configured)."
    )
    return {
        "status": overall_status,
        "enabled": True,
        "reason": reason,
        "collected_at": now_iso,
        "entities": entities,
    }


def persist_ha_snapshot(
    conn: sqlite3.Connection,
    snapshot: dict[str, Any],
    *,
    retention_limit: int = 200,
    min_persist_interval_seconds: int = 30,
    db_key: str = "",
    force: bool = False,
) -> int:
    """Persist minimized HA entity states and bounded snapshot history."""
    now_epoch = _utc_now().timestamp()
    if not force and db_key and min_persist_interval_seconds > 0:
        last_ts = _LAST_PERSIST_BY_DB.get(db_key, 0.0)
        if (now_epoch - last_ts) < min_persist_interval_seconds:
            return 0

    entities: list[dict[str, Any]] = snapshot.get("entities", [])
    for ent in entities:
        conn.execute(
            """
            INSERT INTO ha_entity_states (
                entity_id, domain, friendly_name, state, attributes_json,
                status, last_changed, collected_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(entity_id) DO UPDATE SET
                domain = excluded.domain,
                friendly_name = excluded.friendly_name,
                state = excluded.state,
                attributes_json = excluded.attributes_json,
                status = excluded.status,
                last_changed = excluded.last_changed,
                collected_at = excluded.collected_at
            """,
            (
                ent["entity_id"],
                ent["domain"],
                ent["friendly_name"],
                ent["state"],
                json.dumps(ent.get("attributes", {}), ensure_ascii=False),
                ent["status"],
                ent.get("last_changed"),
                ent["collected_at"],
            ),
        )

    cur = conn.execute(
        """
        INSERT INTO ha_entity_snapshots (collected_at, overall_status, entity_count, summary_json)
        VALUES (?, ?, ?, ?)
        """,
        (
            snapshot["collected_at"],
            snapshot["status"],
            len(entities),
            json.dumps({"reason": snapshot.get("reason", "")}, ensure_ascii=False),
        ),
    )
    snapshot_id = int(cur.lastrowid or 0)

    conn.execute(
        """
        DELETE FROM ha_entity_snapshots
        WHERE id NOT IN (
            SELECT id FROM ha_entity_snapshots ORDER BY id DESC LIMIT ?
        )
        """,
        (retention_limit,),
    )
    if db_key:
        _LAST_PERSIST_BY_DB[db_key] = now_epoch
    return snapshot_id


def get_ha_overview(conn: sqlite3.Connection, settings: Settings) -> HaOverviewResponse:
    """Build current Home Assistant overview from persisted state with staleness detection."""
    if not settings.ha_enabled:
        return HaOverviewResponse(
            status="unavailable",
            enabled=False,
            reason="Home Assistant integration is disabled (opt-in).",
            entity_count=0,
            entities=[],
        )

    latest = conn.execute("SELECT * FROM ha_entity_snapshots ORDER BY id DESC LIMIT 1").fetchone()
    rows = conn.execute("SELECT * FROM ha_entity_states ORDER BY entity_id ASC").fetchall()

    if latest is None:
        return HaOverviewResponse(
            status="unavailable",
            enabled=True,
            reason="No Home Assistant snapshot collected yet.",
            entity_count=0,
            entities=[],
        )

    collected_at = str(latest["collected_at"])
    age = _parse_iso_age_seconds(collected_at)
    is_stale = age is not None and age > settings.ha_snapshot_stale_seconds
    status = "stale" if is_stale else str(latest["overall_status"])
    summary = json.loads(str(latest["summary_json"] or "{}"))
    reason = (
        f"Last Home Assistant snapshot is stale ({int(age or 0)}s old)."
        if is_stale
        else str(summary.get("reason", "Home Assistant telemetry active."))
    )

    entities = [
        HaEntityStateOut(
            entity_id=str(r["entity_id"]),
            domain=str(r["domain"]),
            friendly_name=str(r["friendly_name"]),
            state=str(r["state"]),
            attributes=json.loads(str(r["attributes_json"] or "{}")),
            status="stale" if is_stale else r["status"],
            last_changed=r["last_changed"],
            collected_at=str(r["collected_at"]),
        )
        for r in rows
    ]
    return HaOverviewResponse(
        status=status,  # type: ignore[arg-type]
        enabled=True,
        reason=reason,
        collected_at=collected_at,
        entity_count=len(entities),
        entities=entities,
    )
