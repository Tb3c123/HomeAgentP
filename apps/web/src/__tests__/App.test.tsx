import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { apiClient } from "../api/client";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    apiClient: {
      getMe: vi.fn(),
      login: vi.fn(),
      logout: vi.fn(),
      getOverview: vi.fn(),
      getSettings: vi.fn(),
      listProjects: vi.fn(),
      listTasks: vi.fn(),
      createTask: vi.fn(),
      updateTask: vi.fn(),
      createAttempt: vi.fn(),
      listScripts: vi.fn(),
      getScriptDetail: vi.fn(),
      listReports: vi.fn(),
      getReportDetail: vi.fn(),
      listAuditLogs: vi.fn(),
    },
  };
});

const mockedClient = vi.mocked(apiClient);

describe("HomeAgentP Web Dashboard", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("renders login screen when session is unauthenticated", async () => {
    mockedClient.getMe.mockRejectedValueOnce(new Error("Unauthorized"));

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/Sign in to Dashboard/i)).toBeInTheDocument();
    });
  });

  it("renders honest unavailable states and navigates across NAS, Media, Tasks, Scripts, Reports, and Settings", async () => {
    mockedClient.getMe.mockResolvedValueOnce({
      username: "nas_owner",
      role: "owner",
      csrf_token: "csrf_test_token_12345",
      expires_at: "2026-11-17T00:00:00Z",
    });

    mockedClient.getOverview.mockResolvedValue({
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
          reason: "Read-only NAS telemetry adapter not enabled in Phase 01 Foundation.",
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
          status: "unavailable",
          phase: "Phase 03",
          reason: "Read-only media API connectors are scheduled for Phase 03.",
          services: {
            jellyfin: "unavailable",
            sonarr: "unavailable",
            radarr: "unavailable",
          },
        },
        downloads: {
          title: "Downloads (qBittorrent)",
          status: "unavailable",
          phase: "Phase 03",
          reason: "qBittorrent read-only adapter is scheduled for Phase 03.",
          metrics: {
            active_torrents: "unavailable",
            stalled_torrents: "unavailable",
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
    });

    mockedClient.listProjects.mockResolvedValue([
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
    ]);

    mockedClient.listTasks.mockResolvedValue([
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
    ]);

    mockedClient.listScripts.mockResolvedValue([
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
    ]);

    mockedClient.listReports.mockResolvedValue([
      {
        id: 1,
        slug: "foundation-baseline-report",
        title: "HomeAgentP B+ — Foundation Baseline Report",
        category: "nas_guardian",
        summary: "Baseline verification",
        rel_path: "sample_daily_report.md",
        created_at: "2026-11-16T20:00:00Z",
      },
    ]);

    mockedClient.listAuditLogs.mockResolvedValue([
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
    ]);

    mockedClient.getSettings.mockResolvedValue({
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
      integrations: { nas_guardian: "unavailable" },
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("System Overview")).toBeInTheDocument();
    });

    expect(screen.getByText("Mount /mnt/disk1")).toBeInTheDocument();
    expect(screen.getByText("Mount /mnt/disk2")).toBeInTheDocument();
    expect(screen.getAllByText("UNAVAILABLE").length).toBeGreaterThan(5);

    // Navigate to Tasks
    fireEvent.click(screen.getByRole("button", { name: /Tasks & AI Handoff/i }));
    expect(screen.getByText("Verify Web/Core Skeleton")).toBeInTheDocument();

    // Navigate to Scripts
    fireEvent.click(screen.getByRole("button", { name: /Scripts Registry/i }));
    expect(screen.getByText("NAS Disk Usage Snapshot")).toBeInTheDocument();

    // Navigate to Settings
    fireEvent.click(screen.getByRole("button", { name: /Settings & Safety/i }));
    expect(
      screen.getByText("Runtime Settings & Enforced B+ Safety Constraints"),
    ).toBeInTheDocument();
    expect(screen.getByText("PROHIBITED")).toBeInTheDocument();
  });
});
