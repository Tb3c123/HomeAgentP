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

  it("supports artifact pagination, resets offset on filter change, and ignores stale responses", async () => {
    const page1 = Array.from({ length: 20 }, (_, idx) => ({
      ...mockWorkspaceArtifacts[0],
      id: idx + 1,
      slug: `artifact-${idx + 1}`,
      title: `Artifact ${idx + 1}`,
    }));
    const page2 = [
      {
        ...mockWorkspaceArtifacts[0],
        id: 21,
        slug: "artifact-21",
        title: "Artifact 21",
      },
    ];

    let resolveStale!: (value: typeof page1) => void;
    const stalePromise = new Promise<typeof page1>((res) => {
      resolveStale = res;
    });

    mockedWorkspace.listArtifacts
      .mockResolvedValueOnce(page1)
      .mockResolvedValueOnce(page2)
      .mockReturnValueOnce(stalePromise)
      .mockResolvedValueOnce([
        {
          ...mockWorkspaceArtifacts[0],
          id: 99,
          slug: "fresh-filtered",
          title: "Fresh Filtered Artifact",
        },
      ]);

    render(<WorkspaceSection user={mockAuthUser} tasks={mockTasks} />);
    await screen.findByText("Artifact 1");

    const prevBtn = screen.getByRole("button", { name: "Previous" });
    const nextBtn = screen.getByRole("button", { name: "Next" });
    expect(prevBtn).toBeDisabled();
    expect(nextBtn).toBeEnabled();

    fireEvent.click(nextBtn);
    await screen.findByText("Artifact 21");
    expect(prevBtn).toBeEnabled();
    expect(nextBtn).toBeDisabled();

    // Trigger filter 1 (slow) then filter 2 (fast) -> offset resets to 0 and stale response is ignored
    fireEvent.change(screen.getByLabelText("Filter artifact tag"), {
      target: { value: "slow" },
    });
    fireEvent.change(screen.getByLabelText("Filter artifact tag"), {
      target: { value: "fast" },
    });

    await screen.findByText("Fresh Filtered Artifact");
    resolveStale(page1);
    await waitFor(() => {
      expect(screen.getByText("Fresh Filtered Artifact")).toBeInTheDocument();
      expect(screen.queryByText("Artifact 1")).not.toBeInTheDocument();
    });
    expect(mockedWorkspace.listArtifacts).toHaveBeenLastCalledWith(
      expect.objectContaining({ tag: "fast", offset: 0, limit: 20 }),
    );
  });

  it("prepares next artifact revision and handles 409 conflicts with refresh guidance", async () => {
    mockedWorkspace.createArtifact.mockRejectedValueOnce(
      new ApiError(409, "Revision conflict: expected latest revision 1, found 2."),
    );

    render(<WorkspaceSection user={mockAuthUser} tasks={mockTasks} />);
    await screen.findByText("Phase 04 Workspace Plan");

    fireEvent.click(screen.getByRole("button", { name: "New Revision" }));
    expect(screen.getByText(/Preparing next revision for/)).toBeInTheDocument();
    expect(screen.getByLabelText("Artifact slug")).toHaveValue("phase-04-plan");

    fireEvent.change(screen.getByLabelText("Artifact version"), {
      target: { value: "1.1.0" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Publish New Revision" }));

    await waitFor(() => {
      expect(mockedWorkspace.createArtifact).toHaveBeenCalledWith(
        expect.objectContaining({
          slug: "phase-04-plan",
          version: "1.1.0",
          expected_latest_revision: 1,
        }),
        mockAuthUser.csrf_token,
      );
    });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /Refreshed artifact list — please review latest revision and retry\./,
    );
  });
});
