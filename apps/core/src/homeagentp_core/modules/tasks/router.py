"""Projects, Tasks, and Task Attempts API router."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from homeagentp_core.auth.security import (
    AuthenticatedPrincipal,
    get_current_principal,
    get_settings,
    record_audit_log,
    require_csrf,
)
from homeagentp_core.config import Settings
from homeagentp_core.db.connection import db_session
from homeagentp_core.modules.tasks.schemas import (
    DomainCategory,
    ProjectCreate,
    ProjectOut,
    TaskAttemptCreate,
    TaskAttemptOut,
    TaskCreate,
    TaskOut,
    TaskPriority,
    TaskStatus,
    TaskUpdate,
)

router = APIRouter(prefix="/api/v1", tags=["tasks"])


def _row_to_project(row: sqlite3.Row) -> ProjectOut:
    return ProjectOut(
        id=int(row["id"]),
        slug=str(row["slug"]),
        name=str(row["name"]),
        category=row["category"],
        description=str(row["description"]),
        repo_url=str(row["repo_url"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _row_to_attempt(row: sqlite3.Row) -> TaskAttemptOut:
    return TaskAttemptOut(
        id=int(row["id"]),
        task_id=int(row["task_id"]),
        attempt_number=int(row["attempt_number"]),
        executor_type=row["executor_type"],
        status=row["status"],
        summary=str(row["summary"]),
        artifact_rel_path=str(row["artifact_rel_path"]),
        created_at=str(row["created_at"]),
        finished_at=str(row["finished_at"]) if row["finished_at"] is not None else None,
    )


def _fetch_task_with_attempts(conn: sqlite3.Connection, task_id: int) -> TaskOut:
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
    attempt_rows = conn.execute(
        "SELECT * FROM task_attempts WHERE task_id = ? ORDER BY attempt_number ASC",
        (task_id,),
    ).fetchall()
    return TaskOut(
        id=int(row["id"]),
        project_id=int(row["project_id"]) if row["project_id"] is not None else None,
        title=str(row["title"]),
        description=str(row["description"]),
        category=row["category"],
        status=row["status"],
        priority=row["priority"],
        task_brief_md=str(row["task_brief_md"]),
        git_branch=str(row["git_branch"]),
        pr_url=str(row["pr_url"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        attempts=[_row_to_attempt(a) for a in attempt_rows],
    )


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> list[ProjectOut]:
    with db_session(settings.db_path) as conn:
        rows = conn.execute("SELECT * FROM projects ORDER BY id ASC").fetchall()
        return [_row_to_project(r) for r in rows]


@router.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_csrf),
    settings: Settings = Depends(get_settings),
) -> ProjectOut:
    now_iso = datetime.now(UTC).isoformat()
    client_ip = request.client.host if request.client else "unknown"
    with db_session(settings.db_path) as conn:
        existing = conn.execute(
            "SELECT id FROM projects WHERE slug = ?", (payload.slug,)
        ).fetchone()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Project with slug '{payload.slug}' already exists.",
            )
        cursor = conn.execute(
            """
            INSERT INTO projects (
                slug, name, category, description, repo_url, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.slug,
                payload.name.strip(),
                payload.category,
                payload.description.strip(),
                payload.repo_url.strip(),
                now_iso,
                now_iso,
            ),
        )
        project_id = int(cursor.lastrowid or 0)
        record_audit_log(
            conn,
            actor=principal.username,
            action="project.create",
            target_type="project",
            target_id=str(project_id),
            details={"slug": payload.slug, "category": payload.category},
            ip_address=client_ip,
        )
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return _row_to_project(row)


