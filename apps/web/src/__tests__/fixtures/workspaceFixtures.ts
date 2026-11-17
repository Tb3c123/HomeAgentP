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
