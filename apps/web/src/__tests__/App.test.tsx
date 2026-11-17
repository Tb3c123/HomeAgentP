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
      getNasStatus: vi.fn(),
      collectNasSnapshot: vi.fn(),
      listNasHistory: vi.fn(),
      listNasAlerts: vi.fn(),
      getMediaOverview: vi.fn(),
      getMediaServices: vi.fn(),
      getMediaServiceDetail: vi.fn(),
      collectMediaSnapshot: vi.fn(),
      listMediaAlerts: vi.fn(),
      listMediaHistory: vi.fn(),
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

import type { MediaOverviewResponse } from "../api/types";

const mockedClient = vi.mocked(apiClient);

const mockMediaOverviewResponse: MediaOverviewResponse = {
  status: "degraded",
  overall_status: "degraded",
  adapter_enabled: true,
  collected_at: "2026-11-16T20:05:00Z",
  collection_interval_seconds: 90,
  history_retention_limit: 120,
  failure_threshold: 3,
  snapshot_stale_seconds: 300,
  reason: "Degraded status or warnings in: qbittorrent.",
  scheduler: {
    enabled: true,
    running: true,
    last_status: "degraded",
  },
  summary: {
    configured_services_count: 7,
    online_services_count: 6,
    jellyfin_active_streams: 2,
    jellyfin_direct_play_streams: 1,
    jellyfin_transcoding_streams: 1,
    qb_download_speed_bytes: 12582912,
    qb_upload_speed_bytes: 1048576,
    qb_downloading_count: 1,
    qb_seeding_count: 2,
    qb_stalled_count: 1,
    qb_errored_count: 0,
    sonarr_queue_count: 1,
    sonarr_missing_episodes: 3,
    radarr_queue_count: 1,
    radarr_missing_movies: 4,
    bazarr_missing_subtitles: 7,
    prowlarr_failing_indexers: 0,
    seerr_pending_requests: 1,
    seerr_approved_requests: 5,
  },
  services: {
    jellyfin: {
      service: "jellyfin",
      title: "Jellyfin Media Server",
      category: "media",
      enabled: true,
      configured: true,
      status: "online",
      error_code: null,
      reason: "Server healthy.",
      latency_ms: 14.2,
      version: "10.9.11",
      collected_at: "2026-11-16T20:05:00Z",
      stale: false,
      age_seconds: 0,
      consecutive_failures: 0,
      read_only_enforced: true,
      write_operations_performed: 0,
      metrics: {
        server_name: "HomeNAS-Jellyfin",
        operating_system: "Linux",
        libraries: {
          movies: 142,
          series: 28,
          episodes: 910,
          songs: 0,
          albums: 0,
        },
        sessions: {
          active_count: 2,
          direct_play_count: 1,
          direct_stream_count: 0,
          transcoding_count: 1,
          paused_count: 0,
          streams: [
            {
              session_id: "sess-1",
              user_name: "family",
              client: "Jellyfin Web",
              device_name: "LivingRoomTV",
              item_title: "Dune: Part Two",
              item_type: "Movie",
              play_method: "DirectPlay",
              is_paused: false,
              transcode_reasons: [],
            },
            {
              session_id: "sess-2",
              user_name: "mobile_user",
              client: "Findroid",
              device_name: "Pixel 8",
              item_title: "Severance",
              item_type: "Episode",
              play_method: "Transcode",
              is_paused: false,
              transcode_reasons: ["ContainerNotSupported"],
            },
          ],
        },
        playback_errors: {
          accessible: true,
          count: 0,
          recent: [],
        },
      },
      alerts: [],
    },
    qbittorrent: {
      service: "qbittorrent",
      title: "qBittorrent Download Client",
      category: "downloads",
      enabled: true,
      configured: true,
      status: "degraded",
      error_code: null,
      reason: "1 stalled torrent(s) exceeding 1800s threshold",
      latency_ms: 18.5,
      version: "v4.6.5",
      collected_at: "2026-11-16T20:05:00Z",
      stale: false,
      age_seconds: 0,
      consecutive_failures: 0,
      read_only_enforced: true,
      write_operations_performed: 0,
      metrics: {
        webapi_version: "2.9.3",
        connection_status: "connected",
        dht_nodes: 185,
        download_speed_bytes: 12582912,
        upload_speed_bytes: 1048576,
        downloaded_session_bytes: 10737418240,
        uploaded_session_bytes: 2147483648,
        counts: {
          total: 4,
          downloading: 1,
          seeding: 2,
          paused: 0,
          stalled: 1,
          stalled_over_threshold: 1,
          queued: 0,
          checking: 0,
          errored: 0,
        },
        stalled_threshold_seconds: 1800,
        stalled_torrents: [
          {
            hash: "abc12345",
            name: "Linux-ISO-x86_64",
            state: "stalledDL",
            progress_percent: 42.5,
            time_active_seconds: 5400,
            eta_seconds: 8640000,
            exceeds_threshold: true,
          },
        ],
        errored_torrents: [],
        active_queue: [],
        credential_scope_notice:
          "qBittorrent WebUI session cookies carry full account privileges on the server; read-only operation is strictly enforced client-side by HomeAgentP via GET-only endpoint allowlisting.",
      },
      alerts: [],
    },
    sonarr: {
      service: "sonarr",
      title: "Sonarr TV Automation",
      category: "media",
      enabled: true,
      configured: true,
      status: "online",
      error_code: null,
      reason: "Sonarr v3 healthy.",
      latency_ms: 11.0,
      version: "4.0.9.2244",
      collected_at: "2026-11-16T20:05:00Z",
      stale: false,
      age_seconds: 0,
      consecutive_failures: 0,
      read_only_enforced: true,
      write_operations_performed: 0,
      metrics: {
        total_count: 28,
        monitored_count: 26,
        available_file_count: 910,
        size_on_disk_bytes: 1099511627776,
        missing_count: 3,
        queue_total: 1,
        queue_failed_count: 0,
        queue_items: [],
        failed_imports: [],
        health_warnings: [],
        diskspace: [
          {
            path: "/mnt/disk1/media/tv",
            label: "disk1",
            free_bytes: 2199023255552,
            total_bytes: 8796093022208,
          },
        ],
      },
      alerts: [],
    },
    radarr: {
      service: "radarr",
      title: "Radarr Movie Automation",
      category: "media",
      enabled: true,
      configured: true,
      status: "online",
      error_code: null,
      reason: "Radarr v3 healthy.",
      latency_ms: 10.4,
      version: "5.10.3.9171",
      collected_at: "2026-11-16T20:05:00Z",
      stale: false,
      age_seconds: 0,
      consecutive_failures: 0,
      read_only_enforced: true,
      write_operations_performed: 0,
      metrics: {
        total_count: 142,
        monitored_count: 130,
        available_file_count: 126,
        size_on_disk_bytes: 2199023255552,
        missing_count: 4,
        queue_total: 1,
        queue_failed_count: 0,
        queue_items: [],
        failed_imports: [],
        health_warnings: [],
        diskspace: [],
      },
      alerts: [],
    },
    bazarr: {
      service: "bazarr",
      title: "Bazarr Subtitle Manager",
      category: "media",
      enabled: true,
      configured: true,
      status: "online",
      error_code: null,
      reason: "Bazarr healthy.",
      latency_ms: 9.8,
      version: "1.4.3",
      collected_at: "2026-11-16T20:05:00Z",
      stale: false,
      age_seconds: 0,
      consecutive_failures: 0,
      read_only_enforced: true,
      write_operations_performed: 0,
      metrics: {
        missing_episode_subtitles: 5,
        missing_movie_subtitles: 2,
        unhealthy_providers_count: 0,
        sonarr_signalr: "LIVE",
        radarr_signalr: "LIVE",
        health_issues: [],
      },
      alerts: [],
    },
    prowlarr: {
      service: "prowlarr",
      title: "Prowlarr Indexer Manager",
      category: "media",
      enabled: true,
      configured: true,
      status: "online",
      error_code: null,
      reason: "Prowlarr v1 healthy.",
      latency_ms: 8.6,
      version: "1.24.3.4754",
      collected_at: "2026-11-16T20:05:00Z",
      stale: false,
      age_seconds: 0,
      consecutive_failures: 0,
      read_only_enforced: true,
      write_operations_performed: 0,
      metrics: {
        total_indexers: 6,
        enabled_indexers: 6,
        failing_indexers_count: 0,
        failing_indexers: [],
        health_warnings: [],
      },
      alerts: [],
    },
    seerr: {
      service: "seerr",
      title: "Seerr Media Requests",
      category: "media",
      enabled: true,
      configured: true,
      status: "online",
      error_code: null,
      reason: "Seerr v1 healthy.",
      latency_ms: 12.1,
      version: "2.0.1",
      collected_at: "2026-11-16T20:05:00Z",
      stale: false,
      age_seconds: 0,
      consecutive_failures: 0,
      read_only_enforced: true,
      write_operations_performed: 0,
      metrics: {
        update_available: false,
        commits_behind: 0,
        requests: {
          total: 18,
          movie: 10,
          tv: 8,
          pending: 1,
          approved: 5,
          processing: 1,
          available: 10,
          declined: 1,
        },
        recent_requests: [],
      },
      alerts: [],
    },
  },
  alerts: [
    {
      alert_key: "media:qbittorrent:media.qbittorrent.stalled_torrents",
      code: "media.qbittorrent.stalled_torrents",
      severity: "warning",
      category: "downloads",
      service: "qbittorrent",
      target: "qbittorrent",
      message: "qBittorrent has 1 stalled torrent(s) exceeding 1800s threshold.",
      status: "active",
      first_seen_at: "2026-11-16T20:00:00Z",
      last_seen_at: "2026-11-16T20:05:00Z",
      occurrences: 2,
    },
  ],
  safety: {
    read_only_enforced: true,
    write_operations_performed: 0,
    media_filesystem_mounted: false,
    docker_socket_used: false,
    ssrf_allowlist_enforced: true,
    redirects_blocked: true,
    qbittorrent_client_allowlist_only: true,
  },
};

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

  it("renders honest unavailable states and navigates across NAS Guardian, Media & Downloads, Tasks, Scripts, Reports, and Settings", async () => {
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
    });

    mockedClient.getNasStatus.mockResolvedValue({
      status: "critical",
      adapter_enabled: true,
      collected_at: "2026-11-16T20:05:00Z",
      collection_interval_seconds: 60,
      history_retention_limit: 500,
      thresholds: {
        cpu_warn_percent: 80,
        cpu_critical_percent: 92,
        ram_warn_percent: 82,
        ram_critical_percent: 92,
        disk_warn_percent: 80,
        disk_critical_percent: 90,
        container_mem_warn_percent: 85,
        container_mem_critical_percent: 95,
      },
      cpu: {
        status: "ok",
        usage_percent: 18.4,
        logical_cores: 4,
        load_1m: 0.42,
        load_5m: 0.35,
        load_15m: 0.28,
        pressure: {
          some: { avg10: 1.25, avg60: 0.65, avg300: 0.2, total_us: 12000 },
          full: null,
        },
      },
      memory: {
        status: "ok",
        total_bytes: 16 * 1024 * 1024 * 1024,
        available_bytes: 12 * 1024 * 1024 * 1024,
        used_bytes: 4 * 1024 * 1024 * 1024,
        usage_percent: 25.0,
        swap_total_bytes: 4 * 1024 * 1024 * 1024,
        swap_free_bytes: 4 * 1024 * 1024 * 1024,
        swap_used_bytes: 0,
        swap_usage_percent: 0.0,
        pressure: {
          some: { avg10: 0.05, avg60: 0.02, avg300: 0.0, total_us: 500 },
          full: { avg10: 0.0, avg60: 0.0, avg300: 0.0, total_us: 0 },
        },
      },
      mounts: {
        "/": {
          path: "/",
          required: false,
          status: "mounted",
          is_mounted: true,
          is_root_fallback: false,
          device: "/dev/nvme0n1p2",
          fstype: "ext4",
          total_bytes: 256 * 1024 * 1024 * 1024,
          available_bytes: 200 * 1024 * 1024 * 1024,
          used_bytes: 56 * 1024 * 1024 * 1024,
          usage_percent: 21.9,
          reason: "",
        },
        "/mnt/disk1": {
          path: "/mnt/disk1",
          required: true,
          status: "mounted",
          is_mounted: true,
          is_root_fallback: false,
          device: "/dev/sda1",
          fstype: "ext4",
          total_bytes: 8000 * 1024 * 1024 * 1024,
          available_bytes: 3000 * 1024 * 1024 * 1024,
          used_bytes: 5000 * 1024 * 1024 * 1024,
          usage_percent: 62.5,
          reason: "",
        },
        "/mnt/disk2": {
          path: "/mnt/disk2",
          required: true,
          status: "unmounted_fallback",
          is_mounted: false,
          is_root_fallback: true,
          device: "",
          fstype: "",
          total_bytes: null,
          available_bytes: null,
          used_bytes: null,
          usage_percent: null,
          reason: "Directory exists on root filesystem (/) — underlying HDD is unmounted.",
        },
      },
      containers: {
        status: "unavailable",
        docker_socket_mounted: false,
        source: "not_configured",
        services: {
          jellyfin: {
            name: "jellyfin",
            status: "unavailable",
            state: "unavailable",
            memory_bytes: null,
            memory_limit_bytes: null,
            memory_percent: null,
            restart_count: null,
            reason: "No read-only container snapshot configured.",
          },
        },
        reason: "Docker socket is prohibited by B+ policy.",
      },
      alerts: [
        {
          alert_key: "mount:/mnt/disk2:mount.unmounted_fallback",
          code: "mount.unmounted_fallback",
          severity: "critical",
          category: "mount_guardian",
          target: "/mnt/disk2",
          message: "Mount /mnt/disk2 is UNMOUNTED (directory fell back to root filesystem /).",
          status: "active",
          first_seen_at: "2026-11-16T20:00:00Z",
          last_seen_at: "2026-11-16T20:05:00Z",
          occurrences: 3,
        },
      ],
      telemetry_boundary: {
        mode: "host_snapshot",
        source: "nas_host_snapshot.json",
        host_verified: true,
        fresh: true,
      },
      scheduler: {
        enabled: true,
        running: true,
        last_status: "critical",
      },
      storage_safety: {
        hdd_write_operations: 0,
        media_tree_crawled: false,
        docker_socket_used: false,
      },
    });

    mockedClient.listNasHistory.mockResolvedValue([
      {
        id: 1,
        collected_at: "2026-11-16T20:05:00Z",
        adapter_status: "critical",
        cpu_usage_percent: 18.4,
        load_1m: 0.42,
        load_5m: 0.35,
        load_15m: 0.28,
        ram_total_bytes: 16 * 1024 * 1024 * 1024,
        ram_available_bytes: 12 * 1024 * 1024 * 1024,
        ram_used_bytes: 4 * 1024 * 1024 * 1024,
        ram_usage_percent: 25.0,
        swap_total_bytes: 4 * 1024 * 1024 * 1024,
        swap_used_bytes: 0,
        swap_usage_percent: 0.0,
      },
    ]);

    mockedClient.listNasAlerts.mockImplementation(async (includeResolved?: boolean) => {
      const activeItem = {
        id: 1,
        alert_key: "mount:/mnt/disk2:mount.unmounted_fallback",
        code: "mount.unmounted_fallback",
        severity: "critical" as const,
        category: "mount_guardian",
        target: "/mnt/disk2",
        message: "Mount /mnt/disk2 is UNMOUNTED (directory fell back to root filesystem /).",
        status: "active",
        first_seen_at: "2026-11-16T20:00:00Z",
        last_seen_at: "2026-11-16T20:05:00Z",
        occurrences: 3,
      };
      if (includeResolved) {
        return [
          activeItem,
          {
            id: 2,
            alert_key: "cpu:cpu.usage_warning",
            code: "cpu.usage_warning",
            severity: "warning" as const,
            category: "cpu",
            target: "cpu",
            message: "CPU usage was elevated.",
            status: "resolved",
            first_seen_at: "2026-11-16T19:00:00Z",
            last_seen_at: "2026-11-16T19:05:00Z",
            resolved_at: "2026-11-16T19:06:00Z",
            occurrences: 2,
          },
        ];
      }
      return [activeItem];
    });

    mockedClient.getMediaOverview.mockResolvedValue(mockMediaOverviewResponse);
    mockedClient.listMediaHistory.mockResolvedValue([
      {
        id: 1,
        collected_at: "2026-11-16T20:05:00Z",
        overall_status: "degraded",
        jellyfin_active_streams: 2,
        jellyfin_transcoding_streams: 1,
        qb_dl_speed_bytes: 12582912,
        qb_up_speed_bytes: 1048576,
        qb_downloading_count: 1,
        qb_stalled_count: 1,
        qb_errored_count: 0,
        sonarr_queue_count: 1,
        radarr_queue_count: 1,
        missing_subtitles_count: 7,
        pending_requests_count: 1,
      },
    ]);
    mockedClient.listMediaAlerts.mockImplementation(async (includeResolved?: boolean) => {
      const activeAlert = {
        id: 10,
        alert_key: "media:qbittorrent:media.qbittorrent.stalled_torrents",
        code: "media.qbittorrent.stalled_torrents",
        severity: "warning" as const,
        category: "downloads",
        service: "qbittorrent",
        target: "qbittorrent",
        message: "qBittorrent has 1 stalled torrent(s) exceeding 1800s threshold.",
        status: "active",
        first_seen_at: "2026-11-16T20:00:00Z",
        last_seen_at: "2026-11-16T20:05:00Z",
        occurrences: 2,
      };
      if (includeResolved) {
        return [
          activeAlert,
          {
            id: 11,
            alert_key: "media:prowlarr:media.prowlarr.indexer_failure",
            code: "media.prowlarr.indexer_failure",
            severity: "warning" as const,
            category: "indexers",
            service: "prowlarr",
            target: "prowlarr",
            message: "Prowlarr had 1 failing indexer.",
            status: "resolved",
            first_seen_at: "2026-11-16T18:00:00Z",
            last_seen_at: "2026-11-16T18:05:00Z",
            resolved_at: "2026-11-16T18:10:00Z",
            occurrences: 1,
          },
        ];
      }
      return [activeAlert];
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
      integrations: { nas_guardian: "critical", media_downloads: "warning" },
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("System Overview")).toBeInTheDocument();
    });

    expect(screen.getByText("Mount /mnt/disk1")).toBeInTheDocument();
    expect(screen.getByText("Mount /mnt/disk2")).toBeInTheDocument();
    expect(mockedClient.listNasAlerts).toHaveBeenCalledWith(false);
    expect(mockedClient.listMediaAlerts).toHaveBeenCalledWith(false);

    // Navigate to NAS Guardian
    fireEvent.click(screen.getByRole("button", { name: /^NAS Guardian$/i }));
    expect(
      screen.getByText(/NAS Guardian \(CPU, RAM, Mount Guardian & Container Health\)/i),
    ).toBeInTheDocument();
    expect(screen.getByText("HOST_SNAPSHOT")).toBeInTheDocument();
    expect(screen.getByText("UNMOUNTED_FALLBACK")).toBeInTheDocument();
    expect(
      screen.getByText(
        /Mount \/mnt\/disk2 is UNMOUNTED \(directory fell back to root filesystem \/\)\./i,
      ),
    ).toBeInTheDocument();

    // Toggle "Show resolved" checkbox on NAS Guardian -> calls listNasAlerts(true) and displays resolved alert
    fireEvent.click(screen.getByLabelText(/Show resolved/i));
    await waitFor(() => {
      expect(mockedClient.listNasAlerts).toHaveBeenCalledWith(true);
      expect(screen.getByText("CPU usage was elevated.")).toBeInTheDocument();
      expect(screen.getByText("RESOLVED")).toBeInTheDocument();
    });

    // Navigate to Media & Downloads Hub (Phase 03)
    fireEvent.click(screen.getByRole("button", { name: /Media & Downloads/i }));
    expect(
      screen.getByText(/Media & Downloads Monitoring Hub \(Phase 03 Read-Only\)/i),
    ).toBeInTheDocument();
    expect(screen.getByText("Dune: Part Two")).toBeInTheDocument();
    expect(screen.getByText("Severance")).toBeInTheDocument();
    expect(screen.getByText("Linux-ISO-x86_64")).toBeInTheDocument();
    expect(
      screen.getByText(/qBittorrent has 1 stalled torrent\(s\) exceeding 1800s threshold\./i),
    ).toBeInTheDocument();

    // Toggle "Show resolved" on Media Alerts -> calls listMediaAlerts(true) and shows resolved Prowlarr alert
    fireEvent.click(screen.getByLabelText(/Show resolved/i));
    await waitFor(() => {
      expect(mockedClient.listMediaAlerts).toHaveBeenCalledWith(true);
      expect(screen.getByText("Prowlarr had 1 failing indexer.")).toBeInTheDocument();
    });

    // Trigger manual read-only media poll on Media & Downloads tab
    mockedClient.collectMediaSnapshot.mockResolvedValueOnce(mockMediaOverviewResponse);
    fireEvent.click(screen.getByRole("button", { name: /Media & Downloads/i }));
    fireEvent.click(screen.getByRole("button", { name: /Poll Read-Only Media Snapshot/i }));
    await waitFor(() => {
      expect(mockedClient.collectMediaSnapshot).toHaveBeenCalledTimes(1);
    });

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


