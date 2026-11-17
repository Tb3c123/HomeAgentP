import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { NasGuardianSection } from "../components/sections/NasGuardianSection";
import { setupAuthenticatedWorkspaceMocks } from "./fixtures/mockApiSetup";
import {
  mockNasActiveAlert,
  mockNasHistory,
  mockNasResolvedAlert,
  mockNasStatus,
} from "./fixtures/nasFixtures";

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

describe("NAS Guardian Section", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("renders host snapshot, unmounted fallback, and toggles resolved NAS alerts via App", async () => {
    const mockedClient = setupAuthenticatedWorkspaceMocks();

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("System Overview")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /^NAS Guardian$/i }));
    expect(screen.getByText("HOST_SNAPSHOT")).toBeInTheDocument();
    expect(screen.getByText("UNMOUNTED_FALLBACK")).toBeInTheDocument();
    expect(
      screen.getByText(
        /Mount \/mnt\/disk2 is UNMOUNTED \(directory fell back to root filesystem \/\)\./i,
      ),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(/Show resolved/i));
    await waitFor(() => {
      expect(mockedClient.listNasAlerts).toHaveBeenCalledWith(true);
      expect(screen.getByText("CPU usage was elevated.")).toBeInTheDocument();
      expect(screen.getByText("RESOLVED")).toBeInTheDocument();
    });
  });

  it("triggers manual snapshot collection and renders history in NasGuardianSection", () => {
    const onCollectSnapshot = vi.fn();
    const onToggleIncludeResolved = vi.fn();

    render(
      <NasGuardianSection
        nasStatus={mockNasStatus}
        nasAlerts={[mockNasActiveAlert, mockNasResolvedAlert]}
        nasHistory={mockNasHistory}
        nasCollectBusy={false}
        includeResolvedAlerts={true}
        onCollectSnapshot={onCollectSnapshot}
        onToggleIncludeResolved={onToggleIncludeResolved}
      />,
    );

    expect(screen.getByText(/Recent Metrics History \(1 snapshots\)/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Collect Read-Only Snapshot" }));
    expect(onCollectSnapshot).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByLabelText("Show resolved"));
    expect(onToggleIncludeResolved).toHaveBeenCalledWith(false);
  });
});
