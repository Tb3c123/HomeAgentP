"""Tests for Phase 05 P05-F01: Read-only Home Assistant integration, SSRF, and RBAC."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from tests.core.conftest import TEST_ADMIN_PASSWORD, TEST_ADMIN_USERNAME
from tests.core.workspace.conftest import login_client, make_workspace_settings

from homeagentp_core.auth.security import hash_password
from homeagentp_core.config import Settings
from homeagentp_core.db.connection import db_session
from homeagentp_core.main import create_app
from homeagentp_core.modules.home_assistant.client import (
    HaClientError,
    HomeAssistantReadOnlyClient,
)
from homeagentp_core.modules.home_assistant.collector import (
    collect_ha_telemetry,
    persist_ha_snapshot,
)
from homeagentp_core.modules.home_assistant.security import (
    HaSecurityError,
    minimize_ha_state_payload,
    validate_ha_allowlist,
    validate_ha_url,
)


def _make_ha_settings(tmp_path: Path, **overrides: object) -> Settings:
    base = make_workspace_settings(tmp_path, db_name="ha_gate_a.db")
    data = base.model_dump()
    data.update(overrides)
    return Settings(**data)


def test_disabled_ha_makes_zero_network_calls_and_reports_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called(*args: object, **kwargs: object) -> object:
        raise AssertionError("Network must not be called when HA is disabled")

    monkeypatch.setattr(httpx.Client, "stream", fail_if_called)
    settings = _make_ha_settings(tmp_path, ha_enabled=False)
    snapshot = collect_ha_telemetry(settings)
    assert snapshot["status"] == "unavailable"
    assert snapshot["enabled"] is False
    assert snapshot["entities"] == []


def test_ha_allowlist_ssrf_redirect_and_payload_minimization(tmp_path: Path) -> None:
    # Entity allowlist validation & max 25 cap
    assert validate_ha_allowlist(["sensor.nas_ups_load", "SENSOR.NAS_UPS_LOAD"]) == [
        "sensor.nas_ups_load"
    ]
    with pytest.raises(HaSecurityError):
        validate_ha_allowlist(["invalid_entity"])
    with pytest.raises(HaSecurityError):
        validate_ha_allowlist([f"sensor.e{i}" for i in range(26)])

    # SSRF & host allowlist checks
    with pytest.raises(HaSecurityError) as exc_host:
        validate_ha_url("http://192.168.1.99:8123", ["127.0.0.1"])
    assert exc_host.value.code == "host_not_allowlisted"

    with pytest.raises(HaSecurityError) as exc_meta:
        validate_ha_url("http://169.254.169.254", ["169.254.169.254"])
    assert exc_meta.value.code == "ssrf_blocked"

    with pytest.raises(HaSecurityError) as exc_mapped:
        validate_ha_url("http://[::ffff:169.254.169.254]", ["::ffff:169.254.169.254"])
    assert exc_mapped.value.code == "ssrf_blocked"

    # Redirect blocking and oversized payload rejection via MockTransport
    def redirect_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "http://169.254.169.254/latest"})

    client_redir = HomeAssistantReadOnlyClient(
        base_url="http://127.0.0.1:8123",
        token="ha-test-token-value",  # noqa: S106
        allowed_hosts=["127.0.0.1"],
        transport=httpx.MockTransport(redirect_handler),
    )
    with pytest.raises(HaClientError) as exc_redir:
        client_redir.check_health()
    assert exc_redir.value.code == "redirect_blocked"

    def huge_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"{" + b"x" * 10000 + b"}")

    client_huge = HomeAssistantReadOnlyClient(
        base_url="http://127.0.0.1:8123",
        token="ha-test-token-value",  # noqa: S106
        allowed_hosts=["127.0.0.1"],
        max_response_bytes=4096,
        transport=httpx.MockTransport(huge_handler),
    )
    with pytest.raises(HaClientError) as exc_huge:
        client_huge.check_health()
    assert exc_huge.value.code == "payload_too_large"

    # Data minimization drops non-allowlisted / nested attributes
    state, friendly, attrs, last_changed = minimize_ha_state_payload(
        {
            "state": "24.5",
            "last_changed": "2026-11-17T06:00:00Z",
            "attributes": {
                "friendly_name": "UPS Load",
                "unit_of_measurement": "%",
                "secret_raw_dump": "should-never-be-stored",
                "nested": {"a": 1},
            },
        },
        expected_entity_id="sensor.ups_load",
    )
    assert state == "24.5"
    assert friendly == "UPS Load"
    assert attrs == {"friendly_name": "UPS Load", "unit_of_measurement": "%"}
    assert "secret_raw_dump" not in json.dumps(attrs)
    assert last_changed == "2026-11-17T06:00:00Z"


def test_ha_get_only_collection_persistence_staleness_and_rbac(tmp_path: Path) -> None:
    seen_requests: list[tuple[str, str]] = []

    def ok_handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append((request.method, request.url.path))
        if request.url.path == "/api/":
            return httpx.Response(200, json={"message": "API running."})
        if request.url.path == "/api/states/sensor.nas_ups_load":
            return httpx.Response(
                200,
                json={
                    "entity_id": "sensor.nas_ups_load",
                    "state": "18",
                    "attributes": {
                        "friendly_name": "NAS UPS Load",
                        "unit_of_measurement": "%",
                        "extra_unlisted": "drop-me",
                    },
                },
            )
        return httpx.Response(404, json={"message": "Entity not found"})

    settings = _make_ha_settings(
        tmp_path,
        ha_enabled=True,
        home_assistant_url="http://127.0.0.1:8123",
        ha_token="ha-secret-token-xyz",  # noqa: S106
        ha_allowed_hosts=["127.0.0.1"],
        ha_allowed_entities=["sensor.nas_ups_load"],
    )
    snapshot = collect_ha_telemetry(settings, transport=httpx.MockTransport(ok_handler))
    assert snapshot["status"] == "online"
    assert all(method == "GET" for method, _ in seen_requests)
    assert [p for _, p in seen_requests] == ["/api/", "/api/states/sensor.nas_ups_load"]

    app = create_app(settings)
    with TestClient(app) as client:
        with db_session(settings.db_path) as conn:
            persist_ha_snapshot(conn, snapshot, force=True)
            conn.execute(
                """
                INSERT INTO users (username, password_hash, role, is_active, created_at)
                VALUES (?, ?, 'viewer', 1, '2026-11-17T00:00:00Z')
                """,
                ("ha_viewer", hash_password("ViewerPass#12345")),
            )

        # Viewer can read overview, cannot trigger collect even with CSRF
        viewer_csrf = login_client(client, "ha_viewer", "ViewerPass#12345")
        ov_resp = client.get("/api/v1/home-assistant/overview")
        assert ov_resp.status_code == 200
        assert ov_resp.json()["status"] == "online"
        assert ov_resp.json()["entities"][0]["friendly_name"] == "NAS UPS Load"

        assert (
            client.post(
                "/api/v1/home-assistant/collect",
                headers={"X-CSRF-Token": viewer_csrf},
            ).status_code
            == 403
        )

        # Staleness detection when snapshot is older than ha_snapshot_stale_seconds
        old_ts = (datetime.now(UTC) - timedelta(seconds=600)).isoformat()
        with db_session(settings.db_path) as conn:
            conn.execute("UPDATE ha_entity_snapshots SET collected_at = ?", (old_ts,))

        stale_resp = client.get("/api/v1/home-assistant/overview")
        assert stale_resp.status_code == 200
        assert stale_resp.json()["status"] == "stale"

        # Owner login + missing CSRF rejected
        owner_csrf = login_client(client, TEST_ADMIN_USERNAME, TEST_ADMIN_PASSWORD)
        assert client.post("/api/v1/home-assistant/collect").status_code == 403
        assert owner_csrf
