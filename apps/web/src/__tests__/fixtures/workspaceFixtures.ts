import type {
  AuditLogItem,
  ProjectItem,
  ReportSummaryItem,
  ScriptManifestItem,
  TaskItem,
} from "../../api/types";

export const mockProjects: ProjectItem[] = [
  {
    id: 1,
    slug: "nas-guardian",
    name: "NAS Guardian & Storage Safety",
    category: "nas_guardian",
    description: "Monitor mounts safely",
    repo_url: "https://github.com/Tb3c123/HomeAgentP",
    created_at: "2026-11-16T20:00:00Z",
    updated_at: "2026-11-16T20:00:00Z",
  },
];

export const mockTasks: TaskItem[] = [
  {
    id: 10,
    project_id: 1,
    title: "Verify Web/Core Skeleton",
    description: "Phase 01 Foundation check",
    category: "developer",
    status: "in_progress",
    priority: "high",
    task_brief_md: "Scope: Phase 01",
    git_branch: "feature/phase-01-foundation",
    pr_url: "",
    created_at: "2026-11-16T20:00:00Z",
    updated_at: "2026-11-16T20:00:00Z",
    attempts: [],
  },
];

export const mockScripts: ScriptManifestItem[] = [
  {
    id: 1,
    slug: "disk-usage-report",
    name: "NAS Disk Usage Snapshot",
    description: "Inspect non-tmpfs usage",
    category: "nas_guardian",
    rel_path: "disk_usage_report.sh",
    sha256: "c40275641731043d6d6e1a240dc5c571dc226a5c7c5bd41a769e459f63045098",
    review_status: "allowlisted",
    is_executable_allowed: false,
    execution_policy: "read_only_phase_01",
    created_at: "2026-11-16T20:00:00Z",
    updated_at: "2026-11-16T20:00:00Z",
  },
];

export const mockReports: ReportSummaryItem[] = [
  {
    id: 1,
    slug: "foundation-baseline-report",
    title: "HomeAgentP B+ — Foundation Baseline Report",
    category: "nas_guardian",
    summary: "Baseline verification",
    rel_path: "sample_daily_report.md",
    created_at: "2026-11-16T20:00:00Z",
  },
];

export const mockAuditLogs: AuditLogItem[] = [
  {
    id: 1,
    actor: "nas_owner",
    action: "auth.login_succeeded",
    target_type: "session",
    target_id: "",
    details: {},
    ip_address: "127.0.0.1",
    created_at: "2026-11-16T20:00:00Z",
  },
];

export const mockTaskBriefs = [
  {
    id: 1,
    task_id: 10,
    version: 1,
    purpose: "Verify Phase 04 workspace handoff",
    scope: "Task Briefs + Artifacts UI",
    excluded_scope: "Live NAS deployment",
    input_references: ["docs/plans/04-workspace-artifacts.md"],
    acceptance_checks: ["Vitest passes"],
    security_constraints: "No secret leakage",
    rollback_plan: "Revert UI commit",
    human_status: "ready_for_handoff" as const,
    rendered_text: "# Task Brief v1\nPurpose: Verify Phase 04 workspace handoff",
    created_by: "nas_owner",
    created_at: "2026-11-17T01:00:00Z",
  },
];

export const mockWorkspaceArtifacts = [
  {
    id: 1,
    slug: "phase-04-plan",
    revision: 1,
    version: "1.0.0",
    title: "Phase 04 Workspace Plan",
    kind: "plan" as const,
    source_type: "allowlisted_report" as const,
    rel_path: "sample_daily_report.md",
    sha256: "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
    git_url: "https://github.com/Tb3c123/HomeAgentP/blob/main/docs/plans/04-workspace-artifacts.md",
    summary: "Phase 04 workspace and artifacts plan",
    tags: ["phase-04", "plan"],
    project_id: 1,
    task_id: 10,
    created_by: "nas_owner",
    created_at: "2026-11-17T01:05:00Z",
  },
];

export const mockWorkspaceArtifactDetail = {
  ...mockWorkspaceArtifacts[0],
  content: "# Sample Daily Report\nAll NAS mounts healthy.",
  size_bytes: 47,
  checksum_verified: true,
};

export const mockGitProvenanceLinks = [
  {
    id: 1,
    entity_type: "task" as const,
    entity_id: 10,
    repo_url: "https://github.com/Tb3c123/HomeAgentP",
    branch: "feature/phase-04-workspace-artifacts",
    commit_sha: "7963fee",
    pr_url: "https://github.com/Tb3c123/HomeAgentP/pull/4",
    review_status: "pending" as const,
    ci_status: "success" as const,
    ci_url: "https://github.com/Tb3c123/HomeAgentP/actions/runs/12345",
    verification_source: "manual_unverified" as const,
    created_at: "2026-11-17T01:10:00Z",
    updated_at: "2026-11-17T01:10:00Z",
  },
];
