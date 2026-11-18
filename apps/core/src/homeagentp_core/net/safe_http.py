"""Shared SSRF, DNS-pinning, and public-IP enforcement helpers.

Dependency Compatibility:
- Tested against `httpx>=0.27.0,<0.29.0` and `httpcore>=1.0.0,<2.0.0`.
- `build_pinned_transport()` verifies `httpx.HTTPTransport._pool` is an
  `httpcore.ConnectionPool` with `_network_backend` and fails closed with
  `NetworkSecurityError("ssrf_pinning_unavailable", ...)` if internals change.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Iterable
from typing import Any

import httpcore
import httpx
from httpcore._backends.sync import SyncBackend


class NetworkSecurityError(RuntimeError):
    """Fail-closed SSRF, DNS resolution, or transport pinning error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def validate_ip_object(
    ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address,
    hostname: str,
    *,
    require_public_ip: bool = False,
) -> None:
    """Reject unspecified, multicast, link-local, metadata, mapped, and (optionally) private IPs."""
    if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.ipv4_mapped is not None:
        validate_ip_object(ip_obj.ipv4_mapped, hostname, require_public_ip=require_public_ip)

    if ip_obj.is_unspecified or ip_obj.is_multicast:
        raise NetworkSecurityError(
            "ssrf_blocked",
            f"Disallowed IP address target '{hostname}' (unspecified or multicast).",
        )
    if str(ip_obj).startswith("169.254.") or ip_obj.is_link_local:
        raise NetworkSecurityError(
            "ssrf_blocked",
            f"Link-local / cloud metadata address '{hostname}' is blocked by SSRF policy.",
        )
    if require_public_ip and (ip_obj.is_private or ip_obj.is_loopback or not ip_obj.is_global):
        raise NetworkSecurityError(
            "ssrf_blocked",
            f"Non-public IP address target '{hostname}' is blocked by public-IP egress policy.",
        )


def resolve_and_validate_host(
    hostname: str,
    port: int | None = None,
    *,
    require_public_ip: bool = False,
) -> list[str]:
    """Resolve hostname once, fail closed on DNS error, and validate all returned IPs."""
    cleaned = hostname.strip().lower()
    if not cleaned:
        raise NetworkSecurityError("invalid_url", "Service URL is missing a valid hostname.")

    try:
        ip_obj = ipaddress.ip_address(cleaned)
    except ValueError:
        ip_obj = None

    if ip_obj is not None:
        validate_ip_object(ip_obj, cleaned, require_public_ip=require_public_ip)
        return [str(ip_obj)]

    try:
        infos = socket.getaddrinfo(cleaned, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise NetworkSecurityError(
            "dns_resolution_failed",
            f"DNS resolution failed for '{cleaned}'.",
        ) from exc

    validated_ips: list[str] = []
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        raw_ip = str(sockaddr[0]).split("%", 1)[0]
        try:
            resolved_ip = ipaddress.ip_address(raw_ip)
        except ValueError:
            continue
        validate_ip_object(resolved_ip, cleaned, require_public_ip=require_public_ip)
        ip_str = str(resolved_ip)
        if ip_str not in validated_ips:
            validated_ips.append(ip_str)

    if not validated_ips:
        raise NetworkSecurityError(
            "dns_resolution_failed",
            f"DNS resolution returned no usable addresses for '{cleaned}'.",
        )
    return validated_ips


class SafeDnsPinningBackend(SyncBackend):
    """Network backend that performs a single DNS lookup, validates IPs, and pins the TCP target."""

    def __init__(self, *, require_public_ip: bool = False) -> None:
        super().__init__()
        self._require_public_ip = require_public_ip

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.NetworkStream:
        validated_ips = resolve_and_validate_host(
            host,
            port,
            require_public_ip=self._require_public_ip,
        )
        pinned_ip = validated_ips[0]
        return super().connect_tcp(
            pinned_ip,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )


def build_pinned_transport(*, require_public_ip: bool = False) -> httpx.HTTPTransport:
    """Build an httpx.HTTPTransport with SafeDnsPinningBackend, failing closed if unsupported."""
    try:
        transport = httpx.HTTPTransport(trust_env=False)
        pool = getattr(transport, "_pool", None)
        if not isinstance(pool, httpcore.ConnectionPool):
            raise NetworkSecurityError(
                "ssrf_pinning_unavailable",
                "Cannot enforce DNS pinning: unsupported httpx/httpcore ConnectionPool internals.",
            )
        if not hasattr(pool, "_network_backend"):
            raise NetworkSecurityError(
                "ssrf_pinning_unavailable",
                "Cannot enforce DNS pinning: ConnectionPool missing '_network_backend' attribute.",
            )
        backend = SafeDnsPinningBackend(require_public_ip=require_public_ip)
        pool._network_backend = backend
        installed = getattr(pool, "_network_backend", None)
        if installed is not backend or not isinstance(installed, SafeDnsPinningBackend):
            raise NetworkSecurityError(
                "ssrf_pinning_unavailable",
                "Cannot enforce DNS pinning: failed to verify installed network backend.",
            )
        return transport
    except NetworkSecurityError:
        raise
    except Exception as exc:
        raise NetworkSecurityError(
            "ssrf_pinning_unavailable",
            "Cannot enforce DNS pinning due to HTTP transport incompatibility: "
            f"{type(exc).__name__}.",
        ) from exc
