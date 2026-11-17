"""RBAC, secret detection, URL validation, and redacted error helpers for Workspace."""

from __future__ import annotations

import re
from collections.abc import Mapping
from urllib.parse import urlparse

from fastapi import Depends, HTTPException, status

from homeagentp_core.auth.security import AuthenticatedPrincipal, require_csrf

_TOKEN_PREFIX_RE = re.compile(
    r"(?:ghp_[A-Za-z0-9]{20,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|"
    r"glpat-[A-Za-z0-9_-]{20,}|"
    r"sk-[A-Za-z0-9]{20,}|"
    r"AKIA[0-9A-Z]{16}|"
    r"xox[baprs]-[A-Za-z0-9-]{10,}|"
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----)",
    re.IGNORECASE,
)

_AUTH_HEADER_RE = re.compile(
    r"\b(?:Bearer|Basic)\s+[A-Za-z0-9._+/=-]{12,}",
    re.IGNORECASE,
)

_CRED_ASSIGN_RE = re.compile(
    r"\b(?:password|passwd|secret|api_key|apikey|access_token|auth_token|private_key)\b"
    r"\s*[:=]\s*['\"]?([^\s'\"]{8,})['\"]?",
    re.IGNORECASE,
)

_URL_USERINFO_RE = re.compile(r"https?://[^\s/@:]+:[^\s/@]+@", re.IGNORECASE)

_PLACEHOLDER_PREFIXES = (
    "changeme",
    "placeholder",
    "example",
    "your_",
    "<redacted>",
    "redacted",
    "***",
    "replace_",
    "dummy",
)


def require_workspace_owner(
    principal: AuthenticatedPrincipal = Depends(require_csrf),
) -> AuthenticatedPrincipal:
    """Enforce owner role (plus session + CSRF) for any mutating workspace operation."""
    if principal.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner role required for workspace modifications.",
        )
    return principal


def contains_secret_or_credential(value: str) -> bool:
    """Detect token prefixes, auth headers, credential assignments, or URL userinfo."""
    if not value:
        return False
    if _TOKEN_PREFIX_RE.search(value):
        return True
    if _AUTH_HEADER_RE.search(value):
        return True
    if _URL_USERINFO_RE.search(value):
        return True
    for match in _CRED_ASSIGN_RE.finditer(value):
        candidate = match.group(1).strip().lower()
        if not any(candidate.startswith(prefix) for prefix in _PLACEHOLDER_PREFIXES):
            return True
    return False


def assert_no_secrets(fields: Mapping[str, str | list[str]]) -> None:
    """Raise a sanitized 400 error if any field contains a secret or credential pattern."""
    for field_name, raw_val in fields.items():
        items = raw_val if isinstance(raw_val, list) else [raw_val]
        for item in items:
            if contains_secret_or_credential(item):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Field '{field_name}' contains a disallowed secret or credential pattern."
                    ),
                )


def validate_github_https_url(url: str, *, field_name: str = "git_url") -> str:
    """Validate that a Git reference URL is an HTTPS github.com URL without userinfo."""
    cleaned = url.strip()
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Field '{field_name}' must not be empty.",
        )
    if contains_secret_or_credential(cleaned):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Field '{field_name}' contains disallowed credentials.",
        )
    parsed = urlparse(cleaned)
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Field '{field_name}' must use https://github.com/.",
        )
    if parsed.username or parsed.password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Field '{field_name}' must not include URL credentials.",
        )
    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Field '{field_name}' must reference a GitHub owner/repository path.",
        )
    return cleaned


def validate_relative_path_syntax(rel_path: str) -> str:
    """Pre-validate relative path syntax before delegating to safe_reader."""
    cleaned = rel_path.strip()
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Field 'rel_path' is required for allowlisted file artifacts.",
        )
    if (
        cleaned.startswith("/")
        or cleaned.startswith("\\")
        or "\\" in cleaned
        or "\x00" in cleaned
        or ".." in cleaned.split("/")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or disallowed relative artifact path.",
        )
    return cleaned
