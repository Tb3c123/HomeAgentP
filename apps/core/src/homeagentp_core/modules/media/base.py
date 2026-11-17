"""Base interfaces, SSRF-hardened read-only HTTP client, and error types for Phase 03 Media Hub.

Security & B+ Invariants:
- All connectors are strictly read-only. No write/delete/modify/trigger endpoints are ever called.
- Outbound requests are restricted to hostnames in `HOMEAGENTP_MEDIA_ALLOWED_HOSTS`
  (`http`/`https`), rejecting embedded credentials, cloud link-local metadata IPs
  (169.254.169.254), unspecified addresses (0.0.0.0), and HTTP redirects (`follow_redirects=False`).
- Every HTTP request enforces a strict timeout (`media_http_timeout_seconds`) and streaming
  byte ceiling (`media_max_response_bytes`).
- API keys, passwords, cookies, and tokens are never logged or returned in error payloads.
"""

from __future__ import annotations

import ipaddress
import json
import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx

from homeagentp_core.config import Settings
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


def validate_service_url(raw_url: str, allowed_hosts: list[str]) -> str:
    """Validate a configured service URL against SSRF, scheme, and host allowlist rules."""
    cleaned = raw_url.strip()
    if not cleaned:
        raise MediaSecurityError("not_configured", "Service URL is empty.")

    try:
        parsed = urlsplit(cleaned)
    except ValueError as exc:
        raise MediaSecurityError("invalid_url", f"Malformed service URL: {exc}") from exc

    if parsed.scheme not in {"http", "https"}:
        raise MediaSecurityError(
            "ssrf_blocked",
            f"Unsupported URL scheme '{parsed.scheme}'. Only http and https are allowed.",
        )

    if parsed.username is not None or parsed.password is not None:
        raise MediaSecurityError(
            "ssrf_blocked",
            "Credentials embedded in service URLs are prohibited; use secret env vars.",
        )

    if parsed.query or parsed.fragment:
        raise MediaSecurityError(
            "invalid_url",
            "Service base URL must not contain query parameters or fragments.",
        )

    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        raise MediaSecurityError("invalid_url", "Service URL is missing a valid hostname.")

    # Check IP address literals for dangerous ranges before checking host allowlist
    try:
        ip_obj = ipaddress.ip_address(hostname)
    except ValueError:
        ip_obj = None

    if ip_obj is not None:
        if ip_obj.is_unspecified or ip_obj.is_multicast:
            raise MediaSecurityError(
                "ssrf_blocked",
                f"Disallowed IP address target '{hostname}' (unspecified or multicast).",
            )
        if str(ip_obj).startswith("169.254.") or ip_obj.is_link_local:
            raise MediaSecurityError(
                "ssrf_blocked",
                f"Link-local / cloud metadata address '{hostname}' is blocked by SSRF policy.",
            )

    normalized_allowlist = {h.strip().lower() for h in allowed_hosts if h.strip()}
    if hostname not in normalized_allowlist:
        raise MediaSecurityError(
            "ssrf_blocked",
            f"Service host '{hostname}' is not in HOMEAGENTP_MEDIA_ALLOWED_HOSTS.",
        )

    try:
        port = parsed.port
    except ValueError as exc:
        raise MediaSecurityError("invalid_url", f"Invalid port in service URL: {exc}") from exc

    if port is not None and (port < 1 or port > 65535):
        raise MediaSecurityError("invalid_url", f"Port {port} is out of valid range.")

    return cleaned.rstrip("/")


def check_semver_major(version_str: str, *, min_major: int, service_label: str) -> None:
    """Verify that a reported version string meets the minimum expected major version."""
    cleaned = version_str.strip().lstrip("vV")
    if not cleaned:
        return
    first_part = cleaned.split(".")[0].split("-")[0]
    if not first_part.isdigit():
        raise MediaVersionError(
            f"{service_label} reported unrecognizable version '{version_str}'."
        )
    major = int(first_part)
    if major < min_major:
        raise MediaVersionError(
            f"{service_label} version '{version_str}' (major={major}) is older than "
            f"minimum supported major version {min_major}."
        )


