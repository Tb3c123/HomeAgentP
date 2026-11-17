"""Pydantic schemas for Projects, Tasks, and Task Attempts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

DomainCategory = Literal[
    "nas_guardian",
    "media",
    "downloads",
    "home_assistant",
    "monitoring",
    "telegram",
    "scripts",
    "tasks",
    "ai_workspace",
    "developer",
    "security",
]

TaskStatus = Literal["backlog", "ready", "in_progress", "review", "done", "blocked"]
TaskPriority = Literal["low", "medium", "high", "critical"]
AttemptExecutor = Literal["human", "antigravity_handoff", "scheduled_job"]
AttemptStatus = Literal["started", "succeeded", "failed", "cancelled", "not_tested"]


class ProjectCreate(BaseModel):
    slug: str = Field(..., min_length=2, max_length=64, pattern=r"^[a-z0-9-]+$")
    name: str = Field(..., min_length=2, max_length=120)
    category: DomainCategory
    description: str = Field(default="", max_length=1000)
    repo_url: str = Field(default="", max_length=255)


class ProjectOut(BaseModel):
    id: int
    slug: str
    name: str
    category: DomainCategory
    description: str
    repo_url: str
    created_at: str
    updated_at: str


class TaskCreate(BaseModel):
    project_id: int | None = None
    title: str = Field(..., min_length=2, max_length=200)
    description: str = Field(default="", max_length=4000)
    category: DomainCategory = "tasks"
    status: TaskStatus = "backlog"
    priority: TaskPriority = "medium"
    task_brief_md: str = Field(default="", max_length=10000)
    git_branch: str = Field(default="", max_length=120)
    pr_url: str = Field(default="", max_length=255)


class TaskUpdate(BaseModel):
    project_id: int | None = None
    title: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    category: DomainCategory | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    task_brief_md: str | None = Field(default=None, max_length=10000)
    git_branch: str | None = Field(default=None, max_length=120)
    pr_url: str | None = Field(default=None, max_length=255)


class TaskAttemptCreate(BaseModel):
    executor_type: AttemptExecutor = "antigravity_handoff"
    status: AttemptStatus = "started"
    summary: str = Field(default="", max_length=2000)
    artifact_rel_path: str = Field(default="", max_length=255)


class TaskAttemptOut(BaseModel):
    id: int
    task_id: int
    attempt_number: int
    executor_type: AttemptExecutor
    status: AttemptStatus
    summary: str
    artifact_rel_path: str
    created_at: str
    finished_at: str | None


class TaskOut(BaseModel):
    id: int
    project_id: int | None
    title: str
    description: str
    category: DomainCategory
    status: TaskStatus
    priority: TaskPriority
    task_brief_md: str
    git_branch: str
    pr_url: str
    created_at: str
    updated_at: str
    attempts: list[TaskAttemptOut] = Field(default_factory=list)
