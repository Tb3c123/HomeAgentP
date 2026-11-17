"""SSRF-hardened, read-only HTTP client for Media & Downloads connectors."""

from __future__ import annotations

import json
from typing import Any

import httpx

from homeagentp_core.logging import redact_text
from homeagentp_core.modules.media.errors import (
    MediaAdapterError,
    MediaAuthError,
    MediaConnectionError,
    MediaMalformedResponseError,
    MediaSecurityError,
    MediaTimeoutError,
)
from homeagentp_core.modules.media.security import validate_service_url


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
