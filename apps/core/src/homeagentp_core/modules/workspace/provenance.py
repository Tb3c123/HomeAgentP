"""Git Provenance links CRUD & validation for Phase 04 (P04-F04)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from fastapi import HTTPException, status

from homeagentp_core.auth.security import record_audit_log
from homeagentp_core.modules.workspace.schemas import (
    GitProvenanceCreate,
    GitProvenanceOut,
    GitProvenanceUpdate,
    ProvenanceEntityType,
)
from homeagentp_core.modules.workspace.security import (
    assert_no_secrets,
    validate_github_https_url,
)


def _row_to_provenance(row: sqlite3.Row) -> GitProvenanceOut:
    return GitProvenanceOut(
        id=int(row["id"]),
        entity_type=row["entity_type"],
        entity_id=int(row["entity_id"]),
        repo_url=str(row["repo_url"]),
        branch=str(row["branch"]),
        commit_sha=str(row["commit_sha"]),
        pr_url=str(row["pr_url"]),
        review_status=row["review_status"],
        ci_status=row["ci_status"],
        ci_url=str(row["ci_url"]),
        verification_source=row["verification_source"],
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _assert_target_entity_exists(
    conn: sqlite3.Connection,
    entity_type: ProvenanceEntityType,
    entity_id: int,
) -> None:
    if entity_type == "task":
        row = conn.execute("SELECT id FROM tasks WHERE id = ?", (entity_id,)).fetchone()
    else:
        row = conn.execute(
            "SELECT id FROM workspace_artifacts WHERE id = ?", (entity_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Referenced {entity_type} ({entity_id}) not found.",
        )


def list_provenance_links(
    conn: sqlite3.Connection,
    *,
    entity_type: ProvenanceEntityType | None = None,
    entity_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[GitProvenanceOut]:
    rows = conn.execute(
        """
        SELECT * FROM git_provenance_links
        WHERE (? IS NULL OR entity_type = ?)
          AND (? IS NULL OR entity_id = ?)
        ORDER BY updated_at DESC, id DESC
        LIMIT ? OFFSET ?
        """,
        (entity_type, entity_type, entity_id, entity_id, limit, offset),
    ).fetchall()
    return [_row_to_provenance(r) for r in rows]


def create_provenance_link(
    conn: sqlite3.Connection,
    *,
    payload: GitProvenanceCreate,
    actor: str,
    ip_address: str,
) -> GitProvenanceOut:
    assert_no_secrets(
        {
            "repo_url": payload.repo_url,
            "branch": payload.branch,
            "pr_url": payload.pr_url,
            "ci_url": payload.ci_url,
        }
    )
    clean_repo_url = validate_github_https_url(payload.repo_url, field_name="repo_url")
    clean_pr_url = (
        validate_github_https_url(payload.pr_url, field_name="pr_url")
        if payload.pr_url.strip()
        else ""
    )
    clean_ci_url = (
        validate_github_https_url(payload.ci_url, field_name="ci_url")
        if payload.ci_url.strip()
        else ""
    )

    _assert_target_entity_exists(conn, payload.entity_type, payload.entity_id)
    now_iso = datetime.now(UTC).isoformat()

    cursor = conn.execute(
        """
        INSERT INTO git_provenance_links (
            entity_type, entity_id, repo_url, branch, commit_sha,
            pr_url, review_status, ci_status, ci_url,
            verification_source, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'manual_unverified', ?, ?)
        """,
        (
            payload.entity_type,
            payload.entity_id,
            clean_repo_url,
            payload.branch.strip(),
            payload.commit_sha.strip().lower(),
            clean_pr_url,
            payload.review_status,
            payload.ci_status,
            clean_ci_url,
            now_iso,
            now_iso,
        ),
    )
    link_id = int(cursor.lastrowid or 0)
    record_audit_log(
        conn,
        actor=actor,
        action="workspace.provenance.create",
        target_type="git_provenance",
        target_id=str(link_id),
        details={
            "entity_type": payload.entity_type,
            "entity_id": payload.entity_id,
            "verification_source": "manual_unverified",
        },
        ip_address=ip_address,
    )
    row = conn.execute("SELECT * FROM git_provenance_links WHERE id = ?", (link_id,)).fetchone()
    assert row is not None
    return _row_to_provenance(row)


def update_provenance_link(
    conn: sqlite3.Connection,
    *,
    link_id: int,
    payload: GitProvenanceUpdate,
    actor: str,
    ip_address: str,
) -> GitProvenanceOut:
    existing = conn.execute(
        "SELECT * FROM git_provenance_links WHERE id = ?", (link_id,)
    ).fetchone()
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Git provenance link not found.",
        )

    assert_no_secrets(
        {
            "branch": payload.branch or "",
            "pr_url": payload.pr_url or "",
            "ci_url": payload.ci_url or "",
        }
    )

    branch = payload.branch.strip() if payload.branch is not None else str(existing["branch"])
    commit_sha = (
        payload.commit_sha.strip().lower()
        if payload.commit_sha is not None
        else str(existing["commit_sha"])
    )
    if payload.pr_url is not None:
        pr_url = (
            validate_github_https_url(payload.pr_url, field_name="pr_url")
            if payload.pr_url.strip()
            else ""
        )
    else:
        pr_url = str(existing["pr_url"])
    if payload.ci_url is not None:
        ci_url = (
            validate_github_https_url(payload.ci_url, field_name="ci_url")
            if payload.ci_url.strip()
            else ""
        )
    else:
        ci_url = str(existing["ci_url"])

    review_status = (
        payload.review_status if payload.review_status is not None else existing["review_status"]
    )
    ci_status = payload.ci_status if payload.ci_status is not None else existing["ci_status"]
    now_iso = datetime.now(UTC).isoformat()

    conn.execute(
        """
        UPDATE git_provenance_links
        SET branch = ?, commit_sha = ?, pr_url = ?, review_status = ?,
            ci_status = ?, ci_url = ?, verification_source = 'manual_unverified',
            updated_at = ?
        WHERE id = ?
        """,
        (branch, commit_sha, pr_url, review_status, ci_status, ci_url, now_iso, link_id),
    )
    record_audit_log(
        conn,
        actor=actor,
        action="workspace.provenance.update",
        target_type="git_provenance",
        target_id=str(link_id),
        details={
            "review_status": review_status,
            "ci_status": ci_status,
            "verification_source": "manual_unverified",
        },
        ip_address=ip_address,
    )
    row = conn.execute("SELECT * FROM git_provenance_links WHERE id = ?", (link_id,)).fetchone()
    assert row is not None
    return _row_to_provenance(row)
