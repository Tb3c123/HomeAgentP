import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { apiClient } from "../api/client";
import { setupAuthenticatedWorkspaceMocks } from "./fixtures/mockApiSetup";

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

describe("Authentication & Navigation", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("renders login screen when session is unauthenticated", async () => {
    vi.mocked(apiClient).getMe.mockRejectedValueOnce(new Error("Unauthorized"));

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/Sign in to Dashboard/i)).toBeInTheDocument();
    });
  });

  it("renders honest overview states and navigates across all workspace sections", async () => {
    const mockedClient = setupAuthenticatedWorkspaceMocks();

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("System Overview")).toBeInTheDocument();
    });

    expect(screen.getByText("Mount /mnt/disk1")).toBeInTheDocument();
    expect(screen.getByText("Mount /mnt/disk2")).toBeInTheDocument();
    expect(mockedClient.listNasAlerts).toHaveBeenCalledWith(false);
    expect(mockedClient.listMediaAlerts).toHaveBeenCalledWith(false);

    fireEvent.click(screen.getByRole("button", { name: /^NAS Guardian$/i }));
    expect(
      screen.getByText(/NAS Guardian \(CPU, RAM, Mount Guardian & Container Health\)/i),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Media & Downloads/i }));
    expect(
      screen.getByText(/Media & Downloads Monitoring Hub \(Phase 03 Read-Only\)/i),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Tasks & AI Handoff/i }));
    expect(screen.getByText("Verify Web/Core Skeleton")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Scripts Registry/i }));
    expect(screen.getByText("NAS Disk Usage Snapshot")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Settings & Safety/i }));
    expect(
      screen.getByText("Runtime Settings & Enforced B+ Safety Constraints"),
    ).toBeInTheDocument();
    expect(screen.getByText("PROHIBITED")).toBeInTheDocument();
  });
});
