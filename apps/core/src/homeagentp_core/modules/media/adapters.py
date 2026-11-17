"""Compatibility re-export layer for Media & Downloads connectors.

All connector implementations now live in `homeagentp_core.modules.media.connectors`.
This module preserves existing import paths for callers and tests.
"""

from __future__ import annotations

from homeagentp_core.modules.media.connectors.arr_common import (
    _ArrV3BaseAdapter as _ArrV3BaseAdapter,
)
from homeagentp_core.modules.media.connectors.bazarr import (
    BazarrAdapter as BazarrAdapter,
)
from homeagentp_core.modules.media.connectors.jellyfin import (
    JellyfinAdapter as JellyfinAdapter,
)
from homeagentp_core.modules.media.connectors.prowlarr import (
    ProwlarrAdapter as ProwlarrAdapter,
)
from homeagentp_core.modules.media.connectors.qbittorrent import (
    QBITTORRENT_CREDENTIAL_NOTICE as QBITTORRENT_CREDENTIAL_NOTICE,
)
from homeagentp_core.modules.media.connectors.qbittorrent import (
    QBittorrentAdapter as QBittorrentAdapter,
)
from homeagentp_core.modules.media.connectors.radarr import (
    RadarrAdapter as RadarrAdapter,
)
from homeagentp_core.modules.media.connectors.registry import (
    build_media_adapters as build_media_adapters,
)
from homeagentp_core.modules.media.connectors.seerr import (
    SeerrAdapter as SeerrAdapter,
)
from homeagentp_core.modules.media.connectors.sonarr import (
    SonarrAdapter as SonarrAdapter,
)

__all__ = [
    "QBITTORRENT_CREDENTIAL_NOTICE",
    "BazarrAdapter",
    "JellyfinAdapter",
    "ProwlarrAdapter",
    "QBittorrentAdapter",
    "RadarrAdapter",
    "SeerrAdapter",
    "SonarrAdapter",
    "_ArrV3BaseAdapter",
    "build_media_adapters",
]
