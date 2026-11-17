"""Immutable Workspace Artifacts & Knowledge metadata registry with safe_reader preview."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException, status

from homeagentp_core.auth.security import record_audit_log
from homeagentp_core.config import Settings
from homeagentp_core.modules.scripts.safe_reader import (
    PathSecurityError,
    read_allowlisted_text_file,
)
from homeagentp_core.modules.workspace.schemas import (
    ArtifactKind,
    ArtifactSourceType,
    WorkspaceArtifactCreate,
    WorkspaceArtifactDetailOut,
    WorkspaceArtifactOut,
)
from homeagentp_core.modules.workspace.security import (
    assert_no_secrets,
    validate_github_https_url,
    validate_relative_path_syntax,
)


def _allowlisted_root(settings: Settings, source_type: ArtifactSourceType) -> Path:
    if source_type == "allowlisted_report":
        return settings.reports_dir
    if source_type == "allowlisted_script":
        return settings.scripts_dir
    raise ValueError(f"Unsupported allowlisted source_type: {source_type}")


def _row_to_artifact(row: sqlite3.Row) -> WorkspaceArtifactOut:
    return WorkspaceArtifactOut(
        id=int(row["id"]),
        slug=str(row["slug"]),
        revision=int(row["revision"]),
        version=str(row["version"]),
        title=str(row["title"]),
        kind=row["kind"],
        source_type=row["source_type"],
        rel_path=str(row["rel_path"]),
        sha256=str(row["sha256"]),
        git_url=str(row["git_url"]),
        summary=str(row["summary"]),
        tags=list(json.loads(str(row["tags_json"]))),
        project_id=int(row["project_id"]) if row["project_id"] is not None else None,
        task_id=int(row["task_id"]) if row["task_id"] is not None else None,
        created_by=str(row["created_by"]),
        created_at=str(row["created_at"]),
    )


def register_workspace_artifact(
    conn: sqlite3.Connection,
    settings: Settings,
    *,
    payload: WorkspaceArtifactCreate,
    actor: str,
    ip_address: str,
) -> WorkspaceArtifactOut:
    """Register a new artifact or immutable revision with SHA-256 verification."""
    assert_no_secrets(
        {
            "title": payload.title,
            "summary": payload.summary,
            "tags": payload.tags,
            "rel_path": payload.rel_path,
            "git_url": payload.git_url,
        }
    )

    clean_rel_path = ""
    computed_sha256 = ""
    clean_git_url = ""

    if payload.source_type in ("allowlisted_report", "allowlisted_script"):
        clean_rel_path = validate_relative_path_syntax(payload.rel_path)
        root_dir = _allowlisted_root(settings, payload.source_type)
        expected_sha = payload.expected_sha256.strip().lower() or None
        try:
            safe_file = read_allowlisted_text_file(
                root_dir,
                clean_rel_path,
                expected_sha256=expected_sha,
            )
        except PathSecurityError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(exc),
            ) from exc
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Referenced allowlisted artifact file does not exist.",
            ) from exc
        clean_rel_path = safe_file.rel_path
        computed_sha256 = safe_file.sha256
    elif payload.source_type == "git_reference":
        clean_git_url = validate_github_https_url(payload.git_url, field_name="git_url")
    elif payload.git_url.strip():
        clean_git_url = validate_github_https_url(payload.git_url, field_name="git_url")

    clean_tags = [tag.strip() for tag in payload.tags if tag.strip()]
    now_iso = datetime.now(UTC).isoformat()

    conn.execute("BEGIN IMMEDIATE;")
    if payload.project_id is not None:
        proj = conn.execute(
            "SELECT id FROM projects WHERE id = ?", (payload.project_id,)
        ).fetchone()
        if proj is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Referenced project not found."
            )
    if payload.task_id is not None:
        task = conn.execute("SELECT id FROM tasks WHERE id = ?", (payload.task_id,)).fetchone()
        if task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Referenced task not found."
            )

    max_row = conn.execute(
        "SELECT COALESCE(MAX(revision), 0) AS max_rev FROM workspace_artifacts WHERE slug = ?",
        (payload.slug,),
    ).fetchone()
    current_max_rev = int(max_row["max_rev"]) if max_row is not None else 0

    if (
        payload.expected_latest_revision is not None
        and payload.expected_latest_revision != current_max_rev
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Artifact revision conflict for '{payload.slug}': expected "
                f"{payload.expected_latest_revision}, found {current_max_rev}."
            ),
        )

    next_revision = current_max_rev + 1
    try:
        cursor = conn.execute(
            """
            INSERT INTO workspace_artifacts (
                slug, revision, version, title, kind, source_type,
                rel_path, sha256, git_url, summary, tags_json,
                project_id, task_id, created_by, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.slug,
                next_revision,
                payload.version,
                payload.title.strip(),
                payload.kind,
                payload.source_type,
                clean_rel_path,
                computed_sha256,
                clean_git_url,
                payload.summary.strip(),
                json.dumps(clean_tags, ensure_ascii=False),
                payload.project_id,
                payload.task_id,
                actor,
                now_iso,
            ),
        )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Artifact '{payload.slug}' version '{payload.version}' already exists "
                "or conflicted with a concurrent registration."
            ),
        ) from exc

    artifact_id = int(cursor.lastrowid or 0)
    record_audit_log(
        conn,
        actor=actor,
        action="workspace.artifact.register",
        target_type="workspace_artifact",
        target_id=f"{payload.slug}@r{next_revision}",
        details={
            "slug": payload.slug,
            "revision": next_revision,
            "version": payload.version,
            "kind": payload.kind,
            "source_type": payload.source_type,
        },
        ip_address=ip_address,
    )
    row = conn.execute("SELECT * FROM workspace_artifacts WHERE id = ?", (artifact_id,)).fetchone()
    assert row is not None
    return _row_to_artifact(row)


