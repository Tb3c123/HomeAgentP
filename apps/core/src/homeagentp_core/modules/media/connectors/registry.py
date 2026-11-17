"""Registry for instantiating all modular Media & Downloads service adapters."""

from __future__ import annotations

import httpx

from homeagentp_core.config import Settings
from homeagentp_core.modules.media.base import MediaServiceAdapter
from homeagentp_core.modules.media.connectors.bazarr import BazarrAdapter
from homeagentp_core.modules.media.connectors.jellyfin import JellyfinAdapter
from homeagentp_core.modules.media.connectors.prowlarr import ProwlarrAdapter
from homeagentp_core.modules.media.connectors.qbittorrent import QBittorrentAdapter
from homeagentp_core.modules.media.connectors.radarr import RadarrAdapter
from homeagentp_core.modules.media.connectors.seerr import SeerrAdapter
from homeagentp_core.modules.media.connectors.sonarr import SonarrAdapter


def build_media_adapters(
    settings: Settings,
    *,
    transports: dict[str, httpx.BaseTransport] | None = None,
) -> dict[str, MediaServiceAdapter]:
    """Instantiate all 7 Media & Downloads service adapters in canonical order."""
    t_map = transports or {}
    return {
        "jellyfin": JellyfinAdapter(settings, transport=t_map.get("jellyfin")),
        "qbittorrent": QBittorrentAdapter(settings, transport=t_map.get("qbittorrent")),
        "sonarr": SonarrAdapter(settings, transport=t_map.get("sonarr")),
        "radarr": RadarrAdapter(settings, transport=t_map.get("radarr")),
        "bazarr": BazarrAdapter(settings, transport=t_map.get("bazarr")),
        "prowlarr": ProwlarrAdapter(settings, transport=t_map.get("prowlarr")),
        "seerr": SeerrAdapter(settings, transport=t_map.get("seerr")),
    }