class SafeMediaHttpClient:
    """SSRF-safe, read-only HTTP client with endpoint allowlisting and response size caps."""

    def __init__(
        self,
        *,
        base_url: str,
        allowed_hosts: list[str],
        timeout_seconds: float,
        max_response_bytes: int,
        allowed_get_prefixes: tuple[str, ...],
        allowed_post_paths: tuple[str, ...] = (),
        default_headers: dict[str, str] | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = validate_service_url(base_url, allowed_hosts)
        self._timeout_seconds = timeout_seconds
        self._max_response_bytes = max_response_bytes
        self._allowed_get_prefixes = allowed_get_prefixes
        self._allowed_post_paths = allowed_post_paths
        self._headers = dict(default_headers or {})
        self._cookies: dict[str, str] = {}
        self._transport = transport

    def set_cookie(self, name: str, value: str) -> None:
        """Store an in-memory session cookie (used only for qBittorrent SID)."""
        self._cookies[name] = value

    def _verify_path(self, method: str, path: str) -> None:
        upper_method = method.upper()
        if not path.startswith("/") or ".." in path or "\\" in path:
            raise MediaSecurityError(
                "invalid_path",
                f"Disallowed relative API path '{path}'.",
            )
        if upper_method == "GET":
            if not any(
                path == prefix or path.startswith(prefix)
                for prefix in self._allowed_get_prefixes
            ):
                raise MediaSecurityError(
                    "endpoint_not_allowlisted",
                    f"GET endpoint '{path}' is not in the read-only allowlist.",
                )
            return
        if upper_method == "POST":
            if path not in self._allowed_post_paths:
                raise MediaSecurityError(
                    "write_method_prohibited",
                    f"POST to '{path}' is prohibited by the read-only adapter policy.",
                )
            return
        raise MediaSecurityError(
            "write_method_prohibited",
            f"HTTP method '{upper_method}' is prohibited by the read-only adapter policy.",
        )

    def request_raw(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        form_data: dict[str, str] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> tuple[int, bytes, httpx.Headers, dict[str, str]]:
        """Execute a validated HTTP request with redirect blocking and streaming byte caps."""
        self._verify_path(method, path)
        target_url = f"{self.base_url}{path}"
        merged_headers = {**self._headers, **(extra_headers or {})}

        try:
            with httpx.Client(
                timeout=httpx.Timeout(self._timeout_seconds),
                follow_redirects=False,
                headers=merged_headers,
                cookies=self._cookies,
                transport=self._transport,
            ) as client:
                with client.stream(
                    method.upper(),
                    target_url,
                    params=params,
                    data=form_data,
                ) as response:
                    status_code = response.status_code
                    if status_code in {301, 302, 303, 307, 308}:
                        raise MediaSecurityError(
                            "redirect_blocked",
                            f"HTTP redirect ({status_code}) from '{path}' is blocked by "
                            "SSRF policy.",
                        )
                    if status_code in {401, 403}:
                        raise MediaAuthError(
                            f"Authentication rejected by service (HTTP {status_code}) on '{path}'."
                        )

                    chunks: list[bytes] = []
                    total_read = 0
                    for chunk in response.iter_bytes():
                        total_read += len(chunk)
                        if total_read > self._max_response_bytes:
                            raise MediaMalformedResponseError(
                                f"Response from '{path}' exceeded maximum allowed size "
                                f"({self._max_response_bytes} bytes).",
                                error_code="response_too_large",
                            )
                        chunks.append(chunk)

                    body = b"".join(chunks)
                    resp_cookies = {k: str(v) for k, v in response.cookies.items()}
                    if status_code >= 400:
                        raise MediaAdapterError(
                            f"http_{status_code}",
                            f"Service returned HTTP {status_code} on '{path}'.",
                            status="error",
                        )
                    return status_code, body, response.headers, resp_cookies
        except MediaAdapterError:
            raise
        except httpx.TimeoutException as exc:
            raise MediaTimeoutError(
                f"Request to '{path}' timed out after {self._timeout_seconds}s."
            ) from exc
        except httpx.RequestError as exc:
            raise MediaConnectionError(
                f"Connection error requesting '{path}': {redact_text(str(exc))}"
            ) from exc

    def get_json(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        """Perform an allowlisted GET request and decode JSON safely."""
        _, body, _, _ = self.request_raw("GET", path, params=params)
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MediaMalformedResponseError(
                f"Invalid JSON payload from '{path}': {exc}"
            ) from exc

    def get_text(self, path: str, *, params: dict[str, Any] | None = None) -> str:
        """Perform an allowlisted GET request and decode UTF-8 text."""
        _, body, _, _ = self.request_raw("GET", path, params=params)
        try:
            return body.decode("utf-8").strip()
        except UnicodeDecodeError as exc:
            raise MediaMalformedResponseError(
                f"Invalid UTF-8 text payload from '{path}': {exc}"
            ) from exc


class MediaServiceAdapter(ABC):
    """Uniform read-only adapter interface for all Phase 03 Media & Downloads services."""

    service_name: str
    title: str
    category: Literal["media", "downloads"]

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    @abstractmethod
    def is_configured(self) -> tuple[bool, str]:
        """Return (configured_and_enabled, reason_if_not)."""

    @abstractmethod
    def _empty_metrics(self) -> dict[str, Any]:
        """Return honest empty/unavailable metric structure for this service."""

    @abstractmethod
    def _poll_live(
        self, now_iso: str
    ) -> tuple[str, str | None, dict[str, Any], list[dict[str, Any]], str]:
        """Execute read-only API calls and return (status, version, metrics, alerts, reason)."""

    def collect(self, *, now: datetime | None = None) -> dict[str, Any]:
        """Collect a read-only snapshot with full fault isolation and latency measurement."""
        ref_now = now or datetime.now(UTC)
        now_iso = ref_now.isoformat()

        if not self._settings.media_adapter_enabled:
            return {
                "service": self.service_name,
                "title": self.title,
                "category": self.category,
                "enabled": False,
                "configured": False,
                "status": "unavailable",
                "error_code": None,
                "reason": (
                    "Media & Downloads monitoring hub is disabled "
                    "(HOMEAGENTP_MEDIA_ADAPTER_ENABLED=false)."
                ),
                "latency_ms": None,
                "version": None,
                "collected_at": now_iso,
                "stale": False,
                "age_seconds": 0.0,
                "consecutive_failures": 0,
                "read_only_enforced": True,
                "write_operations_performed": 0,
                "metrics": self._empty_metrics(),
                "alerts": [],
            }

        configured, reason = self.is_configured()
        if not configured:
            return {
                "service": self.service_name,
                "title": self.title,
                "category": self.category,
                "enabled": False,
                "configured": False,
                "status": "unavailable",
                "error_code": None,
                "reason": reason,
                "latency_ms": None,
                "version": None,
                "collected_at": now_iso,
                "stale": False,
                "age_seconds": 0.0,
                "consecutive_failures": 0,
                "read_only_enforced": True,
                "write_operations_performed": 0,
                "metrics": self._empty_metrics(),
                "alerts": [],
            }

        start_t = time.monotonic()
        try:
            svc_status, version, metrics, alerts, ok_reason = self._poll_live(now_iso)
            latency_ms = round((time.monotonic() - start_t) * 1000.0, 2)
            return {
                "service": self.service_name,
                "title": self.title,
                "category": self.category,
                "enabled": True,
                "configured": True,
                "status": svc_status,
                "error_code": None,
                "reason": ok_reason,
                "latency_ms": latency_ms,
                "version": version,
                "collected_at": now_iso,
                "stale": False,
                "age_seconds": 0.0,
                "consecutive_failures": 0,
                "read_only_enforced": True,
                "write_operations_performed": 0,
                "metrics": metrics,
                "alerts": alerts,
            }
        except MediaAdapterError as exc:
            latency_ms = round((time.monotonic() - start_t) * 1000.0, 2)
            return {
                "service": self.service_name,
                "title": self.title,
                "category": self.category,
                "enabled": True,
                "configured": True,
                "status": exc.status,
                "error_code": exc.error_code,
                "reason": exc.safe_message,
                "latency_ms": latency_ms,
                "version": None,
                "collected_at": now_iso,
                "stale": False,
                "age_seconds": 0.0,
                "consecutive_failures": 1,
                "read_only_enforced": True,
                "write_operations_performed": 0,
                "metrics": self._empty_metrics(),
                "alerts": [],
            }
        except Exception as exc:
            latency_ms = round((time.monotonic() - start_t) * 1000.0, 2)
            safe_err = redact_text(f"{type(exc).__name__}: {exc}")
            return {
                "service": self.service_name,
                "title": self.title,
                "category": self.category,
                "enabled": True,
                "configured": True,
                "status": "error",
                "error_code": "unexpected_error",
                "reason": safe_err,
                "latency_ms": latency_ms,
                "version": None,
                "collected_at": now_iso,
                "stale": False,
                "age_seconds": 0.0,
                "consecutive_failures": 1,
                "read_only_enforced": True,
                "write_operations_performed": 0,
                "metrics": self._empty_metrics(),
                "alerts": [],
            }
