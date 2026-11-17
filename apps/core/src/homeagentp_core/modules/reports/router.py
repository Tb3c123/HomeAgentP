"""Reports and Audit Logs API router."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

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

router = APIRouter(prefix="/api/v1", tags=["reports-audit"])


class ReportSummaryOut(BaseModel):
    id: int
    slug: str
    title: str
    category: str
    summary: str
    rel_path: str
    created_at: str


class ReportDetailOut(ReportSummaryOut):
    content: str
    sha256: str
    size_bytes: int


class AuditLogOut(BaseModel):
    id: int
    actor: str
    action: str
    target_type: str
    target_id: str
    details: dict[str, Any]
    ip_address: str
    created_at: str


def _row_to_report(row: sqlite3.Row) -> ReportSummaryOut:
    return ReportSummaryOut(
        id=int(row["id"]),
        slug=str(row["slug"]),
        title=str(row["title"]),
        category=str(row["category"]),
        summary=str(row["summary"]),
        rel_path=str(row["rel_path"]),
        created_at=str(row["created_at"]),
    )


@router.get("/reports", response_model=list[ReportSummaryOut])
def list_reports(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> list[ReportSummaryOut]:
    with db_session(settings.db_path) as conn:
        rows = conn.execute("SELECT * FROM reports ORDER BY id DESC").fetchall()
        return [_row_to_report(r) for r in rows]


@router.get("/reports/{slug}", response_model=ReportDetailOut)
def get_report_detail(
    slug: str,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> ReportDetailOut:
    with db_session(settings.db_path) as conn:
        row = conn.execute("SELECT * FROM reports WHERE slug = ?", (slug.strip(),)).fetchone()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Report '{slug}' not found.",
            )
        report = _row_to_report(row)

    try:
        safe_file = read_allowlisted_text_file(settings.reports_dir, report.rel_path)
    except PathSecurityError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report file '{report.rel_path}' is missing on disk.",
        ) from exc

    return ReportDetailOut(
        **report.model_dump(),
        content=safe_file.content,
        sha256=safe_file.sha256,
        size_bytes=safe_file.size_bytes,
    )


@router.get("/audit-logs", response_model=list[AuditLogOut])
def list_audit_logs(
    limit: int = Query(default=50, ge=1, le=200),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> list[AuditLogOut]:
    with db_session(settings.db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        result: list[AuditLogOut] = []
        for r in rows:
            try:
                details = json.loads(str(r["details_json"]))
            except json.JSONDecodeError:
                details = {}
            result.append(
                AuditLogOut(
                    id=int(r["id"]),
                    actor=str(r["actor"]),
                    action=str(r["action"]),
                    target_type=str(r["target_type"]),
                    target_id=str(r["target_id"]),
                    details=details if isinstance(details, dict) else {},
                    ip_address=str(r["ip_address"]),
                    created_at=str(r["created_at"]),
                )
            )
        return result
