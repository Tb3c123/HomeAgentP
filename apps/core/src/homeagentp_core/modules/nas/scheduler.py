"""Background NAS Guardian collection scheduler (P02-F02).

Invariants:
- Runs independently of Dashboard requests inside the FastAPI lifespan when enabled.
- True Non-Overlapping Worker Execution:
  * Uses a single-worker executor (`ThreadPoolExecutor(max_workers=1)`) plus an explicit
    `_worker_busy` guard (`threading.Lock`) that is released ONLY inside the worker thread's own
    `finally:` block, not merely when `asyncio.wait_for()` cancels the awaiting coroutine.
  * If a previous worker thread timed out in `asyncio.wait_for()` and is still blocked on OS I/O
    in the background, subsequent `run_once()` calls detect `_worker_busy.locked()` and skip
    (`skipped_overlap_count += 1`, `last_status = "skipped_worker_busy"`) instead of spawning a
    second concurrent collection thread.
- Timeout & Error resilience: wraps each collection + SQLite persistence step in
  `asyncio.wait_for(..., timeout=settings.nas_collection_timeout_seconds)` and records clear
  timestamps and error states (`last_run_at`, `last_success_at`, `last_status`, `last_error`).
- Excessive SQLite write protection: skips persisting snapshots when telemetry is `unavailable`
  and enforces `settings.nas_min_persist_interval_seconds` via `persist_nas_snapshot()`.
- Graceful shutdown: cancels the sleep/wait loop cleanly on FastAPI shutdown and shuts down the
  single-worker executor without leaving dangling tasks or open SQLite transactions.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
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
        shutdown_timeout_seconds: float = 2.0,
    ) -> None:
        self._settings = settings
        self._collector_fn: CollectorCallable = collector_fn or (
            lambda cfg: collect_nas_telemetry(cfg, sample_delay_seconds=0.01)
        )
        self._shutdown_timeout_seconds = max(0.0, float(shutdown_timeout_seconds))
        self._lock = asyncio.Lock()
        self._worker_lock = threading.Lock()
        self._worker_done_event = threading.Event()
        self._worker_done_event.set()
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="nas-guardian-worker"
        )
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

        self.running: bool = False
        self.stopping: bool = False
        self.in_progress: bool = False
        self.worker_thread_busy: bool = False
        self.last_run_at: str | None = None
        self.last_success_at: str | None = None
        self.last_status: str = "idle"
        self.last_error: str | None = None
        self.last_snapshot_id: int | None = None
        self.run_count: int = 0
        self.skipped_overlap_count: int = 0

    def status_summary(self) -> dict[str, Any]:
        """Return current scheduler state for `/api/v1/nas/status` and Dashboard inspection."""
        worker_busy = self._worker_lock.locked()
        return {
            "enabled": bool(
                self._settings.nas_scheduler_enabled and self._settings.nas_adapter_enabled
            ),
            "running": self.running,
            "stopping": self.stopping,
            "in_progress": self.in_progress or worker_busy,
            "worker_thread_busy": worker_busy,
            "interval_seconds": self._settings.nas_collection_interval_seconds,
            "timeout_seconds": self._settings.nas_collection_timeout_seconds,
            "shutdown_timeout_seconds": self._shutdown_timeout_seconds,
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
        """Run inside the dedicated single worker thread holding `_worker_lock`."""
        try:
            snapshot = self._collector_fn(self._settings)
            adapter_st = str(snapshot.get("adapter_status", "unavailable"))
            snapshot_id = 0
            # Avoid excessive SQLite writes when telemetry is unavailable unless forced
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
        finally:
            self.worker_thread_busy = False
            self._worker_lock.release()
            self._worker_done_event.set()
            if self.stopping and not self.running:
                self.stopping = False
                self.last_status = "stopped"
                self.last_error = None

    async def run_once(self, *, force_persist: bool = False) -> dict[str, Any] | None:
        """Execute a single non-overlapping collection cycle with worker-level overlap guard."""
        if self.stopping or self._stop_event.is_set():
            self.last_status = (
                "stopping_worker_hung" if self._worker_lock.locked() else "stopped"
            )
            self.last_error = (
                "Scheduler is shutting down or stopped; rejecting new collection cycle."
            )
            return None

        if self._lock.locked() or self._worker_lock.locked():
            self.skipped_overlap_count += 1
            if self._worker_lock.locked() and not self._lock.locked():
                self.last_status = "skipped_worker_busy"
                self.last_error = (
                    "Previous collection worker thread is still finishing after a timeout; "
                    "skipping cycle to prevent overlapping worker execution."
                )
            return None

        async with self._lock:
            if self.stopping or self._stop_event.is_set():
                self.last_status = (
                    "stopping_worker_hung" if self._worker_lock.locked() else "stopped"
                )
                return None

            if not self._worker_lock.acquire(blocking=False):
                self.skipped_overlap_count += 1
                self.last_status = "skipped_worker_busy"
                return None

            self._worker_done_event.clear()
            self.worker_thread_busy = True
            self.in_progress = True
            self.last_run_at = datetime.now(UTC).isoformat()
            loop = asyncio.get_running_loop()
            try:
                future = loop.run_in_executor(
                    self._executor,
                    lambda: self._collect_and_persist_sync(force_persist=force_persist),
                )
                result = await asyncio.wait_for(
                    future,
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
                    f"{self._settings.nas_collection_timeout_seconds}s "
                    "(underlying worker remains guarded until it exits)."
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
            self.stopping = False
            self.last_status = "disabled"
            return
        if self._worker_lock.locked():
            self.running = False
            self.stopping = True
            self.last_status = "stopping_worker_hung"
            return
        if self._task is not None and not self._task.done():
            return
        if getattr(self._executor, "_shutdown", False):
            self._executor = ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="nas-guardian-worker"
            )
        self._stop_event.clear()
        self.stopping = False
        self.running = True
        self.last_status = "starting"
        self._task = asyncio.create_task(self._loop(), name="nas-guardian-scheduler")

    async def stop(self, *, wait_timeout: float | None = None) -> dict[str, Any]:
        """Stop the background loop with a bounded wait for any active worker thread.

        Never claims `last_status == "stopped"` if the underlying worker thread is still
        blocked on OS I/O after `wait_timeout` expires; instead reports
        `last_status = "stopping_worker_hung"`, `stopping = True`, and
        `worker_thread_busy = True`.
        """
        self.stopping = True
        self._stop_event.set()
        self.last_status = "stopping"

        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

        bound = (
            self._shutdown_timeout_seconds
            if wait_timeout is None
            else max(0.0, float(wait_timeout))
        )
        if self._worker_lock.locked() and bound > 0.0:
            loop = asyncio.get_running_loop()
            deadline = loop.time() + bound
            while self._worker_lock.locked():
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break
                await asyncio.sleep(min(0.02, remaining))

        if self._worker_lock.locked():
            self._executor.shutdown(wait=False, cancel_futures=True)
            self.running = False
            self.stopping = True
            self.worker_thread_busy = True
            self.last_status = "stopping_worker_hung"
            self.last_error = (
                f"Scheduler loop stopped, but underlying worker thread is still active "
                f"after {bound:.2f}s bounded shutdown timeout."
            )
        else:
            self._executor.shutdown(wait=True, cancel_futures=True)
            self.running = False
            self.stopping = False
            self.worker_thread_busy = False
            self.last_status = "stopped"

        return self.status_summary()
