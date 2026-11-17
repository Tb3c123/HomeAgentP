"""Compatibility re-export layer for Phase 03 Media & Downloads base infrastructure.

Implementations live in:
- `homeagentp_core.modules.media.errors`
- `homeagentp_core.modules.media.security`
- `homeagentp_core.modules.media.http_client`
- `homeagentp_core.modules.media.adapter_base`
"""

from __future__ import annotations

from homeagentp_core.modules.media.adapter_base import (
    MediaServiceAdapter as MediaServiceAdapter,
)
from homeagentp_core.modules.media.errors import (
    MediaAdapterError as MediaAdapterError,
)
from homeagentp_core.modules.media.errors import (
    MediaAuthError as MediaAuthError,
)
from homeagentp_core.modules.media.errors import (
    MediaConnectionError as MediaConnectionError,
)
from homeagentp_core.modules.media.errors import (
    MediaMalformedResponseError as MediaMalformedResponseError,
)
from homeagentp_core.modules.media.errors import (
    MediaSecurityError as MediaSecurityError,
)
from homeagentp_core.modules.media.errors import (
    MediaTimeoutError as MediaTimeoutError,
)
from homeagentp_core.modules.media.errors import (
    MediaVersionError as MediaVersionError,
)
from homeagentp_core.modules.media.http_client import (
    SafeMediaHttpClient as SafeMediaHttpClient,
)
from homeagentp_core.modules.media.security import (
    check_semver_major as check_semver_major,
)
from homeagentp_core.modules.media.security import (
    validate_service_url as validate_service_url,
)

__all__ = [
    "MediaAdapterError",
    "MediaAuthError",
    "MediaConnectionError",
    "MediaMalformedResponseError",
    "MediaSecurityError",
    "MediaServiceAdapter",
    "MediaTimeoutError",
    "MediaVersionError",
    "SafeMediaHttpClient",
    "check_semver_major",
    "validate_service_url",
]
