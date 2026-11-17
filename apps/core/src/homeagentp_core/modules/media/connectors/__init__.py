"""Modular read-only media service connectors."""

from homeagentp_core.modules.media.connectors.jellyfin import JellyfinAdapter
from homeagentp_core.modules.media.connectors.qbittorrent import (
    QBITTORRENT_CREDENTIAL_NOTICE,
    QBittorrentAdapter,
)
from homeagentp_core.modules.media.connectors.sonarr import SonarrAdapter

__all__ = [
    "QBITTORRENT_CREDENTIAL_NOTICE",
    "JellyfinAdapter",
    "QBittorrentAdapter",
    "SonarrAdapter",
]

