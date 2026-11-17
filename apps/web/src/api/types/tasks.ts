import type { DomainCategory } from "./common";

export type TaskStatus =
  | "backlog"
  | "ready"
  | "in_progress"
  | "review"
  | "done"
  | "blocked";

export type TaskPriority = "low" | "medium" | "high" | "critical";

export interface ProjectItem {
  id: number;
  slug: string;
  name: string;
  category: DomainCategory;
  description: string;
  repo_url: string;
  created_at: string;
  updated_at: string;
}

export interface TaskAttemptItem {
  id: number;
  task_id: number;
  attempt_number: number;
  executor_type: "human" | "antigravity_handoff" | "scheduled_job";
  status: "started" | "succeeded" | "failed" | "cancelled" | "not_tested";
  summary: string;
  artifact_rel_path: string;
  created_at: string;
  finished_at: string | null;
}

export interface TaskItem {
  id: number;
  project_id: number | null;
  title: string;
  description: string;
  category: DomainCategory;
  status: TaskStatus;
  priority: TaskPriority;
  task_brief_md: string;
  git_branch: string;
  pr_url: string;
  created_at: string;
  updated_at: string;
  attempts: TaskAttemptItem[];
}
