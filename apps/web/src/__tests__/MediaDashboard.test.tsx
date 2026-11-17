import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { MediaDashboard } from "../components/media/MediaDashboard";
import {
  mockMediaActiveAlert,
  mockMediaHistory,
  mockMediaOverview,
} from "./fixtures/mediaFixtures";
import { setupAuthenticatedWorkspaceMocks } from "./fixtures/mockApiSetup";
import { createMockOverview } from "./fixtures/overviewFixtures";

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

describe("MediaDashboard interactions", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("renders all media cards, triggers snapshot poll, and toggles resolved alerts", () => {
    const onCollectSnapshot = vi.fn();
    const onToggleIncludeResolved = vi.fn();
    const overview = createMockOverview();

    render(
      <MediaDashboard
        overview={overview}
        mediaOverview={mockMediaOverview}
        mediaAlerts={[mockMediaActiveAlert]}
        mediaHistory={mockMediaHistory}
        mediaCollectBusy={false}
        includeResolvedMediaAlerts={false}
        onCollectSnapshot={onCollectSnapshot}
        onToggleIncludeResolved={onToggleIncludeResolved}
      />,
    );

    expect(screen.getByText(/Dune: Part Two/)).toBeInTheDocument();
    expect(screen.getByText(/Linux-ISO-x86_64/)).toBeInTheDocument();
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
    const overview = createMockOverview({
      domains: {
        ...createMockOverview().domains,
        media: {
          title: "Media Services",
          status: "not_configured",
          phase: "phase-03",
          reason: "Media connectors disabled.",
          services: { jellyfin: "not_configured" },
        },
        downloads: {
          title: "qBittorrent Downloads",
          status: "not_configured",
          phase: "phase-03",
          reason: "qBittorrent disabled.",
          metrics: { active_torrents: "unavailable" },
        },
      },
    });

    render(
      <MediaDashboard
        overview={overview}
        mediaOverview={null}
        mediaAlerts={[]}
        mediaHistory={[]}
        mediaCollectBusy={true}
        includeResolvedMediaAlerts={false}
        onCollectSnapshot={vi.fn()}
        onToggleIncludeResolved={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "Polling..." })).toBeDisabled();
    expect(screen.getByText("Media connectors disabled.")).toBeInTheDocument();
    expect(screen.getByText("qBittorrent disabled.")).toBeInTheDocument();
  });

  it("toggles resolved media alerts and triggers CSRF-protected media poll from App", async () => {
    const mockedClient = setupAuthenticatedWorkspaceMocks();
    mockedClient.collectMediaSnapshot.mockResolvedValueOnce(mockMediaOverview);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("System Overview")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Media & Downloads/i }));
    expect(screen.getByText("Dune: Part Two")).toBeInTheDocument();
    expect(screen.getByText("Severance")).toBeInTheDocument();
    expect(screen.getByText("Linux-ISO-x86_64")).toBeInTheDocument();
    expect(
      screen.getByText(/qBittorrent has 1 stalled torrent\(s\) exceeding 1800s threshold\./i),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(/Show resolved/i));
    await waitFor(() => {
      expect(mockedClient.listMediaAlerts).toHaveBeenCalledWith(true);
      expect(screen.getByText("Prowlarr had 1 failing indexer.")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Poll Read-Only Media Snapshot/i }));
    await waitFor(() => {
      expect(mockedClient.collectMediaSnapshot).toHaveBeenCalledWith("csrf_test_token_12345");
    });
  });
});
