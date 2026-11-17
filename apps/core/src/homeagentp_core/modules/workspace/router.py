"""FastAPI router for Phase 04 Gate A (Task Briefs & Workspace Artifacts)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, status

from homeagentp_core.auth.security import (
    AuthenticatedPrincipal,
    get_current_principal,
    get_settings,
)
from homeagentp_core.config import Settings
from homeagentp_core.db.connection import db_session
from homeagentp_core.modules.workspace.artifacts import (
    get_workspace_artifact_detail,
    list_artifact_versions,
    list_workspace_artifacts,
    register_workspace_artifact,
)
from homeagentp_core.modules.workspace.briefs import (
    create_task_brief,
    export_task_brief,
    list_task_briefs,
)
from homeagentp_core.modules.workspace.provenance import (
    create_provenance_link,
    list_provenance_links,
    update_provenance_link,
)
from homeagentp_core.modules.workspace.schemas import (
    ArtifactKind,
    ArtifactSourceType,
    GitProvenanceCreate,
    GitProvenanceOut,
    GitProvenanceUpdate,
    ProvenanceEntityType,
    TaskBriefCreate,
    TaskBriefExportOut,
    TaskBriefOut,
    WorkspaceArtifactCreate,
    WorkspaceArtifactDetailOut,
    WorkspaceArtifactOut,
)
from homeagentp_core.modules.workspace.security import require_workspace_owner

router = APIRouter(prefix="/api/v1/workspace", tags=["workspace"])


@router.get("/tasks/{task_id}/briefs", response_model=list[TaskBriefOut])
def get_task_briefs_endpoint(
    task_id: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> list[TaskBriefOut]:
    with db_session(settings.db_path) as conn:
        return list_task_briefs(conn, task_id)


@router.post(
    "/tasks/{task_id}/briefs",
    response_model=TaskBriefOut,
    status_code=status.HTTP_201_CREATED,
)
def create_task_brief_endpoint(
    task_id: int,
    payload: TaskBriefCreate,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_workspace_owner),
    settings: Settings = Depends(get_settings),
) -> TaskBriefOut:
    client_ip = request.client.host if request.client else "unknown"
    with db_session(settings.db_path) as conn:
        return create_task_brief(
            conn,
            task_id=task_id,
            payload=payload,
            actor=principal.username,
            ip_address=client_ip,
        )


@router.get(
    "/tasks/{task_id}/briefs/{version}/export",
    response_model=TaskBriefExportOut,
)
def export_task_brief_endpoint(
    task_id: int,
    version: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> TaskBriefExportOut:
    with db_session(settings.db_path) as conn:
        return export_task_brief(conn, task_id=task_id, version=version)


@router.get("/artifacts", response_model=list[WorkspaceArtifactOut])
def list_workspace_artifacts_endpoint(
    kind: ArtifactKind | None = Query(default=None),
    source_type: ArtifactSourceType | None = Query(default=None),
    project_id: int | None = Query(default=None),
    task_id: int | None = Query(default=None),
    tag: str | None = Query(default=None, max_length=64),
    q: str | None = Query(default=None, max_length=120),
    include_history: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=10000),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> list[WorkspaceArtifactOut]:
    with db_session(settings.db_path) as conn:
        return list_workspace_artifacts(
            conn,
            kind=kind,
            source_type=source_type,
            project_id=project_id,
            task_id=task_id,
            tag=tag,
            q=q,
            include_history=include_history,
            limit=limit,
            offset=offset,
        )


@router.post(
    "/artifacts",
    response_model=WorkspaceArtifactOut,
    status_code=status.HTTP_201_CREATED,
)
def register_workspace_artifact_endpoint(
    payload: WorkspaceArtifactCreate,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_workspace_owner),
    settings: Settings = Depends(get_settings),
) -> WorkspaceArtifactOut:
    client_ip = request.client.host if request.client else "unknown"
    with db_session(settings.db_path) as conn:
        return register_workspace_artifact(
            conn,
            settings,
            payload=payload,
            actor=principal.username,
            ip_address=client_ip,
        )


@router.get("/artifacts/{slug}/versions", response_model=list[WorkspaceArtifactOut])
def list_workspace_artifact_versions_endpoint(
    slug: str,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> list[WorkspaceArtifactOut]:
    with db_session(settings.db_path) as conn:
        return list_artifact_versions(conn, slug)


@router.get("/artifacts/{slug}", response_model=WorkspaceArtifactDetailOut)
def get_workspace_artifact_detail_endpoint(
    slug: str,
    revision: int | None = Query(default=None, ge=1),
    version: str | None = Query(default=None, max_length=32),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> WorkspaceArtifactDetailOut:
    with db_session(settings.db_path) as conn:
        return get_workspace_artifact_detail(
            conn,
            settings,
            slug=slug,
            revision=revision,
            version=version,
        )


@router.get("/provenance", response_model=list[GitProvenanceOut])
def list_provenance_endpoint(
    entity_type: ProvenanceEntityType | None = Query(default=None),
    entity_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=10000),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> list[GitProvenanceOut]:
    with db_session(settings.db_path) as conn:
        return list_provenance_links(
            conn,
            entity_type=entity_type,
            entity_id=entity_id,
            limit=limit,
            offset=offset,
        )


@router.post(
    "/provenance",
    response_model=GitProvenanceOut,
    status_code=status.HTTP_201_CREATED,
)
def create_provenance_endpoint(
    payload: GitProvenanceCreate,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_workspace_owner),
    settings: Settings = Depends(get_settings),
) -> GitProvenanceOut:
    client_ip = request.client.host if request.client else "unknown"
    with db_session(settings.db_path) as conn:
        return create_provenance_link(
            conn,
            payload=payload,
            actor=principal.username,
            ip_address=client_ip,
        )


@router.patch("/provenance/{link_id}", response_model=GitProvenanceOut)
def update_provenance_endpoint(
    link_id: int,
    payload: GitProvenanceUpdate,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_workspace_owner),
    settings: Settings = Depends(get_settings),
) -> GitProvenanceOut:
    client_ip = request.client.host if request.client else "unknown"
    with db_session(settings.db_path) as conn:
        return update_provenance_link(
            conn,
            link_id=link_id,
            payload=payload,
            actor=principal.username,
            ip_address=client_ip,
        )
