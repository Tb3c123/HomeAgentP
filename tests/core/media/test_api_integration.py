"""Unified /api/v1/media/* and /api/v1/overview integration tests."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from tests.core.conftest import TEST_ADMIN_PASSWORD, TEST_ADMIN_USERNAME
from tests.core.media.conftest import build_valid_transports, make_media_settings

from homeagentp_core.main import create_app


def test_unified_media_api_endpoints_integration(tmp_path: Path) -> None:
    """Verify all /api/v1/media/* endpoints with authentication, CSRF, and mocked transports."""
    settings = make_media_settings(tmp_path)
    app = create_app(settings)
    app.state.media_transports = build_valid_transports()

    with TestClient(app) as client:
        assert client.get("/api/v1/media/overview").status_code == 401
        assert client.get("/api/v1/media/jellyfin").status_code == 401

        login_resp = client.post(
            "/api/v1/auth/login",
            json={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
        )
        assert login_resp.status_code == 200
        csrf_token = login_resp.json()["csrf_token"]

        ov_resp = client.get("/api/v1/media/overview")
        assert ov_resp.status_code == 200
        ov_data = ov_resp.json()
        assert ov_data["adapter_enabled"] is True
        assert ov_data["summary"]["jellyfin_active_streams"] == 2
        assert ov_data["summary"]["qb_downloading_count"] == 1

        svcs_resp = client.get("/api/v1/media/services")
        assert svcs_resp.status_code == 200
        assert len(svcs_resp.json()["services_list"]) == 7

        for ep in (
            "/api/v1/media/jellyfin",
            "/api/v1/media/qbittorrent",
            "/api/v1/media/sonarr",
            "/api/v1/media/radarr",
            "/api/v1/media/bazarr",
            "/api/v1/media/prowlarr",
            "/api/v1/media/seerr",
        ):
            r = client.get(ep)
            assert r.status_code == 200, f"Failed GET {ep}"
            assert r.json()["read_only_enforced"] is True

        assert client.post("/api/v1/media/collect").status_code == 403
        collect_resp = client.post(
            "/api/v1/media/collect", headers={"X-CSRF-Token": csrf_token}
        )
        assert collect_resp.status_code == 200
        assert collect_resp.json()["snapshot_id"] >= 1

        hist_resp = client.get("/api/v1/media/history")
        assert hist_resp.status_code == 200
        assert len(hist_resp.json()) == 1

        alerts_resp = client.get("/api/v1/media/alerts?include_resolved=true")
        assert alerts_resp.status_code == 200
        assert len(alerts_resp.json()) >= 1

        top_overview = client.get("/api/v1/overview")
        assert top_overview.status_code == 200
        assert top_overview.json()["domains"]["media"]["status"] == "degraded"
        assert top_overview.json()["domains"]["downloads"]["status"] == "critical"
