"""Bazarr, Prowlarr, Seerr connector unit tests and disabled-connector checks."""

from __future__ import annotations

from pathlib import Path

from tests.core.media.conftest import build_valid_transports, make_media_settings

from homeagentp_core.db.connection import db_session
from homeagentp_core.db.migrator import apply_migrations
from homeagentp_core.modules.media import adapters as legacy_adapters
from homeagentp_core.modules.media.collector import collect_media_telemetry
from homeagentp_core.modules.media.connectors import (
    BazarrAdapter as PkgBazarr,
)
from homeagentp_core.modules.media.connectors import (
    ProwlarrAdapter as PkgProwlarr,
)
from homeagentp_core.modules.media.connectors import (
    SeerrAdapter as PkgSeerr,
)
from homeagentp_core.modules.media.connectors.bazarr import BazarrAdapter as DirectBazarr
from homeagentp_core.modules.media.connectors.prowlarr import ProwlarrAdapter as DirectProwlarr
from homeagentp_core.modules.media.connectors.seerr import SeerrAdapter as DirectSeerr


def test_bazarr_prowlarr_seerr_valid_metrics_and_imports(tmp_path: Path) -> None:
    assert legacy_adapters.BazarrAdapter is DirectBazarr
    assert legacy_adapters.ProwlarrAdapter is DirectProwlarr
    assert legacy_adapters.SeerrAdapter is DirectSeerr
    assert PkgBazarr is DirectBazarr
    assert PkgProwlarr is DirectProwlarr
    assert PkgSeerr is DirectSeerr

    settings = make_media_settings(tmp_path)
    transports = build_valid_transports()

    bz = DirectBazarr(settings, transport=transports["bazarr"]).collect()
    assert bz["status"] == "degraded"
    assert bz["version"] == "1.4.3"
    assert bz["metrics"]["missing_episode_subtitles"] == 7
    assert bz["metrics"]["missing_movie_subtitles"] == 2
    assert bz["metrics"]["unhealthy_providers_count"] == 1

    pr = DirectProwlarr(settings, transport=transports["prowlarr"]).collect()
    assert pr["status"] == "degraded"
    assert pr["version"] == "1.24.2.4779"
    assert pr["metrics"]["total_indexers"] == 3
    assert pr["metrics"]["enabled_indexers"] == 2
    assert pr["metrics"]["failing_indexers_count"] == 1

    sr = DirectSeerr(settings, transport=transports["seerr"]).collect()
    assert sr["status"] == "online"
    assert sr["version"] == "1.9.2"
    assert sr["metrics"]["requests"]["total"] == 14
    assert sr["metrics"]["requests"]["pending"] == 2
    assert sr["metrics"]["requests"]["approved"] == 4
    assert len(sr["metrics"]["recent_requests"]) == 2


def test_disabled_connectors_report_honest_unavailable(tmp_path: Path) -> None:
    """When HOMEAGENTP_MEDIA_ADAPTER_ENABLED=false, all connectors report unavailable."""
    settings = make_media_settings(tmp_path, media_adapter_enabled=False)
    with db_session(settings.db_path) as conn:
        apply_migrations(conn)
        snap = collect_media_telemetry(settings, conn=conn)

    assert snap["overall_status"] == "unavailable"
    assert snap["adapter_enabled"] is False
    for svc_name, svc_data in snap["services"].items():
        assert svc_data["status"] == "unavailable", f"{svc_name} should be unavailable"
        assert svc_data["enabled"] is False
        assert svc_data["write_operations_performed"] == 0
    assert snap["alerts"] == []
