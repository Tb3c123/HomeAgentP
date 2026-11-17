import type { AuthUser, OverviewResponse, RedactedSettings } from "../../api/types";

export const mockAuthUser: AuthUser = {
  username: "nas_owner",
  role: "owner",
  csrf_token: "csrf_test_token_12345",
  expires_at: "2026-11-17T00:00:00Z",
};

export function createMockOverview(
  overrides: Partial<OverviewResponse> = {},
): OverviewResponse {
  return {
    architecture: "B+ (Antigravity-first, Dashboard-light)",
    generated_at: "2026-11-16T20:00:00Z",
    workspace_counts: {
      projects: 4,
      tasks_total: 1,
      tasks_open: 1,
      tasks_in_progress: 1,
      scripts_total: 2,
      scripts_allowlisted: 1,
      reports_total: 1,
      audit_events: 2,
    },
    domains: {
      nas_guardian: {
        title: "NAS Guardian",
        status: "unavailable",
        phase: "Phase 02",
        reason: "Read-only NAS telemetry adapter is disabled.",
        metrics: {
          cpu_load: "unavailable",
          ram_usage: "unavailable",
          mounts: { "/mnt/disk1": "unavailable", "/mnt/disk2": "unavailable" },
          smart_health: "unavailable",
          containers: "unavailable",
        },
      },
      media: {
        title: "Media Stack",
        status: "online",
        phase: "Phase 03",
        reason: "Read-only media API connectors active.",
        services: {
          jellyfin: "online",
          sonarr: "online",
          radarr: "online",
          bazarr: "online",
          prowlarr: "online",
          seerr: "online",
        },
      },
      downloads: {
        title: "Downloads (qBittorrent)",
        status: "degraded",
        phase: "Phase 03",
        reason: "1 stalled torrent(s) exceeding 1800s threshold",
        metrics: {
          active_torrents: "3",
          stalled_torrents: "1",
        },
      },
      home_automation: {
        title: "Home Assistant & Telegram Alerts",
        status: "unavailable",
        phase: "Phase 05",
        reason: "Scheduled for Phase 05.",
        integrations: {
          home_assistant: "unavailable",
          telegram_alerts: "unavailable",
        },
      },
      ai_workspace: {
        title: "AI Workspace & Developer Handoff",
        status: "online",
        phase: "Phase 01",
        handoff_mode: "Git branch/PR",
        consumer_cli_wrapper: "disabled_by_policy",
      },
    },
    ...overrides,
  };
}

export const mockRedactedSettings: RedactedSettings = {
  env: "testing",
  port: 8310,
  core_host: "127.0.0.1",
  core_port: 8311,
  db_path: "./data/homeagentp.db",
  admin_username: "nas_owner",
  session_ttl_seconds: 28800,
  cookie_secure: false,
  scripts_dir: "./config/examples/scripts",
  reports_dir: "./config/examples/reports",
  seed_examples: true,
  secret_key: "[REDACTED]",
  admin_password: "[REDACTED]",
  telegram_bot_token: "not_configured",
  architecture_mode: "B+ (Antigravity-first, Dashboard-light)",
  script_execution_enabled: false,
  docker_socket_mounted: false,
  antigravity_cli_wrapper: "prohibited",
  integrations: { nas_guardian: "critical", media_downloads: "warning" },
};
