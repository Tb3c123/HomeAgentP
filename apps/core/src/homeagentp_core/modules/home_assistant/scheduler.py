"""Background Home Assistant read-only collection scheduler (P05-F04)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeagentp_core.config import Settings
from homeagentp_core.db.connection import db_session
from homeagentp_core.modules.home_assistant.collector import (
    collect_ha_telemetry,
    persist_ha_snapshot,
)
from homeagentp_core.scheduler import HardenedPeriodicScheduler

HaCollectorCallable = Callable[[Settings], dict[str, Any]]


class HomeAssistantCollectionScheduler(HardenedPeriodicScheduler):
    """Asyncio background scheduler for periodic read-only Home Assistant polling."""

    def __init__(
        self,
        settings: Settings,
        *,
        collector_fn: HaCollectorCallable | None = None,
        shutdown_timeout_seconds: float = 2.0,
    ) -> None:
        self._settings = settings
        self._collector_fn = collector_fn
        super().__init__(
            worker_name_prefix="ha-telemetry-worker",
            task_name="ha-telemetry-scheduler",
            shutdown_timeout_seconds=shutdown_timeout_seconds,
        )

    def _is_enabled(self) -> bool:
        return bool(self._settings.ha_scheduler_enabled and self._settings.ha_enabled)

    def _interval_seconds(self) -> int:
        return self._settings.ha_collection_interval_seconds

    def _timeout_seconds(self) -> float:
        return self._settings.ha_collection_timeout_seconds

    def _min_persist_interval_seconds(self) -> int:
        return self._settings.ha_min_persist_interval_seconds

    def _extract_status(self, snapshot: dict[str, Any]) -> str:
        return str(snapshot.get("status", "unavailable"))

    def _execute_sync(self, *, force_persist: bool = False) -> dict[str, Any]:
        """Execute HA telemetry collection and bounded SQLite persistence."""
        snapshot = (
            self._collector_fn(self._settings)
            if self._collector_fn is not None
            else collect_ha_telemetry(self._settings)
        )
        with db_session(self._settings.db_path) as conn:
            min_interval = 0 if force_persist else self._settings.ha_min_persist_interval_seconds
            # Always persist 'unavailable' transitions immediately so stale online state is cleared
            force_flag = force_persist or snapshot.get("status") == "unavailable"
            snapshot_id = persist_ha_snapshot(
                conn,
                snapshot,
                retention_limit=self._settings.ha_history_retention_limit,
                min_persist_interval_seconds=min_interval,
                db_key=str(self._settings.db_path),
                force=force_flag,
            )
        return {"snapshot_id": snapshot_id, "snapshot": snapshot}
