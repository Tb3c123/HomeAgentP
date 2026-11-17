"""Authentication API endpoints: /api/v1/auth/login, /logout, /me."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from homeagentp_core.auth.security import (
    SESSION_COOKIE_NAME,
    AuthenticatedPrincipal,
    create_user_session,
    get_current_principal,
    get_settings,
    record_audit_log,
    require_csrf,
    verify_password,
)
from homeagentp_core.config import Settings
from homeagentp_core.db.connection import db_session

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=256)


class AuthUserResponse(BaseModel):
    username: str
    role: str
    csrf_token: str
    expires_at: str


@router.post("/login", response_model=AuthUserResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    settings: Settings = Depends(get_settings),
) -> AuthUserResponse:
    """Authenticate user credentials and issue an HttpOnly session cookie + CSRF token."""
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

    with db_session(settings.db_path) as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, role, is_active FROM users WHERE username = ?",
            (payload.username.strip(),),
        ).fetchone()

        if (
            row is None
            or int(row["is_active"]) != 1
            or not verify_password(payload.password, str(row["password_hash"]))
        ):
            record_audit_log(
                conn,
                actor=payload.username.strip() or "anonymous",
                action="auth.login_failed",
                target_type="session",
                details={"username": payload.username.strip()},
                ip_address=client_ip,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password.",
            )

        raw_token, csrf_token, expires_at = create_user_session(
            conn,
            user_id=int(row["id"]),
            settings=settings,
            ip_address=client_ip,
            user_agent=user_agent,
        )
        record_audit_log(
            conn,
            actor=str(row["username"]),
            action="auth.login_succeeded",
            target_type="session",
            details={"role": str(row["role"])},
            ip_address=client_ip,
        )

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=raw_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        max_age=settings.session_ttl_seconds,
        path="/",
    )
    return AuthUserResponse(
        username=str(row["username"]),
        role=str(row["role"]),
        csrf_token=csrf_token,
        expires_at=expires_at,
    )


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    principal: AuthenticatedPrincipal = Depends(require_csrf),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    """Invalidate current session and clear cookie."""
    client_ip = request.client.host if request.client else "unknown"
    with db_session(settings.db_path) as conn:
        conn.execute("DELETE FROM sessions WHERE id = ?", (principal.session_id_hash,))
        record_audit_log(
            conn,
            actor=principal.username,
            action="auth.logout",
            target_type="session",
            ip_address=client_ip,
        )

    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
    return {"status": "logged_out"}


@router.get("/me", response_model=AuthUserResponse)
def get_me(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> AuthUserResponse:
    """Return current authenticated user profile and active CSRF token."""
    return AuthUserResponse(
        username=principal.username,
        role=principal.role,
        csrf_token=principal.csrf_token,
        expires_at=principal.expires_at,
    )
