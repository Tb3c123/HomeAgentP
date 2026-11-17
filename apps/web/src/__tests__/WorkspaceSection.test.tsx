import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiClient } from "../api/client";
import { workspaceClient } from "../api/workspaceClient";
import { App } from "../App";
import { WorkspaceSection } from "../components/workspace/WorkspaceSection";
import { setupAuthenticatedWorkspaceMocks } from "./fixtures/mockApiSetup";
import { mockAuthUser } from "./fixtures/overviewFixtures";
import {
  mockGitProvenanceLinks,
  mockTaskBriefs,
  mockTasks,
  mockWorkspaceArtifactDetail,
  mockWorkspaceArtifacts,
} from "./fixtures/workspaceFixtures";

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
      getNasStatus: vi.fn(),
      collectNasSnapshot: vi.fn(),
      listNasHistory: vi.fn(),
      listNasAlerts: vi.fn(),
      getMediaOverview: vi.fn(),
      getMediaService: vi.fn(),
      collectMediaSnapshot: vi.fn(),
      listMediaHistory: vi.fn(),
      listMediaAlerts: vi.fn(),
    },
  };
});

vi.mock("../api/workspaceClient", () => ({
  workspaceClient: {
    listTaskBriefs: vi.fn(),
    createTaskBrief: vi.fn(),
    exportTaskBrief: vi.fn(),
    listArtifacts: vi.fn(),
    createArtifact: vi.fn(),
    getArtifactDetail: vi.fn(),
    listProvenance: vi.fn(),
    createProvenance: vi.fn(),
    updateProvenance: vi.fn(),
  },
}));

describe("Phase 04 WorkspaceSection (Task Briefs, Artifacts & Git Provenance)", () => {
  const mockedWorkspace = vi.mocked(workspaceClient);

  beforeEach(() => {
    vi.clearAllMocks();
    mockedWorkspace.listTaskBriefs.mockResolvedValue(mockTaskBriefs);
    mockedWorkspace.listArtifacts.mockResolvedValue(mockWorkspaceArtifacts);
    mockedWorkspace.getArtifactDetail.mockResolvedValue(mockWorkspaceArtifactDetail);
    mockedWorkspace.listProvenance.mockResolvedValue(mockGitProvenanceLinks);
    mockedWorkspace.exportTaskBrief.mockResolvedValue({
      task_id: 10,
      version: 1,
      human_status: "ready_for_handoff",
      handoff_mode: "manual_copy_only",
      rendered_text: "# Task Brief v1\nPurpose: Verify Phase 04 workspace handoff",
    });
  });

  it("navigates to Workspace & Artifacts from App and renders briefs, artifacts, and provenance", async () => {
    setupAuthenticatedWorkspaceMocks();
    render(<App />);

    await screen.findByText("Workspace & Artifacts");
    fireEvent.click(screen.getByRole("button", { name: "Workspace & Artifacts" }));

    expect(
      await screen.findByRole("heading", { name: "Workspace, Task Briefs & Artifacts" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("Verify Phase 04 workspace handoff")).toBeInTheDocument();
    expect(await screen.findByText("Phase 04 Workspace Plan")).toBeInTheDocument();
    expect(await screen.findByText("Manual (unverified)")).toBeInTheDocument();
    expect(vi.mocked(apiClient).getMe).toHaveBeenCalledTimes(1);
  });

  it("creates a task brief version and copies exported handoff text", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });

    mockedWorkspace.createTaskBrief.mockResolvedValueOnce({
      ...mockTaskBriefs[0],
      id: 2,
      version: 2,
      purpose: "Second brief version",
    });

    render(<WorkspaceSection user={mockAuthUser} tasks={mockTasks} />);

    await screen.findByText("Verify Phase 04 workspace handoff");

    fireEvent.change(screen.getByLabelText("Purpose"), {
      target: { value: "Second brief version" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create Brief Version" }));

    await waitFor(() => {
      expect(mockedWorkspace.createTaskBrief).toHaveBeenCalledWith(
        10,
        expect.objectContaining({
          purpose: "Second brief version",
          expected_latest_version: 1,
        }),
        mockAuthUser.csrf_token,
      );
    });
    expect(await screen.findByText("Created Task Brief v2.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Copy Handoff Brief v1" }));
    await waitFor(() => {
      expect(mockedWorkspace.exportTaskBrief).toHaveBeenCalledWith(10, 1);
      expect(writeText).toHaveBeenCalledWith(
        "# Task Brief v1\nPurpose: Verify Phase 04 workspace handoff",
      );
    });
    expect(await screen.findByLabelText("Exported Task Brief")).toBeInTheDocument();
  });

  it("filters artifacts, opens read-only preview with SHA-256 badge, and attaches provenance", async () => {
    mockedWorkspace.createProvenance.mockResolvedValueOnce({
      ...mockGitProvenanceLinks[0],
      id: 2,
      branch: "feature/test-link",
    });

    render(<WorkspaceSection user={mockAuthUser} tasks={mockTasks} />);
    await screen.findByText("Phase 04 Workspace Plan");

    fireEvent.change(screen.getByLabelText("Filter artifact kind"), {
      target: { value: "plan" },
    });
    await waitFor(() => {
      expect(mockedWorkspace.listArtifacts).toHaveBeenCalledWith(
        expect.objectContaining({ kind: "plan", offset: 0 }),
      );
    });

    fireEvent.click(screen.getByRole("button", { name: "Preview" }));
    expect(await screen.findByText("SHA-256 Verified")).toBeInTheDocument();
    expect(await screen.findByText(/All NAS mounts healthy\./)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Provenance branch"), {
      target: { value: "feature/test-link" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Attach Git Provenance" }));

    await waitFor(() => {
      expect(mockedWorkspace.createProvenance).toHaveBeenCalledWith(
        expect.objectContaining({
          entity_type: "task",
          entity_id: 10,
          branch: "feature/test-link",
        }),
        mockAuthUser.csrf_token,
      );
    });
  });

  it("enforces viewer read-only mode and surfaces backend API errors", async () => {
    const viewerUser = { ...mockAuthUser, username: "nas_viewer", role: "viewer" as const };
    mockedWorkspace.listArtifacts.mockRejectedValueOnce(
      new ApiError(403, "Forbidden: owner role required"),
    );

    render(<WorkspaceSection user={viewerUser} tasks={mockTasks} />);

    expect(await screen.findByText(/Viewer Read-Only Mode:/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create Brief Version" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Register Artifact" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Attach Git Provenance" })).not.toBeInTheDocument();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Forbidden: owner role required",
    );
  });
});
