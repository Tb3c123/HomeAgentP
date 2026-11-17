"""qBittorrent connector unit tests, auth/redaction, and backward-compatible imports."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
from tests.core.media.conftest import build_valid_transports, make_media_settings

from homeagentp_core.logging import redact_structure, redact_text
from homeagentp_core.modules.media import adapters as legacy_adapters
from homeagentp_core.modules.media.connectors import QBittorrentAdapter as PkgQBittorrent
from homeagentp_core.modules.media.connectors.qbittorrent import (
    QBittorrentAdapter as DirectQBittorrent,
)


def test_qbittorrent_valid_metrics_and_backward_compatible_imports(tmp_path: Path) -> None:
    assert legacy_adapters.QBittorrentAdapter is DirectQBittorrent
    assert PkgQBittorrent is DirectQBittorrent

    settings = make_media_settings(tmp_path)
    transport = build_valid_transports()["qbittorrent"]
    qb = DirectQBittorrent(settings, transport=transport).collect()
    assert qb["status"] == "critical"
    assert qb["version"] == "v4.6.7"
    assert qb["metrics"]["download_speed_bytes"] == 15_728_640
    assert qb["metrics"]["upload_speed_bytes"] == 2_097_152
    assert qb["metrics"]["counts"]["downloading"] == 1
    assert qb["metrics"]["counts"]["seeding"] == 1
    assert qb["metrics"]["counts"]["stalled"] == 1
    assert qb["metrics"]["counts"]["stalled_over_threshold"] == 1
    assert qb["metrics"]["counts"]["errored"] == 1
    assert "client-side GET endpoint allowlist" in qb["metrics"]["credential_scope_notice"]


def test_qbittorrent_auth_failure_and_secret_redaction(tmp_path: Path) -> None:
    settings = make_media_settings(tmp_path)
    qb_fail = httpx.MockTransport(lambda req: httpx.Response(200, text="Fails."))

    qb_snap = DirectQBittorrent(settings, transport=qb_fail).collect()
    assert qb_snap["status"] == "auth_error"
    assert qb_snap["error_code"] == "auth_failed"
    assert "qb_test_password_secret" not in json.dumps(qb_snap)

    redacted_cfg = settings.redacted_summary()
    assert redacted_cfg["jellyfin_api_key"] == "[REDACTED]"  # noqa: S105
    assert redacted_cfg["qbittorrent_password"] == "[REDACTED]"  # noqa: S105
    assert redacted_cfg["sonarr_api_key"] == "[REDACTED]"  # noqa: S105
    assert "[REDACTED]" in redact_text("X-Emby-Token: secret_emby_123 and SID=secret_sid_456")
    assert redact_structure({"X-Api-Key": "secret"})["X-Api-Key"] == "[REDACTED]"
