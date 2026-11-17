"""Versioned Task Brief persistence and deterministic Antigravity handoff formatter."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from fastapi import HTTPException, status

from homeagentp_core.auth.security import record_audit_log
from homeagentp_core.modules.workspace.schemas import (
    TaskBriefCreate,
    TaskBriefExportOut,
    TaskBriefOut,
)
from homeagentp_core.modules.workspace.security import assert_no_secrets

MAX_RENDERED_BRIEF_CHARS = 24_000


def render_handoff_brief_text(
    *,
    task_id: int,
    task_title: str,
    task_category: str,
    version: int,
    payload: TaskBriefCreate,
) -> str:
    """Render a deterministic plain-text brief for manual copy into official Antigravity."""
    refs_block = (
        "\n".join(f"- {ref.strip()}" for ref in payload.input_references if ref.strip())
        or "- (none)"
    )
    checks_block = (
        "\n".join(f"- [ ] {chk.strip()}" for chk in payload.acceptance_checks if chk.strip())
        or "- [ ] (none)"
    )
    lines = [
        f"HomeAgentP Task Brief (Task #{task_id} v{version})",
        f"Title: {task_title}",
        f"Category: {task_category}",
        f"Human Status: {payload.human_status}",
        "",
        "## Purpose",
        payload.purpose.strip(),
        "",
        "## Scope",
        payload.scope.strip() or "(not specified)",
        "",
        "## Excluded Scope",
        payload.excluded_scope.strip() or "(not specified)",
        "",
        "## Input References",
        refs_block,
        "",
        "## Acceptance Checks",
        checks_block,
        "",
        "## Security Constraints",
        payload.security_constraints.strip() or "(default HomeAgentP B+ constraints)",
        "",
        "## Rollback Plan",
        payload.rollback_plan.strip() or "(not specified)",
    ]
    rendered = "\n".join(lines).strip()
    if len(rendered) > MAX_RENDERED_BRIEF_CHARS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Rendered task brief exceeds maximum allowed length.",
        )
    return rendered


def _row_to_brief(row: sqlite3.Row) -> TaskBriefOut:
    return TaskBriefOut(
        id=int(row["id"]),
        task_id=int(row["task_id"]),
        version=int(row["version"]),
        purpose=str(row["purpose"]),
        scope=str(row["scope"]),
        excluded_scope=str(row["excluded_scope"]),
        input_references=list(json.loads(str(row["input_references_json"]))),
        acceptance_checks=list(json.loads(str(row["acceptance_checks_json"]))),
        security_constraints=str(row["security_constraints"]),
        rollback_plan=str(row["rollback_plan"]),
        human_status=row["human_status"],
        rendered_text=str(row["rendered_text"]),
        created_by=str(row["created_by"]),
        created_at=str(row["created_at"]),
    )


def list_task_briefs(conn: sqlite3.Connection, task_id: int) -> list[TaskBriefOut]:
    """List all immutable brief versions for a task, newest first."""
    task_row = conn.execute("SELECT id FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if task_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
    rows = conn.execute(
        "SELECT * FROM task_briefs WHERE task_id = ? ORDER BY version DESC",
        (task_id,),
    ).fetchall()
    return [_row_to_brief(r) for r in rows]


def create_task_brief(
    conn: sqlite3.Connection,
    *,
    task_id: int,
    payload: TaskBriefCreate,
    actor: str,
    ip_address: str,
) -> TaskBriefOut:
    """Atomically allocate the next immutable Task Brief version using BEGIN IMMEDIATE."""
    assert_no_secrets(
        {
            "purpose": payload.purpose,
            "scope": payload.scope,
            "excluded_scope": payload.excluded_scope,
            "input_references": payload.input_references,
            "acceptance_checks": payload.acceptance_checks,
            "security_constraints": payload.security_constraints,
            "rollback_plan": payload.rollback_plan,
        }
    )

    clean_refs = [r.strip() for r in payload.input_references if r.strip()]
    clean_checks = [c.strip() for c in payload.acceptance_checks if c.strip()]
    now_iso = datetime.now(UTC).isoformat()

    conn.execute("BEGIN IMMEDIATE;")
    task_row = conn.execute(
        "SELECT id, title, category FROM tasks WHERE id = ?",
        (task_id,),
    ).fetchone()
    if task_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")

    max_row = conn.execute(
        "SELECT COALESCE(MAX(version), 0) AS max_ver FROM task_briefs WHERE task_id = ?",
        (task_id,),
    ).fetchone()
    current_max = int(max_row["max_ver"]) if max_row is not None else 0

    if (
        payload.expected_latest_version is not None
        and payload.expected_latest_version != current_max
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Task brief version conflict: expected latest version "
                f"{payload.expected_latest_version}, found {current_max}."
            ),
        )

    next_version = current_max + 1
    rendered_text = render_handoff_brief_text(
        task_id=task_id,
        task_title=str(task_row["title"]),
        task_category=str(task_row["category"]),
        version=next_version,
        payload=payload,
    )
    assert_no_secrets({"rendered_text": rendered_text})

    try:
        cursor = conn.execute(
            """
            INSERT INTO task_briefs (
                task_id, version, purpose, scope, excluded_scope,
                input_references_json, acceptance_checks_json,
                security_constraints, rollback_plan, human_status,
                rendered_text, created_by, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                next_version,
                payload.purpose.strip(),
                payload.scope.strip(),
                payload.excluded_scope.strip(),
                json.dumps(clean_refs, ensure_ascii=False),
                json.dumps(clean_checks, ensure_ascii=False),
                payload.security_constraints.strip(),
                payload.rollback_plan.strip(),
                payload.human_status,
                rendered_text,
                actor,
                now_iso,
            ),
        )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Task brief version allocation conflicted with a concurrent update.",
        ) from exc

    brief_id = int(cursor.lastrowid or 0)
    record_audit_log(
        conn,
        actor=actor,
        action="workspace.brief.create",
        target_type="task_brief",
        target_id=f"{task_id}:v{next_version}",
        details={
            "task_id": task_id,
            "version": next_version,
            "human_status": payload.human_status,
        },
        ip_address=ip_address,
    )
    row = conn.execute("SELECT * FROM task_briefs WHERE id = ?", (brief_id,)).fetchone()
    assert row is not None
    return _row_to_brief(row)


def export_task_brief(
    conn: sqlite3.Connection,
    *,
    task_id: int,
    version: int,
) -> TaskBriefExportOut:
    """Return deterministic plain-text handoff brief for manual copy into Antigravity."""
    row = conn.execute(
        "SELECT task_id, version, human_status, rendered_text "
        "FROM task_briefs WHERE task_id = ? AND version = ?",
        (task_id, version),
    ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task brief version not found.",
        )
    return TaskBriefExportOut(
        task_id=int(row["task_id"]),
        version=int(row["version"]),
        human_status=row["human_status"],
        rendered_text=str(row["rendered_text"]),
    )
