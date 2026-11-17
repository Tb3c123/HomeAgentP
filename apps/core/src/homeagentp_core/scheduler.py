"""Shared hardened single-worker periodic scheduler for HomeAgentP Core.

Invariants:
- True Non-Overlapping Worker Execution:
  * Uses a single-worker executor (`ThreadPoolExecutor(max_workers=1)`) plus an explicit
    `_worker_lock` (`threading.Lock`) released ONLY inside the worker thread's own
    `finally:` block, not merely when `asyncio.wait_for()` cancels the awaiting coroutine.
  * If a previous worker thread timed out in `asyncio.wait_for()` and is still blocked on
    I/O in the background, subsequent `run_once()` calls detect `_worker_lock.locked()` and
    skip (`skipped_overlap_count += 1`, `last_status = "skipped_worker_busy"`) instead of
    spawning a second concurrent worker thread or overlapping SQLite writes.
- Bounded Shutdown:
  * Never claims `last_status == "stopped"` if the underlying worker thread is still active
    after `wait_timeout` expires; instead reports `last_status = "stopping_worker_hung"`,
    `stopping = True`, and `worker_thread_busy = True`.
  * Supports clean `start()` after `stop()` once the worker thread has finished.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

from homeagentp_core.logging import redact_text


class HardenedPeriodicScheduler(ABC):
    """Reusable asyncio + single-worker-thread scheduler with overlap and shutdown guards."""

    def __init__(
        self,
        *,
        worker_name_prefix: str,
        task_name: str,
        shutdown_timeout_seconds: float = 2.0,
    ) -> None:
        self._worker_name_prefix = worker_name_prefix
        self._task_name = task_name
        self._shutdown_timeout_seconds = max(0.0, float(shutdown_timeout_seconds))
        self._lock = asyncio.Lock()
        self._worker_lock = threading.Lock()
        self._worker_done_event = threading.Event()
        self._worker_done_event.set()
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix=self._worker_name_prefix
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

    @abstractmethod
    def _is_enabled(self) -> bool:
        """Return whether this scheduler is enabled in Settings."""

    @abstractmethod
    def _interval_seconds(self) -> int:
        """Return collection interval in seconds."""

    @abstractmethod
    def _timeout_seconds(self) -> float:
        """Return per-cycle execution timeout in seconds."""

    @abstractmethod
    def _min_persist_interval_seconds(self) -> int:
        """Return minimum SQLite snapshot persistence interval in seconds."""

    @abstractmethod
    def _execute_sync(self, *, force_persist: bool = False) -> dict[str, Any]:
        """Execute one collection + persistence cycle synchronously inside the worker thread."""

    @abstractmethod
    def _extract_status(self, snapshot: dict[str, Any]) -> str:
        """Extract the status string from a collected snapshot."""

    def status_summary(self) -> dict[str, Any]:
        """Return current scheduler state for API status endpoints and Dashboard inspection."""
        worker_busy = self._worker_lock.locked()
        return {
            "enabled": self._is_enabled(),
            "running": self.running,
            "stopping": self.stopping,
            "in_progress": self.in_progress or worker_busy,
            "worker_thread_busy": worker_busy,
            "interval_seconds": self._interval_seconds(),
            "timeout_seconds": self._timeout_seconds(),
            "shutdown_timeout_seconds": self._shutdown_timeout_seconds,
            "min_persist_interval_seconds": self._min_persist_interval_seconds(),
            "last_run_at": self.last_run_at,
            "last_success_at": self.last_success_at,
            "last_status": self.last_status,
            "last_error": self.last_error,
            "last_snapshot_id": self.last_snapshot_id,
            "run_count": self.run_count,
            "skipped_overlap_count": self.skipped_overlap_count,
        }

    def _run_worker_sync(self, *, force_persist: bool = False) -> dict[str, Any]:
        """Run inside the dedicated single worker thread holding `_worker_lock`."""
        try:
            return self._execute_sync(force_persist=force_persist)
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
            timeout_sec = self._timeout_seconds()
            try:
                future = loop.run_in_executor(
                    self._executor,
                    lambda: self._run_worker_sync(force_persist=force_persist),
                )
                result = await asyncio.wait_for(future, timeout=timeout_sec)
                snap = result["snapshot"]
                self.last_snapshot_id = int(result["snapshot_id"])
                self.last_success_at = self.last_run_at
                self.last_status = self._extract_status(snap)
                self.last_error = None
                self.run_count += 1
                return result
            except TimeoutError:
                self.last_status = "timeout"
                self.last_error = (
                    f"Collection timed out after {timeout_sec}s "
                    "(underlying worker remains guarded until it exits)."
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
                    timeout=float(self._interval_seconds()),
                )
            except TimeoutError:
                continue

    async def start(self) -> None:
        """Start the background loop if enabled in Settings."""
        if not self._is_enabled():
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
                max_workers=1, thread_name_prefix=self._worker_name_prefix
            )
        self._stop_event.clear()
        self.stopping = False
        self.running = True
        self.last_status = "starting"
        self._task = asyncio.create_task(self._loop(), name=self._task_name)

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
