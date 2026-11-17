"""End-to-end API integration tests for /api/v1/nas/*."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from tests.core.conftest import TEST_ADMIN_PASSWORD, TEST_ADMIN_USERNAME
from tests.core.nas.conftest import make_nas_settings, write_sample_proc_tree

from homeagentp_core.main import create_app
from homeagentp_core.modules.nas.collector import CONTAINER_SNAPSHOT_SCHEMA_VERSION


def test_nas_guardian_api_collection_alerts_and_retention(tmp_path: Path) -> None:
    """End-to-end test of /api/v1/nas/* with verified direct host directory, fresh container
    snapshot, include_resolved parameter, and snapshot retention pruning."""
    proc_dir = tmp_path / "host_proc"
    root_dir = tmp_path / "host_root"
    root_dir.mkdir()
    write_sample_proc_tree(
        proc_dir,
        stat_text="cpu  9000 0 500 500 0 0 0 0 0 0\ncpu0 9000 0 500 500 0 0 0 0 0 0\n",
        loadavg_text="1.85 1.20 0.95 2/200 1001\n",
        cpu_psi_text="some avg10=2.50 avg60=1.10 avg300=0.50 total=10000\n",
        meminfo_text=(
            "MemTotal:       16000000 kB\n"
            "MemAvailable:    1600000 kB\n"
            "SwapTotal:       2000000 kB\n"
            "SwapFree:        2000000 kB\n"
        ),
        mem_psi_text=(
            "some avg10=0.50 avg60=0.20 avg300=0.10 total=2000\n"
            "full avg10=0.00 avg60=0.00 avg300=0.00 total=0\n"
        ),
        mounts_text="/dev/nvme0n1p2 / ext4 rw 0 0\n",
    )

    settings = make_nas_settings(
        tmp_path,
        db_name="nas_test.db",
        nas_adapter_enabled=True,
        nas_telemetry_mode="direct_host_fs",
        nas_proc_root=proc_dir,
        nas_root_mount_path=root_dir,
        nas_required_mounts=["/mnt/disk1", "/mnt/disk2"],
        nas_expected_services=["jellyfin", "qbittorrent"],
        nas_container_snapshot_rel_path="containers_snapshot.json",
        nas_history_retention_limit=5,
    )

    container_snapshot = {
        "schema_version": CONTAINER_SNAPSHOT_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "ttl_seconds": 300,
        "containers": [
            {
                "name": "jellyfin",
                "state": "running",
                "memory_used_bytes": 900_000_000,
                "memory_limit_bytes": 1_000_000_000,
                "cpu_percent": 12.5,
                "restart_count": 0,
            },
            {
                "name": "qbittorrent",
                "state": "exited",
                "memory_used_bytes": 0,
                "memory_limit_bytes": 1_000_000_000,
                "cpu_percent": 0.0,
                "restart_count": 3,
            },
        ],
    }
    (settings.reports_dir / "containers_snapshot.json").write_text(
        json.dumps(container_snapshot),
        encoding="utf-8",
    )

    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/api/v1/nas/status").status_code == 401
        assert client.get("/api/v1/nas/history").status_code == 401
        assert client.get("/api/v1/nas/alerts").status_code == 401

        login_resp = client.post(
            "/api/v1/auth/login",
            json={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
        )
        assert login_resp.status_code == 200
        csrf = login_resp.json()["csrf_token"]

        status_resp = client.get("/api/v1/nas/status")
        assert status_resp.status_code == 200
        st_data = status_resp.json()
        assert st_data["adapter_enabled"] is True
        assert st_data["telemetry_boundary"]["host_verified"] is True
        assert st_data["memory"]["usage_percent"] == 90.0
        assert st_data["containers"]["status"] == "degraded"
        assert st_data["containers"]["fresh"] is True

        # Collect 7 snapshots; retention limit is 5, so only 5 must remain in history
        for _ in range(7):
            collect_resp = client.post(
                "/api/v1/nas/collect",
                headers={"X-CSRF-Token": csrf},
            )
            assert collect_resp.status_code == 200

        history_resp = client.get("/api/v1/nas/history")
        assert history_resp.status_code == 200
        history_items = history_resp.json()
        assert len(history_items) == 5

        alerts_resp = client.get("/api/v1/nas/alerts?include_resolved=false")
        assert alerts_resp.status_code == 200
        active_alerts = alerts_resp.json()
        alert_codes = {a["code"] for a in active_alerts}
        assert "ram.usage_warning" in alert_codes
        assert "container.not_running" in alert_codes
        assert "container.memory_warning" in alert_codes
        # All deduplicated alerts must have occurrences == 7 and status == 'active'
        for a in active_alerts:
            assert a["status"] == "active"
            assert a["occurrences"] == 7
