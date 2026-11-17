"""Media & Downloads alert lifecycle synchronization and SQLite querying."""

from __future__ import annotations

import json
import sqlite3
from typing import Any


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