def list_workspace_artifacts(
    conn: sqlite3.Connection,
    *,
    kind: ArtifactKind | None = None,
    source_type: ArtifactSourceType | None = None,
    project_id: int | None = None,
    task_id: int | None = None,
    tag: str | None = None,
    q: str | None = None,
    include_history: bool = False,
) -> list[WorkspaceArtifactOut]:
    """List workspace artifacts/knowledge with optional filters (latest revision by default)."""
    like_term = f"%{q.strip().lower()}%" if (q is not None and q.strip()) else None
    rows = conn.execute(
        """
        SELECT wa.*
        FROM workspace_artifacts wa
        WHERE (
            ? = 1
            OR wa.revision = (
                SELECT MAX(w2.revision) FROM workspace_artifacts w2 WHERE w2.slug = wa.slug
            )
        )
        AND (? IS NULL OR wa.kind = ?)
        AND (? IS NULL OR wa.source_type = ?)
        AND (? IS NULL OR wa.project_id = ?)
        AND (? IS NULL OR wa.task_id = ?)
        AND (
            ? IS NULL
            OR LOWER(wa.title) LIKE ?
            OR LOWER(wa.summary) LIKE ?
            OR LOWER(wa.slug) LIKE ?
        )
        ORDER BY wa.created_at DESC, wa.id DESC
        """,
        (
            1 if include_history else 0,
            kind,
            kind,
            source_type,
            source_type,
            project_id,
            project_id,
            task_id,
            task_id,
            like_term,
            like_term,
            like_term,
            like_term,
        ),
    ).fetchall()
    items = [_row_to_artifact(r) for r in rows]

    if tag is not None and tag.strip():
        target_tag = tag.strip().lower()
        items = [item for item in items if any(t.lower() == target_tag for t in item.tags)]
    return items


def list_artifact_versions(conn: sqlite3.Connection, slug: str) -> list[WorkspaceArtifactOut]:
    """List all immutable historical revisions for a given artifact slug."""
    rows = conn.execute(
        "SELECT * FROM workspace_artifacts WHERE slug = ? ORDER BY revision DESC",
        (slug.strip(),),
    ).fetchall()
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace artifact '{slug}' not found.",
        )
    return [_row_to_artifact(r) for r in rows]


def get_workspace_artifact_detail(
    conn: sqlite3.Connection,
    settings: Settings,
    *,
    slug: str,
    revision: int | None = None,
    version: str | None = None,
) -> WorkspaceArtifactDetailOut:
    """Return artifact metadata and verified read-only file preview when allowlisted."""
    clean_slug = slug.strip()
    if revision is not None:
        row = conn.execute(
            "SELECT * FROM workspace_artifacts WHERE slug = ? AND revision = ?",
            (clean_slug, revision),
        ).fetchone()
    elif version is not None and version.strip():
        row = conn.execute(
            "SELECT * FROM workspace_artifacts WHERE slug = ? AND version = ?",
            (clean_slug, version.strip()),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM workspace_artifacts WHERE slug = ? ORDER BY revision DESC LIMIT 1",
            (clean_slug,),
        ).fetchone()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace artifact '{clean_slug}' not found.",
        )

    artifact = _row_to_artifact(row)
    content: str | None = None
    size_bytes: int | None = None
    checksum_verified = False

    if artifact.source_type in ("allowlisted_report", "allowlisted_script"):
        root_dir = _allowlisted_root(settings, artifact.source_type)
        try:
            safe_file = read_allowlisted_text_file(
                root_dir,
                artifact.rel_path,
                expected_sha256=artifact.sha256 or None,
            )
        except PathSecurityError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(exc),
            ) from exc
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Referenced allowlisted artifact file is missing on disk.",
            ) from exc
        content = safe_file.content
        size_bytes = safe_file.size_bytes
        checksum_verified = True

    return WorkspaceArtifactDetailOut(
        **artifact.model_dump(),
        content=content,
        size_bytes=size_bytes,
        checksum_verified=checksum_verified,
    )
