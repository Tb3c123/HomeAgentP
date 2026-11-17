"""Pydantic schemas for Phase 04 Task Briefs and Artifacts/Knowledge Metadata."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

HumanBriefStatus = Literal[
    "draft",
    "ready_for_handoff",
    "handed_off",
    "approved",
    "archived",
]

ArtifactKind = Literal["artifact", "knowledge", "plan", "runbook"]
ArtifactSourceType = Literal[
    "allowlisted_report",
    "allowlisted_script",
    "git_reference",
    "note",
]


class TaskBriefCreate(BaseModel):
    purpose: str = Field(..., min_length=3, max_length=2000)
    scope: str = Field(default="", max_length=4000)
    excluded_scope: str = Field(default="", max_length=4000)
    input_references: list[str] = Field(default_factory=list, max_length=20)
    acceptance_checks: list[str] = Field(default_factory=list, max_length=30)
    security_constraints: str = Field(default="", max_length=4000)
    rollback_plan: str = Field(default="", max_length=4000)
    human_status: HumanBriefStatus = "draft"
    expected_latest_version: int | None = Field(default=None, ge=0)


class TaskBriefOut(BaseModel):
    id: int
    task_id: int
    version: int
    purpose: str
    scope: str
    excluded_scope: str
    input_references: list[str]
    acceptance_checks: list[str]
    security_constraints: str
    rollback_plan: str
    human_status: HumanBriefStatus
    rendered_text: str
    created_by: str
    created_at: str


class TaskBriefExportOut(BaseModel):
    task_id: int
    version: int
    human_status: HumanBriefStatus
    handoff_mode: Literal["manual_copy_only"] = "manual_copy_only"
    rendered_text: str


class WorkspaceArtifactCreate(BaseModel):
    slug: str = Field(..., min_length=2, max_length=80, pattern=r"^[a-z0-9][a-z0-9-]*$")
    version: str = Field(
        default="1.0.0",
        min_length=1,
        max_length=32,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    )
    title: str = Field(..., min_length=2, max_length=200)
    kind: ArtifactKind = "artifact"
    source_type: ArtifactSourceType = "note"
    rel_path: str = Field(default="", max_length=255)
    expected_sha256: str = Field(default="", max_length=64)
    git_url: str = Field(default="", max_length=255)
    summary: str = Field(default="", max_length=2000)
    tags: list[str] = Field(default_factory=list, max_length=16)
    project_id: int | None = None
    task_id: int | None = None
    expected_latest_revision: int | None = Field(default=None, ge=0)


class WorkspaceArtifactOut(BaseModel):
    id: int
    slug: str
    revision: int
    version: str
    title: str
    kind: ArtifactKind
    source_type: ArtifactSourceType
    rel_path: str
    sha256: str
    git_url: str
    summary: str
    tags: list[str]
    project_id: int | None
    task_id: int | None
    created_by: str
    created_at: str


class WorkspaceArtifactDetailOut(WorkspaceArtifactOut):
    content: str | None = None
    size_bytes: int | None = None
    checksum_verified: bool = False
