"""URL, SSRF, and API version validation helpers for Media & Downloads connectors."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

from homeagentp_core.modules.media.errors import MediaSecurityError, MediaVersionError


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
