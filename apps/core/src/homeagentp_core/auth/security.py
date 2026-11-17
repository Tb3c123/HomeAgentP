"""Security primitives: password hashing, session management, CSRF validation, and audit logs."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Cookie, Depends, Header, HTTPException, Request, status

from homeagentp_core.config import Settings
from homeagentp_core.db.connection import db_session
from homeagentp_core.logging import redact_structure

PBKDF2_ITERATIONS = 600_000
SESSION_COOKIE_NAME = "homeagentp_session"


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    user_id: int
    username: str
    role: str
    session_id_hash: str
    csrf_token: str
    expires_at: str


def hash_password(password: str, salt: bytes | None = None) -> str:
    """Hash a password using PBKDF2-HMAC-SHA256 (600,000 iterations)."""
    actual_salt = salt if salt is not None else secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        actual_salt,
        PBKDF2_ITERATIONS,
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${actual_salt.hex()}${derived.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against a stored PBKDF2-HMAC-SHA256 hash in constant time."""
    try:
        algorithm, iterations_str, salt_hex, hash_hex = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_str)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, TypeError):
        return False

    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(derived, expected)


def hash_session_token(raw_token: str, secret_key: str) -> str:
    """Compute HMAC-SHA256 of the raw session token so raw tokens are never stored in DB."""
    return hmac.new(
        secret_key.encode("utf-8"),
        raw_token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def record_audit_log(
    conn: sqlite3.Connection,
    *,
    actor: str,
    action: str,
    target_type: str,
    target_id: str = "",
    details: dict[str, Any] | None = None,
    ip_address: str = "",
) -> None:
    """Insert a redacted audit log entry."""
    safe_details = redact_structure(details or {})
    conn.execute(
        """
        INSERT INTO audit_logs (
            actor, action, target_type, target_id, details_json, ip_address, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            actor,
            action,
            target_type,
            str(target_id),
            json.dumps(safe_details, ensure_ascii=False),
            ip_address,
            datetime.now(UTC).isoformat(),
        ),
    )


def ensure_admin_user(conn: sqlite3.Connection, settings: Settings) -> None:
    """Ensure the configured admin user exists in the database."""
    row = conn.execute(
        "SELECT id FROM users WHERE username = ?",
        (settings.admin_username,),
    ).fetchone()
    if row is None:
        conn.execute(
            """
            INSERT INTO users (username, password_hash, role, is_active, created_at)
            VALUES (?, ?, 'owner', 1, ?)
            """,
            (
                settings.admin_username,
                hash_password(settings.admin_password),
                datetime.now(UTC).isoformat(),
            ),
        )
        record_audit_log(
            conn,
            actor="system",
            action="user.bootstrap",
            target_type="user",
            target_id=settings.admin_username,
            details={"role": "owner"},
        )


def get_settings(request: Request) -> Settings:
    """Retrieve application settings from FastAPI app.state."""
    settings: Settings = request.app.state.settings
    return settings


def get_current_principal(
    request: Request,
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    settings: Settings = Depends(get_settings),
) -> AuthenticatedPrincipal:
    """Validate the session cookie and return the authenticated principal."""
    if not session_cookie:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    session_id_hash = hash_session_token(session_cookie, settings.secret_key)
    now_iso = datetime.now(UTC).isoformat()

    with db_session(settings.db_path) as conn:
        row = conn.execute(
            """
            SELECT
                s.id AS session_id_hash,
                s.user_id AS user_id,
                s.csrf_token AS csrf_token,
                s.expires_at AS expires_at,
                u.username AS username,
                u.role AS role,
                u.is_active AS is_active
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.id = ?
            """,
            (session_id_hash,),
        ).fetchone()

        if row is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired session.",
            )

        if int(row["is_active"]) != 1 or str(row["expires_at"]) <= now_iso:
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id_hash,))
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired.",
            )

        conn.execute(
            "UPDATE sessions SET last_seen_at = ? WHERE id = ?",
            (now_iso, session_id_hash),
        )

        return AuthenticatedPrincipal(
            user_id=int(row["user_id"]),
            username=str(row["username"]),
            role=str(row["role"]),
            session_id_hash=str(row["session_id_hash"]),
            csrf_token=str(row["csrf_token"]),
            expires_at=str(row["expires_at"]),
        )


def require_csrf(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> AuthenticatedPrincipal:
    """Require both a valid session and a matching X-CSRF-Token header for write operations."""
    if not x_csrf_token or not hmac.compare_digest(x_csrf_token, principal.csrf_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing or invalid CSRF token.",
        )
    return principal


def create_user_session(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    settings: Settings,
    ip_address: str,
    user_agent: str,
) -> tuple[str, str, str]:
    """Create a session row and return (raw_session_token, csrf_token, expires_at_iso)."""
    raw_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(24)
    session_id_hash = hash_session_token(raw_token, settings.secret_key)
    now = datetime.now(UTC)
    expires_at = (now + timedelta(seconds=settings.session_ttl_seconds)).isoformat()

    conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now.isoformat(),))
    conn.execute(
        """
        INSERT INTO sessions (
            id, user_id, csrf_token, expires_at, created_at, last_seen_at, ip_address, user_agent
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id_hash,
            user_id,
            csrf_token,
            expires_at,
            now.isoformat(),
            now.isoformat(),
            ip_address,
            user_agent[:256],
        ),
    )
    return raw_token, csrf_token, expires_at
