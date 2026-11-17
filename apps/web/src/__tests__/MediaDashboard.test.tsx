import { fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { describe, expect, it, vi } from "vitest";
import type {
  MediaAlertItem,
  MediaHistoryItem,
  MediaOverviewResponse,
  OverviewResponse,
} from "../api/types";
import { MediaDashboard } from "../components/media/MediaDashboard";

const baseOverview: OverviewResponse = {
  architecture: "antigravity-first-dashboard-light",
  generated_at: "2026-11-16T20:05:00Z",
  workspace_counts: {
    projects: 1,
    tasks_total: 1,
    tasks_open: 1,
    tasks_in_progress: 0,
    scripts_total: 1,
    scripts_allowlisted: 1,
    reports_total: 1,
    audit_events: 1,
  },
  domains: {
    nas_guardian: {
      title: "NAS Guardian",
      status: "ok",
      phase: "phase-02",
      reason: "Healthy",
      metrics: {
        cpu_load: "ok",
        ram_usage: "ok",
        mounts: { "/mnt/disk1": "ok", "/mnt/disk2": "ok" },
        smart_health: "ok",
        containers: "ok",
      },
    },
    media: {
      title: "Media Services",
      status: "not_configured",
      phase: "phase-03",
      reason: "Media connectors disabled.",
      services: {
        jellyfin: "not_configured",
        sonarr: "not_configured",
        radarr: "not_configured",
      },
    },
    downloads: {
      title: "qBittorrent Downloads",
      status: "not_configured",
      phase: "phase-03",
      reason: "qBittorrent disabled.",
      metrics: {
        active_torrents: "unavailable",
        stalled_torrents: "unavailable",
      },
    },
    home_automation: {
      title: "Home Assistant",
      status: "not_configured",
      phase: "phase-04",
      reason: "Planned",
      integrations: { home_assistant: "not_configured" },
    },
    ai_workspace: {
      title: "AI Workspace",
      status: "ok",
      phase: "phase-01",
      handoff_mode: "git",
      consumer_cli_wrapper: "disabled",
    },
  },
};

const sampleMediaOverview: MediaOverviewResponse = {
  status: "degraded",
  overall_status: "degraded",
  adapter_enabled: true,
  collected_at: "2026-11-16T20:05:00Z",
  collection_interval_seconds: 90,
  history_retention_limit: 120,
  failure_threshold: 3,
  snapshot_stale_seconds: 300,
  reason: "Degraded status or warnings in: qbittorrent.",
  scheduler: { enabled: true, running: true, last_status: "degraded" },
  summary: {
    configured_services_count: 7,
    online_services_count: 6,
    jellyfin_active_streams: 1,
    jellyfin_direct_play_streams: 1,
    jellyfin_transcoding_streams: 0,
    qb_download_speed_bytes: 5242880,
    qb_upload_speed_bytes: 1048576,
    qb_downloading_count: 1,
    qb_seeding_count: 2,
    qb_stalled_count: 1,
    qb_errored_count: 0,
    sonarr_queue_count: 0,
    sonarr_missing_episodes: 2,
    radarr_queue_count: 0,
    radarr_missing_movies: 1,
    bazarr_missing_subtitles: 4,
    prowlarr_failing_indexers: 0,
    seerr_pending_requests: 1,
    seerr_approved_requests: 3,
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
      latency_ms: 12.0,
      version: "10.9.11",
      collected_at: "2026-11-16T20:05:00Z",
      stale: false,
      age_seconds: 0,
      consecutive_failures: 0,
      read_only_enforced: true,
      write_operations_performed: 0,
      metrics: {
        server_name: "HomeNAS",
        operating_system: "Linux",
        libraries: { movies: 120, series: 24, episodes: 800, songs: 0, albums: 0 },
        sessions: {
          active_count: 1,
          direct_play_count: 1,
          direct_stream_count: 0,
          transcoding_count: 0,
          paused_count: 0,
          streams: [
            {
              session_id: "s1",
              user_name: "family",
              client: "Web",
              device_name: "TV",
              item_title: "Dune: Part Two",
              item_type: "Movie",
              play_method: "DirectPlay",
              is_paused: false,
              transcode_reasons: [],
            },
          ],
        },
        playback_errors: { accessible: true, count: 0, recent: [] },
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
      reason: "1 stalled torrent",
      latency_ms: 15.0,
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
        dht_nodes: 100,
        download_speed_bytes: 5242880,
        upload_speed_bytes: 1048576,
        downloaded_session_bytes: 1000,
        uploaded_session_bytes: 500,
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
            hash: "h1",
            name: "Ubuntu-24.04-ISO",
            state: "stalledDL",
            progress_percent: 55.0,
            exceeds_threshold: true,
          },
        ],
        errored_torrents: [],
        active_queue: [],
        credential_scope_notice: "Read-only GET allowlist enforced.",
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
      reason: "Healthy",
      latency_ms: 10,
      version: "4.0.9",
      collected_at: "2026-11-16T20:05:00Z",
      stale: false,
      age_seconds: 0,
      consecutive_failures: 0,
      read_only_enforced: true,
      write_operations_performed: 0,
      metrics: {
        total_count: 24,
        monitored_count: 20,
        available_file_count: 800,
        size_on_disk_bytes: 1099511627776,
        missing_count: 2,
        queue_total: 0,
        queue_failed_count: 0,
        queue_items: [],
        failed_imports: [],
        health_warnings: [],
        diskspace: [],
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
      reason: "Healthy",
      latency_ms: 9,
      version: "5.10.0",
      collected_at: "2026-11-16T20:05:00Z",
      stale: false,
      age_seconds: 0,
      consecutive_failures: 0,
      read_only_enforced: true,
      write_operations_performed: 0,
      metrics: {
        total_count: 120,
        monitored_count: 110,
        available_file_count: 118,
        size_on_disk_bytes: 2199023255552,
        missing_count: 1,
        queue_total: 0,
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
      title: "Bazarr Subtitles",
      category: "media",
      enabled: true,
      configured: true,
      status: "online",
      error_code: null,
      reason: "Healthy",
      latency_ms: 8,
      version: "1.4.5",
      collected_at: "2026-11-16T20:05:00Z",
      stale: false,
      age_seconds: 0,
      consecutive_failures: 0,
      read_only_enforced: true,
      write_operations_performed: 0,
      metrics: {
        missing_episode_subtitles: 3,
        missing_movie_subtitles: 1,
        unhealthy_providers_count: 0,
        sonarr_signalr: "connected",
        radarr_signalr: "connected",
        health_issues: [],
      },
      alerts: [],
    },
    prowlarr: {
      service: "prowlarr",
      title: "Prowlarr Indexers",
      category: "media",
      enabled: true,
      configured: true,
      status: "online",
      error_code: null,
      reason: "Healthy",
      latency_ms: 7,
      version: "1.24.0",
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
      reason: "Healthy",
      latency_ms: 6,
      version: "2.0.0",
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
          total: 10,
          movie: 6,
          tv: 4,
          pending: 1,
          approved: 3,
          processing: 1,
          available: 5,
          declined: 0,
        },
        recent_requests: [],
      },
      alerts: [],
    },
  },
  alerts: [
    {
      alert_key: "qbittorrent:stalled:h1",
      code: "torrent_stalled",
      severity: "warning",
      category: "downloads",
      service: "qbittorrent",
      target: "Ubuntu-24.04-ISO",
      message: "Torrent stalled for 3000s",
      status: "active",
    },
  ],
  safety: {
    read_only_enforced: true,
    write_operations_performed: 0,
    ssrf_allowlist_enforced: true,
    redirects_blocked: true,
    media_filesystem_mounted: false,
    docker_socket_used: false,
    qbittorrent_client_allowlist_only: true,
  },
};

