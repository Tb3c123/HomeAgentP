"""SSRF-hardened, read-only HTTP client for Media & Downloads connectors.

Dependency Compatibility:
- Tested against `httpx>=0.27.0,<0.29.0` and `httpcore>=1.0.0,<2.0.0`.
- `_build_pinned_transport()` explicitly verifies `httpx.HTTPTransport._pool` is an
  `httpcore.ConnectionPool` with `_network_backend` and fails closed with
  `MediaSecurityError("ssrf_pinning_unavailable", ...)` if internals change.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

import httpcore
import httpx
from httpcore._backends.sync import SyncBackend

from homeagentp_core.logging import redact_text
from homeagentp_core.modules.media.errors import (
    MediaAdapterError,
    MediaAuthError,
    MediaConnectionError,
    MediaMalformedResponseError,
    MediaSecurityError,
    MediaTimeoutError,
)
from homeagentp_core.modules.media.security import (
    resolve_and_validate_host,
    validate_service_url,
)


def _matches_segment_prefix(path: str, prefix: str) -> bool:
    """Match an API path against an allowlisted prefix on exact or '/' segment boundaries."""
    clean_prefix = prefix.rstrip("/")
    if not clean_prefix:
        return path == "/"
    return path == clean_prefix or path.startswith(f"{clean_prefix}/")


class SafeDnsPinningBackend(SyncBackend):
    """Network backend that performs a single DNS lookup, validates IPs, and pins the TCP target."""

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.NetworkStream:
        validated_ips = resolve_and_validate_host(host, port)
        pinned_ip = validated_ips[0]
        return super().connect_tcp(
            pinned_ip,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )


def _build_pinned_transport() -> httpx.HTTPTransport:
    """Build an httpx.HTTPTransport with SafeDnsPinningBackend, failing closed if unsupported."""
    try:
        transport = httpx.HTTPTransport(trust_env=False)
        pool = getattr(transport, "_pool", None)
        if not isinstance(pool, httpcore.ConnectionPool):
            raise MediaSecurityError(
                "ssrf_pinning_unavailable",
                "Cannot enforce DNS pinning: unsupported httpx/httpcore ConnectionPool internals.",
            )
        if not hasattr(pool, "_network_backend"):
            raise MediaSecurityError(
                "ssrf_pinning_unavailable",
                "Cannot enforce DNS pinning: ConnectionPool missing '_network_backend' attribute.",
            )
        backend = SafeDnsPinningBackend()
        pool._network_backend = backend
        installed = getattr(pool, "_network_backend", None)
        if installed is not backend or not isinstance(installed, SafeDnsPinningBackend):
            raise MediaSecurityError(
                "ssrf_pinning_unavailable",
                "Cannot enforce DNS pinning: failed to verify installed network backend.",
            )
        return transport
    except MediaSecurityError:
        raise
    except Exception as exc:
        raise MediaSecurityError(
            "ssrf_pinning_unavailable",
            "Cannot enforce DNS pinning due to HTTP transport incompatibility: "
            f"{type(exc).__name__}.",
        ) from exc


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
        lower_path = path.lower()
        if (
            not path.startswith("/")
            or ".." in path
            or "\\" in path
            or "?" in path
            or "#" in path
            or any(ctrl in path for ctrl in ("\r", "\n", "\x00"))
            or "%2e" in lower_path
            or "%2f" in lower_path
            or "%5c" in lower_path
        ):
            raise MediaSecurityError(
                "invalid_path",
                f"Disallowed relative API path '{path}'.",
            )
        if upper_method == "GET":
            if not any(
                _matches_segment_prefix(path, prefix)
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
        """Execute a validated HTTP request with DNS-pinned transport and redirect blocking."""
        self._verify_path(method, path)
        target_url = f"{self.base_url}{path}"
        merged_headers = {**self._headers, **(extra_headers or {})}
        active_transport = self._transport or _build_pinned_transport()

        try:
            with httpx.Client(
                timeout=httpx.Timeout(self._timeout_seconds),
                follow_redirects=False,
                trust_env=False,
                headers=merged_headers,
                cookies=self._cookies,
                transport=active_transport,
            ) as client:
                with client.stream(
                    method.upper(),
                    target_url,
                    params=params,
                    data=form_data,
                ) as response:
                    status_code = response.status_code
                    if 300 <= status_code < 400 and status_code != 304:
                        raise MediaSecurityError(
                            "redirect_blocked",
                            f"HTTP redirect ({status_code}) from '{path}' is blocked by "
                            "SSRF policy.",
                        )
                    if status_code in {401, 403}:
                        raise MediaAuthError(
                            f"Authentication rejected by service (HTTP {status_code}) on '{path}'."
                        )

                    content_length_raw = response.headers.get("content-length")
                    if content_length_raw is not None:
                        try:
                            declared_length = int(content_length_raw)
                        except ValueError:
                            declared_length = -1
                        if declared_length > self._max_response_bytes:
                            raise MediaMalformedResponseError(
                                f"Response from '{path}' declared Content-Length "
                                f"({declared_length} bytes) exceeding maximum allowed size "
                                f"({self._max_response_bytes} bytes).",
                                error_code="response_too_large",
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
