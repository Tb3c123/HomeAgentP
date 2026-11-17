"""Read-only Script Registry API router.

Arbitrary script execution is strictly prohibited in HomeAgentP Phase 01.
"""

from __future__ import annotations

import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from homeagentp_core.auth.security import (
    AuthenticatedPrincipal,
    get_current_principal,
    get_settings,
)
from homeagentp_core.config import Settings
from homeagentp_core.db.connection import db_session
from homeagentp_core.modules.scripts.safe_reader import (
    PathSecurityError,
    read_allowlisted_text_file,
)

router = APIRouter(prefix="/api/v1/scripts", tags=["scripts"])

ReviewStatus = Literal["draft", "reviewed", "allowlisted", "revoked"]


class ScriptManifestOut(BaseModel):
    id: int
    slug: str
    name: str
    description: str
    category: str
    rel_path: str
    sha256: str
    review_status: ReviewStatus
    is_executable_allowed: bool
    execution_policy: str
    created_at: str
    updated_at: str


class ScriptDetailOut(ScriptManifestOut):
    content: str
    size_bytes: int
    checksum_verified: bool


def _row_to_manifest(row: sqlite3.Row) -> ScriptManifestOut:
    return ScriptManifestOut(
        id=int(row["id"]),
        slug=str(row["slug"]),
        name=str(row["name"]),
        description=str(row["description"]),
        category=str(row["category"]),
        rel_path=str(row["rel_path"]),
        sha256=str(row["sha256"]),
        review_status=row["review_status"],
        is_executable_allowed=bool(row["is_executable_allowed"]),
        execution_policy="read_only_phase_01",
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


@router.get("", response_model=list[ScriptManifestOut])
def list_scripts(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> list[ScriptManifestOut]:
    """List registered script manifests (read-only metadata)."""
    with db_session(settings.db_path) as conn:
        rows = conn.execute("SELECT * FROM script_manifests ORDER BY slug ASC").fetchall()
        return [_row_to_manifest(r) for r in rows]


@router.get("/preview-file")
def preview_allowlisted_script_file(
    rel_path: str = Query(..., description="Relative path inside allowlisted scripts directory"),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    """Read a file inside the allowlisted scripts directory with strict traversal/symlink denial."""
    try:
        safe_file = read_allowlisted_text_file(settings.scripts_dir, rel_path)
    except PathSecurityError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Requested script file does not exist.",
        ) from exc

    return {
        "rel_path": safe_file.rel_path,
        "sha256": safe_file.sha256,
        "size_bytes": safe_file.size_bytes,
        "execution_policy": "read_only_phase_01",
        "content": safe_file.content,
    }


@router.get("/{slug}", response_model=ScriptDetailOut)
def get_script_detail(
    slug: str,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> ScriptDetailOut:
    """Return script metadata and verified read-only source content."""
    with db_session(settings.db_path) as conn:
        row = conn.execute(
            "SELECT * FROM script_manifests WHERE slug = ?",
            (slug.strip(),),
        ).fetchone()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Script '{slug}' not found.",
            )
        manifest = _row_to_manifest(row)

    try:
        safe_file = read_allowlisted_text_file(
            settings.scripts_dir,
            manifest.rel_path,
            expected_sha256=manifest.sha256,
        )
    except PathSecurityError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Script file '{manifest.rel_path}' is missing on disk.",
        ) from exc

    return ScriptDetailOut(
        **manifest.model_dump(),
        content=safe_file.content,
        size_bytes=safe_file.size_bytes,
        checksum_verified=True,
    )
