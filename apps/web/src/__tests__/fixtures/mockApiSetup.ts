import { vi } from "vitest";
import { apiClient } from "../../api/client";
import {
  mockMediaActiveAlert,
  mockMediaHistory,
  mockMediaOverview,
  mockMediaResolvedAlert,
} from "./mediaFixtures";
import {
  mockNasActiveAlert,
  mockNasHistory,
  mockNasResolvedAlert,
  mockNasStatus,
} from "./nasFixtures";
import { createMockOverview, mockAuthUser, mockRedactedSettings } from "./overviewFixtures";
import {
  mockAuditLogs,
  mockProjects,
  mockReports,
  mockScripts,
  mockTasks,
} from "./workspaceFixtures";

export function setupAuthenticatedWorkspaceMocks() {
  const mockedClient = vi.mocked(apiClient);

  mockedClient.getMe.mockResolvedValueOnce(mockAuthUser);
  mockedClient.getOverview.mockResolvedValue(createMockOverview());
  mockedClient.getNasStatus.mockResolvedValue(mockNasStatus);
  mockedClient.listNasHistory.mockResolvedValue(mockNasHistory);
  mockedClient.listNasAlerts.mockImplementation(async (includeResolved?: boolean) =>
    includeResolved ? [mockNasActiveAlert, mockNasResolvedAlert] : [mockNasActiveAlert],
  );
  mockedClient.getMediaOverview.mockResolvedValue(mockMediaOverview);
  mockedClient.listMediaHistory.mockResolvedValue(mockMediaHistory);
  mockedClient.listMediaAlerts.mockImplementation(async (includeResolved?: boolean) =>
    includeResolved ? [mockMediaActiveAlert, mockMediaResolvedAlert] : [mockMediaActiveAlert],
  );
  mockedClient.listProjects.mockResolvedValue(mockProjects);
  mockedClient.listTasks.mockResolvedValue(mockTasks);
  mockedClient.listScripts.mockResolvedValue(mockScripts);
  mockedClient.listReports.mockResolvedValue(mockReports);
  mockedClient.listAuditLogs.mockResolvedValue(mockAuditLogs);
  mockedClient.getSettings.mockResolvedValue(mockRedactedSettings);

  return mockedClient;
}
