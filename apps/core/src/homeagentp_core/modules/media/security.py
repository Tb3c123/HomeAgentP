"""URL, SSRF, DNS, and API version validation helpers for Media & Downloads connectors.

Security & Threat Notes:
- Outbound service URLs are restricted to `http`/`https`, without embedded credentials,
  query strings, fragments, or invalid ports.
- Hostnames must be explicitly allowlisted in `HOMEAGENTP_MEDIA_ALLOWED_HOSTS`.
- Both IP literals and DNS-resolved addresses (including IPv4-mapped IPv6 addresses such
  as `::ffff:169.254.169.254`) are checked against unspecified (`0.0.0.0`, `::`),
  multicast, and link-local / cloud metadata (`169.254.0.0/16`, `fe80::/10`) ranges.
- Private RFC1918 LAN and loopback addresses are permitted *only* when explicitly listed
  in `HOMEAGENTP_MEDIA_ALLOWED_HOSTS` so local NAS services remain reachable.
- DNS rebinding mitigation: when `SafeMediaHttpClient` runs without a mock transport,
  DNS resolution is checked prior to request dispatch; for production NAS deployments,
  static LAN IPs or `/etc/hosts` entries in `HOMEAGENTP_MEDIA_ALLOWED_HOSTS` are
  recommended to eliminate TOCTOU DNS rebinding windows.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

from homeagentp_core.modules.media.errors import MediaSecurityError, MediaVersionError


def _validate_ip_object(
    ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address,
    hostname: str,
) -> None:
    """Reject unspecified, multicast, link-local, metadata, and mapped equivalents."""
    if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.ipv4_mapped is not None:
        _validate_ip_object(ip_obj.ipv4_mapped, hostname)

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


def validate_resolved_dns(hostname: str) -> None:
    """Validate all DNS-resolved IPs for a hostname against dangerous SSRF ranges."""
    try:
        ipaddress.ip_address(hostname)
        return
    except ValueError:
        pass

    try:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except OSError:
        return

    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        raw_ip = str(sockaddr[0]).split("%", 1)[0]
        try:
            resolved_ip = ipaddress.ip_address(raw_ip)
        except ValueError:
            continue
        _validate_ip_object(resolved_ip, hostname)


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
        _validate_ip_object(ip_obj, hostname)

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
