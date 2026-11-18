"""Security, allowlist, SSRF, and data-minimization helpers for Home Assistant (P05-F01)."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlsplit

from homeagentp_core.net.safe_http import NetworkSecurityError, resolve_and_validate_host

ENTITY_ID_PATTERN = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")
MAX_HA_ALLOWED_ENTITIES = 25
MAX_HA_STATE_LEN = 128
MAX_HA_ATTR_VALUE_LEN = 128
MAX_HA_ATTRIBUTES_JSON_BYTES = 1024

ALLOWED_HA_ATTRIBUTE_KEYS = frozenset(
    {
        "unit_of_measurement",
        "device_class",
        "friendly_name",
        "state_class",
        "icon",
    }
)


class HaSecurityError(RuntimeError):
    """Fail-closed Home Assistant URL, allowlist, or payload security error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def validate_ha_url(raw_url: str, allowed_hosts: list[str]) -> str:
    """Validate HA base URL against scheme, credentials, host allowlist, and SSRF policy."""
    cleaned = raw_url.strip().rstrip("/")
    if not cleaned:
        raise HaSecurityError("invalid_url", "Home Assistant URL is empty.")

    parts = urlsplit(cleaned)
    if parts.scheme not in {"http", "https"}:
        raise HaSecurityError("invalid_url", "Home Assistant URL must use http or https.")
    if parts.username or parts.password:
        raise HaSecurityError(
            "invalid_url", "Home Assistant URL must not contain embedded credentials."
        )
    if parts.query or parts.fragment:
        raise HaSecurityError(
            "invalid_url", "Home Assistant URL must not include query strings or fragments."
        )
    hostname = (parts.hostname or "").strip().lower()
    if not hostname:
        raise HaSecurityError("invalid_url", "Home Assistant URL is missing a hostname.")

    normalized_allowlist = {h.strip().lower() for h in allowed_hosts if h.strip()}
    if hostname not in normalized_allowlist:
        raise HaSecurityError(
            "host_not_allowlisted",
            f"Home Assistant host '{hostname}' is not in HOMEAGENTP_HA_ALLOWED_HOSTS.",
        )

    try:
        port = parts.port
    except ValueError as exc:
        raise HaSecurityError(
            "invalid_url", "Home Assistant URL contains an invalid port."
        ) from exc

    try:
        resolve_and_validate_host(hostname, port, require_public_ip=False)
    except NetworkSecurityError as exc:
        raise HaSecurityError(exc.code, exc.message) from exc

    return cleaned


def validate_ha_entity_id(entity_id: str) -> str:
    """Validate a Home Assistant entity_id against strict domain.object_id syntax."""
    cleaned = entity_id.strip().lower()
    if not cleaned or len(cleaned) > 120 or not ENTITY_ID_PATTERN.match(cleaned):
        raise HaSecurityError(
            "invalid_entity_id",
            f"Invalid Home Assistant entity_id '{entity_id}'.",
        )
    return cleaned


def validate_ha_allowlist(entities: list[str]) -> list[str]:
    """Validate and deduplicate the HA entity allowlist, enforcing max 25 entities."""
    validated: list[str] = []
    for raw in entities:
        eid = validate_ha_entity_id(raw)
        if eid not in validated:
            validated.append(eid)
    if len(validated) > MAX_HA_ALLOWED_ENTITIES:
        raise HaSecurityError(
            "allowlist_too_large",
            f"Home Assistant entity allowlist exceeds {MAX_HA_ALLOWED_ENTITIES} entities.",
        )
    return validated


def minimize_ha_state_payload(
    raw_payload: dict[str, Any],
    *,
    expected_entity_id: str,
) -> tuple[str, str, dict[str, Any], str | None]:
    """Extract only minimized, allowlisted fields from an HA /api/states/{entity_id} payload."""
    raw_state = str(raw_payload.get("state", "unknown")).strip()
    state = raw_state[:MAX_HA_STATE_LEN] if raw_state else "unknown"

    raw_attrs = raw_payload.get("attributes")
    minimized_attrs: dict[str, Any] = {}
    friendly_name = expected_entity_id

    if isinstance(raw_attrs, dict):
        for key in sorted(ALLOWED_HA_ATTRIBUTE_KEYS):
            if key not in raw_attrs:
                continue
            val = raw_attrs[key]
            if isinstance(val, (str, int, float, bool)):
                if isinstance(val, str):
                    cleaned_val: str | int | float | bool = val.strip()[:MAX_HA_ATTR_VALUE_LEN]
                else:
                    cleaned_val = val
                minimized_attrs[key] = cleaned_val
                if key == "friendly_name" and isinstance(cleaned_val, str) and cleaned_val:
                    friendly_name = cleaned_val

    while (
        len(json.dumps(minimized_attrs, ensure_ascii=False).encode("utf-8"))
        > MAX_HA_ATTRIBUTES_JSON_BYTES
    ):
        if not minimized_attrs:
            break
        last_key = sorted(minimized_attrs.keys())[-1]
        del minimized_attrs[last_key]

    last_changed = raw_payload.get("last_changed")
    last_changed_str = (
        str(last_changed)[:64] if isinstance(last_changed, str) and last_changed else None
    )
    return state, friendly_name, minimized_attrs, last_changed_str
