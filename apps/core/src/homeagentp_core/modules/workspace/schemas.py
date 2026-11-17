"""Pydantic schemas for Phase 04 Task Briefs and Artifacts/Knowledge Metadata."""

from __future__ import annotations

import json
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

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

InputReferenceItem = Annotated[str, Field(min_length=1, max_length=255)]
AcceptanceCheckItem = Annotated[str, Field(min_length=1, max_length=500)]
ArtifactTagItem = Annotated[str, Field(min_length=1, max_length=48)]

MAX_INPUT_REFERENCES_JSON_BYTES = 4096
MAX_ACCEPTANCE_CHECKS_JSON_BYTES = 8192
MAX_TAGS_JSON_BYTES = 1024


class TaskBriefCreate(BaseModel):
    purpose: str = Field(..., min_length=3, max_length=2000)
    scope: str = Field(default="", max_length=4000)
    excluded_scope: str = Field(default="", max_length=4000)
    input_references: list[InputReferenceItem] = Field(default_factory=list, max_length=20)
    acceptance_checks: list[AcceptanceCheckItem] = Field(default_factory=list, max_length=30)
    security_constraints: str = Field(default="", max_length=4000)
    rollback_plan: str = Field(default="", max_length=4000)
    human_status: HumanBriefStatus = "draft"
    expected_latest_version: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _check_serialized_bounds(self) -> TaskBriefCreate:
        refs_bytes = len(json.dumps(self.input_references, ensure_ascii=False).encode("utf-8"))
        if refs_bytes > MAX_INPUT_REFERENCES_JSON_BYTES:
            raise ValueError(
                f"Serialized input_references exceeds {MAX_INPUT_REFERENCES_JSON_BYTES} bytes."
            )
        checks_bytes = len(json.dumps(self.acceptance_checks, ensure_ascii=False).encode("utf-8"))
        if checks_bytes > MAX_ACCEPTANCE_CHECKS_JSON_BYTES:
            raise ValueError(
                f"Serialized acceptance_checks exceeds {MAX_ACCEPTANCE_CHECKS_JSON_BYTES} bytes."
            )
        return self


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
    tags: list[ArtifactTagItem] = Field(default_factory=list, max_length=16)
    project_id: int | None = None
    task_id: int | None = None
    expected_latest_revision: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _check_tags_serialized_size(self) -> WorkspaceArtifactCreate:
        tags_bytes = len(json.dumps(self.tags, ensure_ascii=False).encode("utf-8"))
        if tags_bytes > MAX_TAGS_JSON_BYTES:
            raise ValueError(f"Serialized tags exceeds {MAX_TAGS_JSON_BYTES} bytes.")
        return self


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


ProvenanceEntityType = Literal["task", "artifact"]
ProvenanceReviewStatus = Literal["none", "pending", "approved", "changes_requested"]
ProvenanceCiStatus = Literal["unknown", "pending", "success", "failure"]
VerificationSource = Literal["manual_unverified", "external_ci_verified"]


class GitProvenanceCreate(BaseModel):
    entity_type: ProvenanceEntityType
    entity_id: int = Field(..., ge=1)
    repo_url: str = Field(..., min_length=19, max_length=255)
    branch: str = Field(default="", max_length=120)
    commit_sha: str = Field(default="", max_length=40, pattern=r"^$|^[0-9a-fA-F]{7,40}$")
    pr_url: str = Field(default="", max_length=255)
    review_status: ProvenanceReviewStatus = "none"
    ci_status: ProvenanceCiStatus = "unknown"
    ci_url: str = Field(default="", max_length=255)


class GitProvenanceUpdate(BaseModel):
    branch: str | None = Field(default=None, max_length=120)
    commit_sha: str | None = Field(default=None, max_length=40, pattern=r"^$|^[0-9a-fA-F]{7,40}$")
    pr_url: str | None = Field(default=None, max_length=255)
    review_status: ProvenanceReviewStatus | None = None
    ci_status: ProvenanceCiStatus | None = None
    ci_url: str | None = Field(default=None, max_length=255)


class GitProvenanceOut(BaseModel):
    id: int
    entity_type: ProvenanceEntityType
    entity_id: int
    repo_url: str
    branch: str
    commit_sha: str
    pr_url: str
    review_status: ProvenanceReviewStatus
    ci_status: ProvenanceCiStatus
    ci_url: str
    verification_source: VerificationSource
    created_at: str
    updated_at: str
