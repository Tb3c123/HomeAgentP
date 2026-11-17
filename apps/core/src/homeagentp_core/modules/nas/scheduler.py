"""Background NAS Guardian collection scheduler (P02-F02)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeagentp_core.config import Settings
from homeagentp_core.db.connection import db_session
from homeagentp_core.modules.nas.collector import (
    collect_nas_telemetry,
    persist_nas_snapshot,
)
from homeagentp_core.scheduler import HardenedPeriodicScheduler

CollectorCallable = Callable[[Settings], dict[str, Any]]


class NasCollectionScheduler(HardenedPeriodicScheduler):
    """Asyncio background scheduler for periodic read-only NAS Guardian telemetry collection."""

    def __init__(
        self,
        settings: Settings,
        *,
        collector_fn: CollectorCallable | None = None,
        shutdown_timeout_seconds: float = 2.0,
    ) -> None:
        self._settings = settings
        self._collector_fn: CollectorCallable = collector_fn or (
            lambda cfg: collect_nas_telemetry(cfg, sample_delay_seconds=0.01)
        )
        super().__init__(
            worker_name_prefix="nas-guardian-worker",
            task_name="nas-guardian-scheduler",
            shutdown_timeout_seconds=shutdown_timeout_seconds,
        )

    def _is_enabled(self) -> bool:
        return bool(
            self._settings.nas_scheduler_enabled and self._settings.nas_adapter_enabled
        )

    def _interval_seconds(self) -> int:
        return self._settings.nas_collection_interval_seconds

    def _timeout_seconds(self) -> float:
        return self._settings.nas_collection_timeout_seconds

    def _min_persist_interval_seconds(self) -> int:
        return self._settings.nas_min_persist_interval_seconds

    def _extract_status(self, snapshot: dict[str, Any]) -> str:
        return str(snapshot.get("adapter_status", "ok"))

    def _execute_sync(self, *, force_persist: bool = False) -> dict[str, Any]:
        """Execute NAS telemetry collection and throttled SQLite persistence."""
        snapshot = self._collector_fn(self._settings)
        adapter_st = str(snapshot.get("adapter_status", "unavailable"))
        snapshot_id = 0
        if force_persist or adapter_st != "unavailable":
            min_interval = (
                0 if force_persist else self._settings.nas_min_persist_interval_seconds
            )
            with db_session(self._settings.db_path) as conn:
                snapshot_id = persist_nas_snapshot(
                    conn,
                    snapshot,
                    retention_limit=self._settings.nas_history_retention_limit,
                    min_persist_interval_seconds=min_interval,
                    db_key=str(self._settings.db_path),
                )
        return {"snapshot_id": snapshot_id, "snapshot": snapshot}
