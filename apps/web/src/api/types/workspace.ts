export type HumanBriefStatus =
  | "draft"
  | "ready_for_handoff"
  | "handed_off"
  | "approved"
  | "archived";

export interface TaskBriefCreateInput {
  purpose: string;
  scope: string;
  excluded_scope: string;
  input_references: string[];
  acceptance_checks: string[];
  security_constraints: string;
  rollback_plan: string;
  human_status: HumanBriefStatus;
  expected_latest_version?: number | null;
}

export interface TaskBriefItem {
  id: number;
  task_id: number;
  version: number;
  purpose: string;
  scope: string;
  excluded_scope: string;
  input_references: string[];
  acceptance_checks: string[];
  security_constraints: string;
  rollback_plan: string;
  human_status: HumanBriefStatus;
  rendered_text: string;
  created_by: string;
  created_at: string;
}

export interface TaskBriefExportItem {
  task_id: number;
  version: number;
  human_status: HumanBriefStatus;
  handoff_mode: "manual_copy_only";
  rendered_text: string;
}

export type ArtifactKind = "artifact" | "knowledge" | "plan" | "runbook";
export type ArtifactSourceType =
  | "allowlisted_report"
  | "allowlisted_script"
  | "git_reference"
  | "note";

export interface WorkspaceArtifactCreateInput {
  slug: string;
  version: string;
  title: string;
  kind: ArtifactKind;
  source_type: ArtifactSourceType;
  rel_path: string;
  expected_sha256?: string;
  git_url: string;
  summary: string;
  tags: string[];
  project_id?: number | null;
  task_id?: number | null;
  expected_latest_revision?: number | null;
}

export interface WorkspaceArtifactItem {
  id: number;
  slug: string;
  revision: number;
  version: string;
  title: string;
  kind: ArtifactKind;
  source_type: ArtifactSourceType;
  rel_path: string;
  sha256: string;
  git_url: string;
  summary: string;
  tags: string[];
  project_id: number | null;
  task_id: number | null;
  created_by: string;
  created_at: string;
}

export interface WorkspaceArtifactDetailItem extends WorkspaceArtifactItem {
  content: string | null;
  size_bytes: number | null;
  checksum_verified: boolean;
}

export interface ArtifactFilterParams {
  kind?: ArtifactKind | "";
  source_type?: ArtifactSourceType | "";
  tag?: string;
  q?: string;
  limit?: number;
  offset?: number;
}

export type ProvenanceEntityType = "task" | "artifact";
export type ProvenanceReviewStatus =
  | "none"
  | "pending"
  | "approved"
  | "changes_requested";
export type ProvenanceCiStatus = "unknown" | "pending" | "success" | "failure";
export type VerificationSource = "manual_unverified" | "external_ci_verified";

export interface GitProvenanceCreateInput {
  entity_type: ProvenanceEntityType;
  entity_id: number;
  repo_url: string;
  branch: string;
  commit_sha: string;
  pr_url: string;
  review_status: ProvenanceReviewStatus;
  ci_status: ProvenanceCiStatus;
  ci_url: string;
}

export interface GitProvenanceUpdateInput {
  branch?: string;
  commit_sha?: string;
  pr_url?: string;
  review_status?: ProvenanceReviewStatus;
  ci_status?: ProvenanceCiStatus;
  ci_url?: string;
}

export interface GitProvenanceItem {
  id: number;
  entity_type: ProvenanceEntityType;
  entity_id: number;
  repo_url: string;
  branch: string;
  commit_sha: string;
  pr_url: string;
  review_status: ProvenanceReviewStatus;
  ci_status: ProvenanceCiStatus;
  ci_url: string;
  verification_source: VerificationSource;
  created_at: string;
  updated_at: string;
}
