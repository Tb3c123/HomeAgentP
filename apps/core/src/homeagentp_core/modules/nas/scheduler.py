"""Background NAS Guardian collection scheduler (P02-F02).

Invariants:
- Runs independently of Dashboard requests inside the FastAPI lifespan when enabled.
- Non-overlapping execution: protected by an `asyncio.Lock` so two collections never overlap.
- Timeout & Error resilience: wraps each collection + SQLite persistence step in
  `asyncio.wait_for(..., timeout=settings.nas_collection_timeout_seconds)` and records clear
  timestamps and error states (`last_run_at`, `last_success_at`, `last_status`, `last_error`).
- Excessive SQLite write protection: skips persisting snapshots when telemetry is `unavailable`
  and enforces `settings.nas_min_persist_interval_seconds` via `persist_nas_snapshot()`.
- Graceful shutdown: cancels the sleep/wait loop cleanly on FastAPI shutdown without leaving
  dangling tasks or open SQLite transactions.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from homeagentp_core.config import Settings
from homeagentp_core.db.connection import db_session
from homeagentp_core.modules.nas.collector import (
    collect_nas_telemetry,
    persist_nas_snapshot,
)

CollectorCallable = Callable[[Settings], dict[str, Any]]


class NasCollectionScheduler:
    """Asyncio background scheduler for periodic read-only NAS Guardian telemetry collection."""

    def __init__(
        self,
        settings: Settings,
        *,
        collector_fn: CollectorCallable | None = None,
    ) -> None:
        self._settings = settings
        self._collector_fn: CollectorCallable = collector_fn or (
            lambda cfg: collect_nas_telemetry(cfg, sample_delay_seconds=0.01)
        )
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
        """Return current scheduler state for `/api/v1/nas/status` and Dashboard inspection."""
        return {
            "enabled": bool(
                self._settings.nas_scheduler_enabled and self._settings.nas_adapter_enabled
            ),
            "running": self.running,
            "in_progress": self.in_progress,
            "interval_seconds": self._settings.nas_collection_interval_seconds,
            "timeout_seconds": self._settings.nas_collection_timeout_seconds,
            "min_persist_interval_seconds": self._settings.nas_min_persist_interval_seconds,
            "last_run_at": self.last_run_at,
            "last_success_at": self.last_success_at,
            "last_status": self.last_status,
            "last_error": self.last_error,
            "last_snapshot_id": self.last_snapshot_id,
            "run_count": self.run_count,
            "skipped_overlap_count": self.skipped_overlap_count,
        }

    def _collect_and_persist_sync(self, *, force_persist: bool = False) -> dict[str, Any]:
        snapshot = self._collector_fn(self._settings)
        adapter_st = str(snapshot.get("adapter_status", "unavailable"))
        snapshot_id = 0
        # Avoid excessive SQLite writes when telemetry is unavailable unless forced by manual API
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
                    timeout=self._settings.nas_collection_timeout_seconds,
                )
                snap = result["snapshot"]
                self.last_snapshot_id = int(result["snapshot_id"])
                self.last_success_at = self.last_run_at
                self.last_status = str(snap.get("adapter_status", "ok"))
                self.last_error = None
                self.run_count += 1
                return result
            except TimeoutError:
                self.last_status = "timeout"
                self.last_error = (
                    f"Collection timed out after "
                    f"{self._settings.nas_collection_timeout_seconds}s."
                )
                return None
            except Exception as exc:
                self.last_status = "error"
                self.last_error = f"{type(exc).__name__}: {exc}"
                return None
            finally:
                self.in_progress = False

    async def _loop(self) -> None:
        while not self._stop_event.is_set():
            await self.run_once(force_persist=False)
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=float(self._settings.nas_collection_interval_seconds),
                )
            except TimeoutError:
                continue

    async def start(self) -> None:
        """Start the background loop if enabled in Settings."""
        if not (self._settings.nas_scheduler_enabled and self._settings.nas_adapter_enabled):
            self.running = False
            self.last_status = "disabled"
            return
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self.running = True
        self.last_status = "starting"
        self._task = asyncio.create_task(self._loop(), name="nas-guardian-scheduler")

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
