"""Shared fixtures and transport registry for Phase 03 Media & Downloads tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
from tests.core.conftest import TEST_ADMIN_PASSWORD, TEST_ADMIN_USERNAME, TEST_SECRET_KEY
from tests.core.media.mocks.arr_and_aux import (
    build_bazarr_transport,
    build_prowlarr_transport,
    build_radarr_transport,
    build_seerr_transport,
    build_sonarr_transport,
)
from tests.core.media.mocks.jellyfin_qb import (
    build_jellyfin_transport,
    build_qbittorrent_transport,
)

from homeagentp_core.config import Settings


def make_media_settings(tmp_path: Path, **overrides: Any) -> Settings:
    scripts_dir = tmp_path / "scripts"
    reports_dir = tmp_path / "reports"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    defaults: dict[str, Any] = {
        "env": "testing",
        "db_path": tmp_path / "media_test.db",
        "secret_key": TEST_SECRET_KEY,
        "admin_username": TEST_ADMIN_USERNAME,
        "admin_password": TEST_ADMIN_PASSWORD,
        "scripts_dir": scripts_dir,
        "reports_dir": reports_dir,
        "seed_examples": False,
        "media_adapter_enabled": True,
        "media_failure_threshold": 3,
        "media_snapshot_stale_seconds": 300,
        "jellyfin_url": "http://jellyfin:8096",
        "jellyfin_api_key": "jf_test_token_secret_123",
        "qbittorrent_url": "http://qbittorrent:8080",
        "qbittorrent_username": "admin",
        "qbittorrent_password": "qb_test_password_secret",
        "qbittorrent_stalled_threshold_seconds": 1800,
        "sonarr_url": "http://sonarr:8989",
        "sonarr_api_key": "sonarr_test_key_123",
        "radarr_url": "http://radarr:7878",
        "radarr_api_key": "radarr_test_key_123",
        "bazarr_url": "http://bazarr:6767",
        "bazarr_api_key": "bazarr_test_key_123",
        "prowlarr_url": "http://prowlarr:9696",
        "prowlarr_api_key": "prowlarr_test_key_123",
        "seerr_url": "http://seerr:5055",
        "seerr_api_key": "seerr_test_key_123",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def build_valid_transports() -> dict[str, httpx.BaseTransport]:
    """Build deterministic mocked HTTP transports for all 7 Media & Downloads services."""
    return {
        "jellyfin": build_jellyfin_transport(),
        "qbittorrent": build_qbittorrent_transport(),
        "sonarr": build_sonarr_transport(),
        "radarr": build_radarr_transport(),
        "bazarr": build_bazarr_transport(),
        "prowlarr": build_prowlarr_transport(),
        "seerr": build_seerr_transport(),
    }
