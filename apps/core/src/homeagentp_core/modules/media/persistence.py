"""SQLite snapshot persistence, retention pruning, and history queries for Media Hub."""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

_LAST_MEDIA_PERSIST_EPOCH: dict[str, float] = {}


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
