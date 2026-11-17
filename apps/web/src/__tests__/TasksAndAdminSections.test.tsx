import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { describe, expect, it, vi } from "vitest";
import {
  ReportsSection,
  ScriptsSection,
  SettingsSection,
} from "../components/sections/AdminSections";
import { TasksSection } from "../components/sections/TasksSection";
import { mockRedactedSettings } from "./fixtures/overviewFixtures";
import {
  mockAuditLogs,
  mockProjects,
  mockReports,
  mockScripts,
  mockTasks,
} from "./fixtures/workspaceFixtures";

describe("Tasks, Scripts, Reports, and Settings Sections", () => {
  it("submits new task and updates task status in TasksSection", async () => {
    const onCreateTask = vi.fn().mockResolvedValue(true);
    const onTaskStatusChange = vi.fn().mockResolvedValue(undefined);

    render(
      <TasksSection
        projects={mockProjects}
        tasks={mockTasks}
        onCreateTask={onCreateTask}
        onTaskStatusChange={onTaskStatusChange}
      />,
    );

    fireEvent.change(screen.getByLabelText("Task Title"), {
      target: { value: "Verify Phase 03 PR" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save Task to SQLite" }));

    await waitFor(() => {
      expect(onCreateTask).toHaveBeenCalledWith(
        expect.objectContaining({ title: "Verify Phase 03 PR" }),
      );
    });

    fireEvent.change(screen.getByLabelText("Status for Verify Web/Core Skeleton"), {
      target: { value: "review" },
    });
    await waitFor(() => {
      expect(onTaskStatusChange).toHaveBeenCalledWith(10, "review");
    });
  });

  it("inspects scripts, reads reports, and displays redacted settings", () => {
    const onSelectScript = vi.fn().mockResolvedValue(undefined);
    const onSelectReport = vi.fn().mockResolvedValue(undefined);

    render(
      <>
        <ScriptsSection
          scripts={mockScripts}
          selectedScript={null}
          onSelectScript={onSelectScript}
        />
        <ReportsSection
          reports={mockReports}
          selectedReport={null}
          auditLogs={mockAuditLogs}
          onSelectReport={onSelectReport}
        />
        <SettingsSection settingsData={mockRedactedSettings} />
      </>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Inspect" }));
    expect(onSelectScript).toHaveBeenCalledWith("disk-usage-report");

    fireEvent.click(screen.getByRole("button", { name: "Read Report" }));
    expect(onSelectReport).toHaveBeenCalledWith("foundation-baseline-report");

    expect(screen.getByText("auth.login_succeeded")).toBeInTheDocument();
    expect(screen.getByText("PROHIBITED")).toBeInTheDocument();
  });
});
