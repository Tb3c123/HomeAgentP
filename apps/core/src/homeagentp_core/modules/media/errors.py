"""Structured exception hierarchy for Phase 03 Media & Downloads adapters."""

from __future__ import annotations

from homeagentp_core.logging import redact_text


class MediaAdapterError(Exception):
    """Base structured exception for Media & Downloads adapters."""

    def __init__(self, error_code: str, message: str, *, status: str = "error") -> None:
        super().__init__(redact_text(message))
        self.error_code = error_code
        self.safe_message = redact_text(message)
        self.status = status


class MediaSecurityError(MediaAdapterError):
    """Raised when an adapter request violates SSRF, redirect, or read-only allowlist policy."""

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(error_code, message, status="error")


class MediaAuthError(MediaAdapterError):
    """Raised on HTTP 401/403 or invalid service credentials."""

    def __init__(self, message: str = "Service authentication failed.") -> None:
        super().__init__("auth_failed", message, status="auth_error")


class MediaTimeoutError(MediaAdapterError):
    """Raised when a service API request exceeds the configured timeout."""

    def __init__(self, message: str = "Service request timed out.") -> None:
        super().__init__("timeout", message, status="timeout")


class MediaConnectionError(MediaAdapterError):
    """Raised when a service is unreachable or drops the connection."""

    def __init__(self, message: str = "Unable to connect to service.") -> None:
        super().__init__("connection_failed", message, status="error")


class MediaMalformedResponseError(MediaAdapterError):
    """Raised when a service returns invalid JSON, unexpected types, or oversized payloads."""

    def __init__(
        self,
        message: str = "Service returned a malformed response.",
        *,
        error_code: str = "malformed_response",
    ) -> None:
        super().__init__(error_code, message, status="error")


class MediaVersionError(MediaAdapterError):
    """Raised when a service reports an incompatible or unsupported API/server version."""

    def __init__(self, message: str) -> None:
        super().__init__("unsupported_version", message, status="error")
