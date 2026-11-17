"""Background Media & Downloads collection scheduler (Phase 03)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeagentp_core.config import Settings
from homeagentp_core.db.connection import db_session
from homeagentp_core.modules.media.collector import (
    collect_media_telemetry,
    persist_media_snapshot,
)
from homeagentp_core.scheduler import HardenedPeriodicScheduler

MediaCollectorCallable = Callable[[Settings], dict[str, Any]]


class MediaCollectionScheduler(HardenedPeriodicScheduler):
    """Asyncio background scheduler for periodic read-only Media & Downloads polling."""

    def __init__(
        self,
        settings: Settings,
        *,
        collector_fn: MediaCollectorCallable | None = None,
        shutdown_timeout_seconds: float = 2.0,
    ) -> None:
        self._settings = settings
        self._collector_fn = collector_fn
        super().__init__(
            worker_name_prefix="media-downloads-worker",
            task_name="media-downloads-scheduler",
            shutdown_timeout_seconds=shutdown_timeout_seconds,
        )

    def _is_enabled(self) -> bool:
        return bool(
            self._settings.media_scheduler_enabled and self._settings.media_adapter_enabled
        )

    def _interval_seconds(self) -> int:
        return self._settings.media_collection_interval_seconds

    def _timeout_seconds(self) -> float:
        return self._settings.media_collection_timeout_seconds

    def _min_persist_interval_seconds(self) -> int:
        return self._settings.media_min_persist_interval_seconds

    def _extract_status(self, snapshot: dict[str, Any]) -> str:
        return str(snapshot.get("overall_status") or snapshot.get("status", "online"))

    def _execute_sync(self, *, force_persist: bool = False) -> dict[str, Any]:
        """Execute Media telemetry collection and throttled SQLite persistence."""
        with db_session(self._settings.db_path) as conn:
            if self._collector_fn is not None:
                snapshot = self._collector_fn(self._settings)
            else:
                snapshot = collect_media_telemetry(self._settings, conn=conn)

            overall_st = str(
                snapshot.get("overall_status") or snapshot.get("status", "unavailable")
            )
            snapshot_id = 0
            if force_persist or overall_st != "unavailable":
                min_interval = (
                    0 if force_persist else self._settings.media_min_persist_interval_seconds
                )
                snapshot_id = persist_media_snapshot(
                    conn,
                    snapshot,
                    retention_limit=self._settings.media_history_retention_limit,
                    min_persist_interval_seconds=min_interval,
                    db_key=str(self._settings.db_path),
                )
        return {"snapshot_id": snapshot_id, "snapshot": snapshot}
