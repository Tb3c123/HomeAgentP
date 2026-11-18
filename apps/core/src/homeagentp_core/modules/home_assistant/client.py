"""Read-only, SSRF-hardened HTTP client for Home Assistant REST API (P05-F01)."""

from __future__ import annotations

import json
from typing import Any

import httpx

from homeagentp_core.logging import redact_text
from homeagentp_core.modules.home_assistant.security import (
    HaSecurityError,
    validate_ha_entity_id,
    validate_ha_url,
)
from homeagentp_core.net.safe_http import NetworkSecurityError, build_pinned_transport


class HaClientError(RuntimeError):
    """Sanitized Home Assistant read-only client error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(redact_text(message))
        self.code = code
        self.message = redact_text(message)


class HomeAssistantReadOnlyClient:
    """Strictly read-only (GET /api/ and GET /api/states/{entity_id}) HA client."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        allowed_hosts: list[str],
        timeout_seconds: float = 5.0,
        max_response_bytes: int = 524_288,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = validate_ha_url(base_url, allowed_hosts)
        cleaned_token = token.strip()
        if not cleaned_token:
            raise HaSecurityError("missing_token", "Home Assistant token is not configured.")
        self._token = cleaned_token
        self._timeout = timeout_seconds
        self._max_response_bytes = max_response_bytes
        if transport is not None:
            self._transport = transport
        else:
            try:
                self._transport = build_pinned_transport(require_public_ip=False)
            except NetworkSecurityError as exc:
                raise HaSecurityError(exc.code, exc.message) from exc

    def _get_json(self, path: str) -> dict[str, Any]:
        """Execute a strictly read-only GET request with redirect blocking and size caps."""
        if not (path == "/api/" or path.startswith("/api/states/")):
            raise HaSecurityError("disallowed_endpoint", f"Endpoint '{path}' is not allowlisted.")

        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
        }
        try:
            with httpx.Client(
                base_url=self._base_url,
                timeout=self._timeout,
                follow_redirects=False,
                transport=self._transport,
            ) as client:
                with client.stream("GET", path, headers=headers) as resp:
                    if 300 <= resp.status_code < 400:
                        raise HaClientError(
                            "redirect_blocked",
                            f"Home Assistant HTTP redirect ({resp.status_code}) blocked.",
                        )
                    if resp.status_code in {401, 403}:
                        raise HaClientError(
                            "auth_failed",
                            f"Home Assistant authentication failed (HTTP {resp.status_code}).",
                        )
                    if resp.status_code == 404:
                        raise HaClientError(
                            "not_found",
                            f"Home Assistant resource '{path}' not found (HTTP 404).",
                        )
                    if resp.status_code >= 400:
                        raise HaClientError(
                            "http_error",
                            f"Home Assistant returned HTTP {resp.status_code}.",
                        )

                    chunks: list[bytes] = []
                    total = 0
                    for chunk in resp.iter_bytes():
                        total += len(chunk)
                        if total > self._max_response_bytes:
                            raise HaClientError(
                                "payload_too_large",
                                "Home Assistant response exceeded "
                                f"{self._max_response_bytes} bytes.",
                            )
                        chunks.append(chunk)
        except HaClientError:
            raise
        except httpx.TimeoutException as exc:
            raise HaClientError("timeout", "Home Assistant request timed out.") from exc
        except (httpx.RequestError, NetworkSecurityError) as exc:
            raise HaClientError(
                "connection_error", f"Home Assistant connection failed: {exc}"
            ) from exc

        try:
            decoded = json.loads(b"".join(chunks).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HaClientError("malformed_json", "Home Assistant returned invalid JSON.") from exc

        if not isinstance(decoded, dict):
            raise HaClientError("malformed_json", "Home Assistant JSON response must be an object.")
        return decoded

    def check_health(self) -> dict[str, Any]:
        """Call GET /api/ to verify Home Assistant API availability."""
        return self._get_json("/api/")

    def get_entity_state(self, entity_id: str) -> dict[str, Any]:
        """Call GET /api/states/{entity_id} for an explicitly validated entity_id."""
        validated_id = validate_ha_entity_id(entity_id)
        return self._get_json(f"/api/states/{validated_id}")
