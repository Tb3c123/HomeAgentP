"""Background scheduler concurrency, timeout, and write-throttling tests."""

from __future__ import annotations

import asyncio
import time as _time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tests.core.nas.conftest import make_nas_settings

from homeagentp_core.config import Settings
from homeagentp_core.db.connection import db_session
from homeagentp_core.main import initialize_core_state
from homeagentp_core.modules.nas.scheduler import NasCollectionScheduler


def test_p02_f02_scheduler_non_overlapping_timeout_and_write_throttling(tmp_path: Path) -> None:
    """Verify P02-F02: background scheduler prevents overlapping runs, handles timeouts,
    throttles excessive SQLite writes, and shuts down cleanly."""
    settings = make_nas_settings(
        tmp_path,
        db_name="f02_sched.db",
        nas_adapter_enabled=True,
        nas_scheduler_enabled=True,
        nas_collection_interval_seconds=10,
        nas_collection_timeout_seconds=1.0,
        nas_min_persist_interval_seconds=60,
    )
    db_file = settings.db_path
    initialize_core_state(settings)

    def fast_collector(_cfg: Settings) -> dict[str, Any]:
        return {
            "collected_at": datetime.now(UTC).isoformat(),
            "adapter_status": "online",
            "cpu": {"usage_percent": 12.0, "pressure": {}},
            "memory": {"usage_percent": 35.0, "pressure": {}},
            "mounts": {},
            "mounts_list": [],
            "containers": {},
            "alerts": [],
        }

    async def _run_scheduler_checks() -> None:
        sched = NasCollectionScheduler(settings, collector_fn=fast_collector)
        res1 = await sched.run_once()
        assert res1 is not None
        first_snap_id = res1["snapshot_id"]
        assert first_snap_id > 0

        # Second immediate run within min_persist_interval_seconds (60s) with unchanged status
        # must be throttled and reuse the existing snapshot row ID without inserting a new row
        res2 = await sched.run_once()
        assert res2 is not None
        assert res2["snapshot_id"] == first_snap_id

        with db_session(db_file) as conn:
            cnt = int(conn.execute("SELECT COUNT(*) FROM nas_metric_snapshots").fetchone()[0])
            assert cnt == 1

        # Test overlap protection & timeout handling
        def slow_collector(_cfg: Settings) -> dict[str, Any]:
            _time.sleep(0.35)
            return fast_collector(_cfg)

        overlap_sched = NasCollectionScheduler(settings, collector_fn=slow_collector)
        t_a = asyncio.create_task(overlap_sched.run_once())
        await asyncio.sleep(0.05)
        t_b = asyncio.create_task(overlap_sched.run_once())
        out_a, out_b = await asyncio.gather(t_a, t_b)
        assert (out_a is None) or (out_b is None)
        assert overlap_sched.skipped_overlap_count == 1

        # Timeout test + verify underlying worker thread does NOT overlap on next run_once()
        timeout_settings = settings.model_copy(update={"nas_collection_timeout_seconds": 1.0})
        active_worker_threads = 0
        max_concurrent_workers = 0
        call_number = 0

        def hanging_then_recovering_collector(_cfg: Settings) -> dict[str, Any]:
            nonlocal active_worker_threads, max_concurrent_workers, call_number
            call_number += 1
            active_worker_threads += 1
            max_concurrent_workers = max(max_concurrent_workers, active_worker_threads)
            try:
                if call_number == 1:
                    _time.sleep(1.35)
                else:
                    _time.sleep(0.05)
                return fast_collector(_cfg)
            finally:
                active_worker_threads -= 1

        timeout_sched = NasCollectionScheduler(
            timeout_settings, collector_fn=hanging_then_recovering_collector
        )
        out_timeout = await timeout_sched.run_once()
        assert out_timeout is None
        assert timeout_sched.last_status == "timeout"
        assert timeout_sched.last_error is not None and "timed out" in timeout_sched.last_error
        # Immediately invoke run_once() while the timed-out worker thread is STILL running:
        # Must be rejected with skipped_worker_busy and never spawn a second concurrent worker!
        assert timeout_sched.worker_thread_busy is True
        out_while_busy = await timeout_sched.run_once()
        assert out_while_busy is None
        assert timeout_sched.last_status == "skipped_worker_busy"
        assert timeout_sched.skipped_overlap_count == 1
        assert max_concurrent_workers == 1

        # Wait for the first worker thread to finish, then confirm the next run succeeds
        await asyncio.sleep(0.5)
        assert timeout_sched.worker_thread_busy is False
        out_after_recovery = await timeout_sched.run_once()
        assert out_after_recovery is not None
        assert timeout_sched.last_status == "online"
        assert max_concurrent_workers == 1
        clean_stop = await timeout_sched.stop(wait_timeout=0.5)
        assert clean_stop["running"] is False
        assert clean_stop["stopping"] is False
        assert clean_stop["worker_thread_busy"] is False
        assert clean_stop["last_status"] == "stopped"

        # Bounded shutdown test when worker thread is STILL hung on OS I/O:
        # Must NOT claim "stopped" while the worker thread is still running!
        def hung_on_shutdown_collector(_cfg: Settings) -> dict[str, Any]:
            _time.sleep(1.35)
            return fast_collector(_cfg)

        hung_sched = NasCollectionScheduler(
            timeout_settings,
            collector_fn=hung_on_shutdown_collector,
            shutdown_timeout_seconds=0.1,
        )
        out_hung = await hung_sched.run_once()
        assert out_hung is None
        assert hung_sched.last_status == "timeout"
        assert hung_sched.worker_thread_busy is True

        # Trigger bounded stop (0.05s wait) while worker thread is still blocked (~0.35s left)
        stop_state = await hung_sched.stop(wait_timeout=0.05)
        assert stop_state["running"] is False
        assert stop_state["stopping"] is True
        assert stop_state["worker_thread_busy"] is True
        assert stop_state["in_progress"] is True
        assert stop_state["last_status"] == "stopping_worker_hung"
        assert "still active" in str(stop_state["last_error"])

        # Attempting a new collection while stopping must be rejected immediately
        rejected = await hung_sched.run_once()
        assert rejected is None
        assert hung_sched.last_status == "stopping_worker_hung"

        # Once the hung worker finally finishes in the background, state transitions to "stopped"
        await asyncio.sleep(0.45)
        final_state = hung_sched.status_summary()
        assert final_state["worker_thread_busy"] is False
        assert final_state["stopping"] is False
        assert final_state["last_status"] == "stopped"

        # Start and graceful stop test
        await sched.start()
        assert sched.running is True
        await asyncio.sleep(0.05)
        await sched.stop()
        assert sched.running is False
        assert sched.last_status == "stopped"

    asyncio.run(_run_scheduler_checks())