const sampleAlerts: MediaAlertItem[] = [
  {
    id: 1,
    alert_key: "qbittorrent:stalled:h1",
    code: "torrent_stalled",
    severity: "warning",
    category: "downloads",
    service: "qbittorrent",
    target: "Ubuntu-24.04-ISO",
    message: "Torrent stalled for 3000s",
    status: "active",
    first_seen_at: "2026-11-16T20:00:00Z",
    last_seen_at: "2026-11-16T20:05:00Z",
    occurrences: 2,
  },
];

const sampleHistory: MediaHistoryItem[] = [
  {
    id: 10,
    collected_at: "2026-11-16T20:05:00Z",
    overall_status: "degraded",
    jellyfin_active_streams: 1,
    jellyfin_transcoding_streams: 0,
    qb_dl_speed_bytes: 5242880,
    qb_up_speed_bytes: 1048576,
    qb_downloading_count: 1,
    qb_stalled_count: 1,
    qb_errored_count: 0,
    sonarr_queue_count: 0,
    radarr_queue_count: 0,
    missing_subtitles_count: 4,
    pending_requests_count: 1,
  },
];

describe("MediaDashboard interactions", () => {
  it("renders all media cards, triggers snapshot poll, and toggles resolved alerts", () => {
    const onCollectSnapshot = vi.fn();
    const onToggleIncludeResolved = vi.fn();

    render(
      <MediaDashboard
        overview={baseOverview}
        mediaOverview={sampleMediaOverview}
        mediaAlerts={sampleAlerts}
        mediaHistory={sampleHistory}
        mediaCollectBusy={false}
        includeResolvedMediaAlerts={false}
        onCollectSnapshot={onCollectSnapshot}
        onToggleIncludeResolved={onToggleIncludeResolved}
      />,
    );

    expect(screen.getByText(/Dune: Part Two/)).toBeInTheDocument();
    expect(screen.getAllByText(/Ubuntu-24.04-ISO/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Sonarr TV Automation/)).toBeInTheDocument();
    expect(screen.getByText(/Radarr Movie Automation/)).toBeInTheDocument();
    expect(screen.getByText(/Bazarr Subtitles/)).toBeInTheDocument();
    expect(screen.getByText(/Prowlarr Indexers/)).toBeInTheDocument();
    expect(screen.getByText(/Seerr Media Requests/)).toBeInTheDocument();
    expect(screen.getByText(/Recent Media Collection History \(1 snapshots\)/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Poll Read-Only Media Snapshot" }));
    expect(onCollectSnapshot).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByLabelText("Show resolved"));
    expect(onToggleIncludeResolved).toHaveBeenCalledWith(true);
  });

  it("disables poll button while busy and renders fallback cards when mediaOverview is null", () => {
    render(
      <MediaDashboard
        overview={baseOverview}
        mediaOverview={null}
        mediaAlerts={[]}
        mediaHistory={[]}
        mediaCollectBusy={true}
        includeResolvedMediaAlerts={false}
        onCollectSnapshot={vi.fn()}
        onToggleIncludeResolved={vi.fn()}
      />,
    );

    const pollButton = screen.getByRole("button", { name: "Polling..." });
    expect(pollButton).toBeDisabled();
    expect(screen.getByText("Media connectors disabled.")).toBeInTheDocument();
    expect(screen.getByText("qBittorrent disabled.")).toBeInTheDocument();
  });
});
