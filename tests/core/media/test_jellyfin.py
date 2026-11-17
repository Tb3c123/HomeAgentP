"""Jellyfin connector unit tests and backward-compatible import checks."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
from tests.core.media.conftest import build_valid_transports, make_media_settings

from homeagentp_core.modules.media import adapters as legacy_adapters
from homeagentp_core.modules.media.connectors import JellyfinAdapter as PkgJellyfin
from homeagentp_core.modules.media.connectors.jellyfin import (
    JellyfinAdapter as DirectJellyfin,
)


def test_jellyfin_connector_backward_compatible_import_and_metrics(tmp_path: Path) -> None:
    """R02.1: Verify JellyfinAdapter extraction preserves imports and exact metrics JSON."""
    assert legacy_adapters.JellyfinAdapter is DirectJellyfin
    assert PkgJellyfin is DirectJellyfin

    settings = make_media_settings(tmp_path)
    transport = build_valid_transports()["jellyfin"]
    snap = DirectJellyfin(settings, transport=transport).collect()
    assert snap["service"] == "jellyfin"
    assert snap["status"] == "degraded"
    assert snap["version"] == "10.9.11"
    assert snap["metrics"]["libraries"] == {
        "movies": 420,
        "series": 85,
        "episodes": 3120,
        "songs": 150,
        "albums": 18,
    }
    assert snap["metrics"]["sessions"]["active_count"] == 2
    assert snap["metrics"]["sessions"]["direct_play_count"] == 1
    assert snap["metrics"]["sessions"]["transcoding_count"] == 1
    assert snap["metrics"]["playback_errors"]["accessible"] is True
    assert snap["metrics"]["playback_errors"]["count"] == 1


def test_jellyfin_auth_failure_and_secret_redaction(tmp_path: Path) -> None:
    settings = make_media_settings(tmp_path)
    jf_401 = httpx.MockTransport(lambda req: httpx.Response(401, json={"error": "Unauthorized"}))
    jf_snap = DirectJellyfin(settings, transport=jf_401).collect()
    assert jf_snap["status"] == "auth_error"
    assert jf_snap["error_code"] == "auth_failed"
    assert "jf_test_token_secret_123" not in json.dumps(jf_snap)


def test_jellyfin_timeout_connection_error_malformed_json_and_oversized_payload(
    tmp_path: Path,
) -> None:
    """Verify timeout, connection failure, malformed JSON, missing fields, and size cap."""
    settings = make_media_settings(tmp_path, media_max_response_bytes=4096)

    def timeout_handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Simulated read timeout", request=req)

    def conn_err_handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=req)

    def malformed_json_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"{not-valid-json")

    def missing_fields_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ServerName": "MissingVersionField"})

    def oversized_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 8192)

    assert (
        DirectJellyfin(settings, transport=httpx.MockTransport(timeout_handler)).collect()[
            "error_code"
        ]
        == "timeout"
    )
    assert (
        DirectJellyfin(settings, transport=httpx.MockTransport(conn_err_handler)).collect()[
            "error_code"
        ]
        == "connection_failed"
    )
    assert (
        DirectJellyfin(settings, transport=httpx.MockTransport(malformed_json_handler)).collect()[
            "error_code"
        ]
        == "malformed_response"
    )
    assert (
        DirectJellyfin(settings, transport=httpx.MockTransport(missing_fields_handler)).collect()[
            "error_code"
        ]
        == "malformed_response"
    )
    assert (
        DirectJellyfin(settings, transport=httpx.MockTransport(oversized_handler)).collect()[
            "error_code"
        ]
        == "response_too_large"
    )
