"""Sonarr and Radarr (*arr v3) connector unit tests."""

from __future__ import annotations

from pathlib import Path

import httpx
from tests.core.media.conftest import build_valid_transports, make_media_settings

from homeagentp_core.modules.media import adapters as legacy_adapters
from homeagentp_core.modules.media.connectors import (
    RadarrAdapter as PkgRadarr,
)
from homeagentp_core.modules.media.connectors import (
    SonarrAdapter as PkgSonarr,
)
from homeagentp_core.modules.media.connectors.radarr import RadarrAdapter as DirectRadarr
from homeagentp_core.modules.media.connectors.sonarr import SonarrAdapter as DirectSonarr


def test_sonarr_and_radarr_valid_metrics_and_imports(tmp_path: Path) -> None:
    assert legacy_adapters.SonarrAdapter is DirectSonarr
    assert legacy_adapters.RadarrAdapter is DirectRadarr
    assert PkgSonarr is DirectSonarr
    assert PkgRadarr is DirectRadarr

    settings = make_media_settings(tmp_path)
    transports = build_valid_transports()

    sn = DirectSonarr(settings, transport=transports["sonarr"]).collect()
    assert sn["status"] == "degraded"
    assert sn["version"] == "4.0.9.2244"
    assert sn["metrics"]["total_count"] == 2
    assert sn["metrics"]["available_file_count"] == 21
    assert sn["metrics"]["missing_count"] == 4
    assert sn["metrics"]["queue_failed_count"] == 1

    rd = DirectRadarr(settings, transport=transports["radarr"]).collect()
    assert rd["status"] == "online"
    assert rd["version"] == "5.10.3.9171"
    assert rd["metrics"]["total_count"] == 2
    assert rd["metrics"]["available_file_count"] == 1
    assert rd["metrics"]["missing_count"] == 1


def test_arr_api_version_incompatibility_rejected(tmp_path: Path) -> None:
    """Verify incompatible server/API major versions raise unsupported_version."""
    settings = make_media_settings(tmp_path)
    old_sonarr = httpx.MockTransport(
        lambda req: httpx.Response(200, json={"version": "2.0.0.5344"})
    )
    snap = DirectSonarr(settings, transport=old_sonarr).collect()
    assert snap["status"] == "error"
    assert snap["error_code"] == "unsupported_version"
