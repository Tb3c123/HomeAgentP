"""Modular read-only media service connectors."""

from homeagentp_core.modules.media.connectors.bazarr import BazarrAdapter
from homeagentp_core.modules.media.connectors.jellyfin import JellyfinAdapter
from homeagentp_core.modules.media.connectors.prowlarr import ProwlarrAdapter
from homeagentp_core.modules.media.connectors.qbittorrent import (
    QBITTORRENT_CREDENTIAL_NOTICE,
    QBittorrentAdapter,
)
from homeagentp_core.modules.media.connectors.radarr import RadarrAdapter
from homeagentp_core.modules.media.connectors.registry import build_media_adapters
from homeagentp_core.modules.media.connectors.seerr import SeerrAdapter
from homeagentp_core.modules.media.connectors.sonarr import SonarrAdapter

__all__ = [
    "QBITTORRENT_CREDENTIAL_NOTICE",
    "BazarrAdapter",
    "JellyfinAdapter",
    "ProwlarrAdapter",
    "QBittorrentAdapter",
    "RadarrAdapter",
    "SeerrAdapter",
    "SonarrAdapter",
    "build_media_adapters",
]