@router.get("/tasks", response_model=list[TaskOut])
def list_tasks(
    status_filter: TaskStatus | None = Query(default=None, alias="status"),
    category: DomainCategory | None = Query(default=None),
    priority: TaskPriority | None = Query(default=None),
    project_id: int | None = Query(default=None),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> list[TaskOut]:
    clauses: list[str] = []
    params: list[object] = []
    if status_filter is not None:
        clauses.append("status = ?")
        params.append(status_filter)
    if category is not None:
        clauses.append("category = ?")
        params.append(category)
    if priority is not None:
        clauses.append("priority = ?")
        params.append(priority)
    if project_id is not None:
        clauses.append("project_id = ?")
        params.append(project_id)

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with db_session(settings.db_path) as conn:
        rows = conn.execute(
            f"SELECT id FROM tasks {where_sql} ORDER BY id DESC",  # noqa: S608
            tuple(params),
        ).fetchall()
        return [_fetch_task_with_attempts(conn, int(r["id"])) for r in rows]


@router.post("/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_csrf),
    settings: Settings = Depends(get_settings),
) -> TaskOut:
    now_iso = datetime.now(UTC).isoformat()
    client_ip = request.client.host if request.client else "unknown"
    with db_session(settings.db_path) as conn:
        if payload.project_id is not None:
            proj = conn.execute(
                "SELECT id FROM projects WHERE id = ?", (payload.project_id,)
            ).fetchone()
            if proj is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Project {payload.project_id} not found.",
                )
        cursor = conn.execute(
            """
            INSERT INTO tasks (
                project_id, title, description, category, status, priority,
                task_brief_md, git_branch, pr_url, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.project_id,
                payload.title.strip(),
                payload.description.strip(),
                payload.category,
                payload.status,
                payload.priority,
                payload.task_brief_md.strip(),
                payload.git_branch.strip(),
                payload.pr_url.strip(),
                now_iso,
                now_iso,
            ),
        )
        task_id = int(cursor.lastrowid or 0)
        record_audit_log(
            conn,
            actor=principal.username,
            action="task.create",
            target_type="task",
            target_id=str(task_id),
            details={
                "title": payload.title.strip(),
                "category": payload.category,
                "status": payload.status,
            },
            ip_address=client_ip,
        )
        return _fetch_task_with_attempts(conn, task_id)


@router.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(
    task_id: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> TaskOut:
    with db_session(settings.db_path) as conn:
        return _fetch_task_with_attempts(conn, task_id)


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def update_task(
    task_id: int,
    payload: TaskUpdate,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_csrf),
    settings: Settings = Depends(get_settings),
) -> TaskOut:
    now_iso = datetime.now(UTC).isoformat()
    client_ip = request.client.host if request.client else "unknown"
    updates = payload.model_dump(exclude_unset=True)

    with db_session(settings.db_path) as conn:
        existing = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")

        if updates:
            set_fragments: list[str] = []
            params: list[object] = []
            for field_name, value in updates.items():
                set_fragments.append(f"{field_name} = ?")
                params.append(value.strip() if isinstance(value, str) else value)
            set_fragments.append("updated_at = ?")
            params.append(now_iso)
            params.append(task_id)

            conn.execute(
                f"UPDATE tasks SET {', '.join(set_fragments)} WHERE id = ?",  # noqa: S608
                tuple(params),
            )
            record_audit_log(
                conn,
                actor=principal.username,
                action="task.update",
                target_type="task",
                target_id=str(task_id),
                details={"updated_fields": list(updates.keys())},
                ip_address=client_ip,
            )

        return _fetch_task_with_attempts(conn, task_id)


@router.post(
    "/tasks/{task_id}/attempts",
    response_model=TaskAttemptOut,
    status_code=status.HTTP_201_CREATED,
)
def create_task_attempt(
    task_id: int,
    payload: TaskAttemptCreate,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_csrf),
    settings: Settings = Depends(get_settings),
) -> TaskAttemptOut:
    now_iso = datetime.now(UTC).isoformat()
    client_ip = request.client.host if request.client else "unknown"
    finished_at = now_iso if payload.status in {"succeeded", "failed", "cancelled"} else None

    with db_session(settings.db_path) as conn:
        task_row = conn.execute("SELECT id FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if task_row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")

        max_num_row = conn.execute(
            "SELECT COALESCE(MAX(attempt_number), 0) AS max_num "
            "FROM task_attempts WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        next_attempt = int(max_num_row["max_num"]) + 1

        cursor = conn.execute(
            """
            INSERT INTO task_attempts (
                task_id, attempt_number, executor_type, status,
                summary, artifact_rel_path, created_at, finished_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                next_attempt,
                payload.executor_type,
                payload.status,
                payload.summary.strip(),
                payload.artifact_rel_path.strip(),
                now_iso,
                finished_at,
            ),
        )
        attempt_id = int(cursor.lastrowid or 0)
        record_audit_log(
            conn,
            actor=principal.username,
            action="task.attempt_recorded",
            target_type="task",
            target_id=str(task_id),
            details={
                "attempt_number": next_attempt,
                "executor_type": payload.executor_type,
                "status": payload.status,
            },
            ip_address=client_ip,
        )
        row = conn.execute("SELECT * FROM task_attempts WHERE id = ?", (attempt_id,)).fetchone()
        return _row_to_attempt(row)
