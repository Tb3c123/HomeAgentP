"""MediaCollectionScheduler concurrency, timeout, hung worker shutdown, and retention tests."""

from __future__ import annotations

import asyncio
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from tests.core.media.conftest import build_valid_transports, make_media_settings

from homeagentp_core.config import Settings
from homeagentp_core.db.connection import db_session
from homeagentp_core.db.migrator import apply_migrations
from homeagentp_core.modules.media.collector import (
    collect_media_telemetry,
    persist_media_snapshot,
    query_media_history,
)
from homeagentp_core.modules.media.scheduler import MediaCollectionScheduler


def test_scheduler_non_overlapping_concurrency_and_sqlite_retention(tmp_path: Path) -> None:
    """Verify MediaCollectionScheduler prevents overlapping runs and prunes SQLite history."""
    settings = make_media_settings(
        tmp_path,
        media_scheduler_enabled=True,
        media_collection_interval_seconds=60,
        media_collection_timeout_seconds=2.0,
        media_min_persist_interval_seconds=0,
        media_history_retention_limit=5,
    )
    transports = build_valid_transports()

    with db_session(settings.db_path) as conn:
        apply_migrations(conn)
        for i in range(8):
            snap = collect_media_telemetry(
                settings,
                conn=conn,
                transports=transports,
                now=datetime(2026, 11, 17, 6, i, 0, tzinfo=UTC),
            )
            persist_media_snapshot(
                conn,
                snap,
                retention_limit=settings.media_history_retention_limit,
                min_persist_interval_seconds=0,
                db_key=f"test-{i}",
            )
        history = query_media_history(conn, limit=50)
        assert len(history) == 5

    def slow_collector(cfg: Settings) -> dict[str, Any]:
        time.sleep(0.15)
        return {
            "collected_at": datetime.now(UTC).isoformat(),
            "status": "online",
            "overall_status": "online",
            "summary": {},
            "services": {},
            "alerts": [],
        }

    scheduler = MediaCollectionScheduler(settings, collector_fn=slow_collector)

    async def run_concurrent() -> None:
        r1, r2 = await asyncio.gather(
            scheduler.run_once(force_persist=True),
            scheduler.run_once(force_persist=True),
        )
        assert (r1 is None) ^ (r2 is None)
        assert scheduler.run_count == 1
        assert scheduler.skipped_overlap_count == 1

    asyncio.run(run_concurrent())


def test_r05_media_scheduler_hardened_worker_timeout_shutdown_and_restart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R05: Verify MediaCollectionScheduler worker guard, bounded shutdown, hung state, restart."""
    settings = make_media_settings(
        tmp_path,
        media_scheduler_enabled=True,
        media_collection_timeout_seconds=1.0,
        media_collection_interval_seconds=60,
        media_min_persist_interval_seconds=0,
    )
    with db_session(settings.db_path) as conn:
        apply_migrations(conn)

    worker_entered = threading.Event()
    release_worker = threading.Event()
    active_workers = 0
    max_concurrent_workers = 0
    worker_count_lock = threading.Lock()

    def _blocking_collector(cfg: Settings) -> dict[str, Any]:
        nonlocal active_workers, max_concurrent_workers
        with worker_count_lock:
            active_workers += 1
            max_concurrent_workers = max(max_concurrent_workers, active_workers)
        try:
            worker_entered.set()
            release_worker.wait(timeout=2.0)
            return {
                "overall_status": "online",
                "status": "online",
                "collected_at": datetime.now(UTC).isoformat(),
                "summary": {},
                "services": {},
                "alerts": [],
            }
        finally:
            with worker_count_lock:
                active_workers -= 1

    async def _exercise() -> None:
        sched = MediaCollectionScheduler(
            settings,
            collector_fn=_blocking_collector,
            shutdown_timeout_seconds=0.05,
        )
        monkeypatch.setattr(sched, "_timeout_seconds", lambda: 0.08)

        res1 = await sched.run_once(force_persist=True)
        assert res1 is None
        assert worker_entered.is_set()
        assert sched.last_status == "timeout"
        assert sched.status_summary()["worker_thread_busy"] is True

        res2 = await sched.run_once(force_persist=True)
        assert res2 is None
        assert sched.last_status == "skipped_worker_busy"
        assert sched.skipped_overlap_count == 1
        assert max_concurrent_workers == 1

        hung_summary = await sched.stop(wait_timeout=0.05)
        assert hung_summary["last_status"] == "stopping_worker_hung"
        assert hung_summary["stopping"] is True
        assert hung_summary["worker_thread_busy"] is True

        await sched.start()
        assert sched.running is False
        assert sched.last_status == "stopping_worker_hung"

        release_worker.set()
        sched._worker_done_event.wait(timeout=2.0)
        await asyncio.sleep(0.02)

        assert sched.status_summary()["worker_thread_busy"] is False
        assert sched.last_status == "stopped"

        await sched.start()
        assert sched.running is True
        await asyncio.sleep(0.05)
        stopped_summary = await sched.stop(wait_timeout=1.0)
        assert stopped_summary["last_status"] == "stopped"
        assert stopped_summary["stopping"] is False
        assert stopped_summary["worker_thread_busy"] is False
        assert sched.run_count >= 1
        assert max_concurrent_workers == 1

    asyncio.run(_exercise())
