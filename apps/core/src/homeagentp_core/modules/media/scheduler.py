"""Background Media & Downloads collection scheduler (Phase 03).

Invariants:
- Runs independently of Dashboard browser requests inside the FastAPI lifespan when enabled.
- Configurable polling interval (default 90s, recommended 60-120s).
- Non-overlapping execution: guarded by an `asyncio.Lock` so concurrent cycles never overlap
  or overload Jellyfin / qBittorrent / *arr services.
- Timeout & Fault Isolation: wraps each collection + SQLite persistence step in
  `asyncio.wait_for(..., timeout=settings.media_collection_timeout_seconds)`.
- SSD Write Protection: skips background SQLite snapshot writes when
  `overall_status == 'unavailable'` and enforces `settings.media_min_persist_interval_seconds`.
- Graceful shutdown: cancels the sleep/wait loop cleanly on FastAPI shutdown.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from homeagentp_core.config import Settings
from homeagentp_core.db.connection import db_session
from homeagentp_core.logging import redact_text
from homeagentp_core.modules.media.collector import (
    collect_media_telemetry,
    persist_media_snapshot,
)

MediaCollectorCallable = Callable[[Settings], dict[str, Any]]


class MediaCollectionScheduler:
    """Asyncio background scheduler for periodic read-only Media & Downloads polling."""

    def __init__(
        self,
        settings: Settings,
        *,
        collector_fn: MediaCollectorCallable | None = None,
    ) -> None:
        self._settings = settings
        self._collector_fn = collector_fn
        self._lock = asyncio.Lock()
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

        self.running: bool = False
        self.in_progress: bool = False
        self.last_run_at: str | None = None
        self.last_success_at: str | None = None
        self.last_status: str = "idle"
        self.last_error: str | None = None
        self.last_snapshot_id: int | None = None
        self.run_count: int = 0
        self.skipped_overlap_count: int = 0

    def status_summary(self) -> dict[str, Any]:
        """Return current scheduler state for `/api/v1/media/overview` and Dashboard inspection."""
        return {
            "enabled": bool(
                self._settings.media_scheduler_enabled and self._settings.media_adapter_enabled
            ),
            "running": self.running,
            "in_progress": self.in_progress,
            "interval_seconds": self._settings.media_collection_interval_seconds,
            "timeout_seconds": self._settings.media_collection_timeout_seconds,
            "min_persist_interval_seconds": self._settings.media_min_persist_interval_seconds,
            "last_run_at": self.last_run_at,
            "last_success_at": self.last_success_at,
            "last_status": self.last_status,
            "last_error": self.last_error,
            "last_snapshot_id": self.last_snapshot_id,
            "run_count": self.run_count,
            "skipped_overlap_count": self.skipped_overlap_count,
        }

    def _collect_and_persist_sync(self, *, force_persist: bool = False) -> dict[str, Any]:
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

    async def run_once(self, *, force_persist: bool = False) -> dict[str, Any] | None:
        """Execute a single non-overlapping collection cycle with timeout protection."""
        if self._lock.locked():
            self.skipped_overlap_count += 1
            return None

        async with self._lock:
            self.in_progress = True
            self.last_run_at = datetime.now(UTC).isoformat()
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        self._collect_and_persist_sync, force_persist=force_persist
                    ),
                    timeout=self._settings.media_collection_timeout_seconds,
                )
                snap = result["snapshot"]
                self.last_snapshot_id = int(result["snapshot_id"])
                self.last_success_at = self.last_run_at
                self.last_status = str(
                    snap.get("overall_status") or snap.get("status", "online")
                )
                self.last_error = None
                self.run_count += 1
                return result
            except TimeoutError:
                self.last_status = "timeout"
                self.last_error = (
                    f"Media collection timed out after "
                    f"{self._settings.media_collection_timeout_seconds}s."
                )
                return None
            except Exception as exc:
                self.last_status = "error"
                self.last_error = redact_text(f"{type(exc).__name__}: {exc}")
                return None
            finally:
                self.in_progress = False

    async def _loop(self) -> None:
        while not self._stop_event.is_set():
            await self.run_once(force_persist=False)
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=float(self._settings.media_collection_interval_seconds),
                )
            except TimeoutError:
                continue

    async def start(self) -> None:
        """Start the background loop if enabled in Settings."""
        if not (
            self._settings.media_scheduler_enabled and self._settings.media_adapter_enabled
        ):
            self.running = False
            self.last_status = "disabled"
            return
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self.running = True
        self.last_status = "starting"
        self._task = asyncio.create_task(
            self._loop(), name="media-downloads-scheduler"
        )

    async def stop(self) -> None:
        """Gracefully stop the background loop and wait for any in-flight cycle to finish."""
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        self.running = False
        if self.last_status == "starting":
            self.last_status = "stopped"
