export type DomainCategory =
  | "nas_guardian"
  | "media"
  | "downloads"
  | "home_automation"
  | "monitoring"
  | "telegram"
  | "scripts"
  | "tasks"
  | "ai_workspace"
  | "developer"
  | "security";

export interface AuthUser {
  username: string;
  role: string;
  csrf_token: string;
  expires_at: string;
}

export interface OverviewResponse {
  architecture: string;
  generated_at: string;
  workspace_counts: {
    projects: number;
    tasks_total: number;
    tasks_open: number;
    tasks_in_progress: number;
    scripts_total: number;
    scripts_allowlisted: number;
    reports_total: number;
    audit_events: number;
  };
  domains: {
    nas_guardian: {
      title: string;
      status: string;
      phase: string;
      reason: string;
      metrics: {
        cpu_load: string;
        ram_usage: string;
        mounts: Record<string, string>;
        smart_health: string;
        containers: string;
      };
    };
    media: {
      title: string;
      status: string;
      phase: string;
      reason: string;
      services: Record<string, string>;
    };
    downloads: {
      title: string;
      status: string;
      phase: string;
      reason: string;
      metrics: Record<string, string>;
    };
    home_automation: {
      title: string;
      status: string;
      phase: string;
      reason: string;
      integrations: Record<string, string>;
    };
    ai_workspace: {
      title: string;
      status: string;
      phase: string;
      handoff_mode: string;
      consumer_cli_wrapper: string;
    };
  };
}

export interface ScriptManifestItem {
  id: number;
  slug: string;
  name: string;
  description: string;
  category: string;
  rel_path: string;
  sha256: string;
  review_status: "draft" | "reviewed" | "allowlisted" | "revoked";
  is_executable_allowed: boolean;
  execution_policy: string;
  created_at: string;
  updated_at: string;
}

export interface ScriptDetailItem extends ScriptManifestItem {
  content: string;
  size_bytes: number;
  checksum_verified: boolean;
}

export interface ReportSummaryItem {
  id: number;
  slug: string;
  title: string;
  category: string;
  summary: string;
  rel_path: string;
  created_at: string;
}

export interface ReportDetailItem extends ReportSummaryItem {
  content: string;
  sha256: string;
  size_bytes: number;
}

export interface AuditLogItem {
  id: number;
  actor: string;
  action: string;
  target_type: string;
  target_id: string;
  details: Record<string, unknown>;
  ip_address: string;
  created_at: string;
}

export interface RedactedSettings {
  env: string;
  port: number;
  core_host: string;
  core_port: number;
  db_path: string;
  admin_username: string;
  session_ttl_seconds: number;
  cookie_secure: boolean;
  scripts_dir: string;
  reports_dir: string;
  seed_examples: boolean;
  secret_key: string;
  admin_password: string;
  telegram_bot_token: string;
  architecture_mode: string;
  script_execution_enabled: boolean;
  docker_socket_mounted: boolean;
  antigravity_cli_wrapper: string;
  integrations: Record<string, string>;
}
