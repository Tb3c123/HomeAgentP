import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { homeAutomationClient } from "../api/homeAutomationClient";
import type {
  AuthUser,
  HaOverviewResponse,
  NotificationDeliveryItem,
  NotificationPreferences,
} from "../api/types";
import { HomeAutomationPanel } from "../components/homeAutomation/HomeAutomationPanel";

vi.mock("../api/homeAutomationClient", () => ({
  homeAutomationClient: {
    getHaOverview: vi.fn(),
    collectHaSnapshot: vi.fn(),
    getNotificationPreferences: vi.fn(),
    updateNotificationPreferences: vi.fn(),
    listNotificationDeliveries: vi.fn(),
    evaluateNotifications: vi.fn(),
  },
}));

const ownerUser: AuthUser = {
  username: "admin",
  role: "owner",
  csrf_token: "owner-csrf-token",
  expires_at: "2026-11-17T23:59:59Z",
};

const viewerUser: AuthUser = {
  username: "viewer1",
  role: "viewer",
  csrf_token: "viewer-csrf-token",
  expires_at: "2026-11-17T23:59:59Z",
};

const disabledHa: HaOverviewResponse = {
  status: "unavailable",
  enabled: false,
  reason: "Home Assistant integration is disabled (opt-in).",
  collected_at: null,
  entity_count: 0,
  entities: [],
};

const onlineHa: HaOverviewResponse = {
  status: "online",
  enabled: true,
  reason: "Collected 1/1 allowlisted entities.",
  collected_at: "2026-11-17T14:00:00Z",
  entity_count: 1,
  entities: [
    {
      entity_id: "sensor.nas_ups_load",
      domain: "sensor",
      friendly_name: "NAS UPS Load",
      state: "22",
      attributes: { unit_of_measurement: "%" },
      status: "online",
      last_changed: "2026-11-17T13:55:00Z",
      collected_at: "2026-11-17T14:00:00Z",
    },
  ],
};

const unconfiguredPrefs: NotificationPreferences = {
  telegram_enabled: false,
  min_severity: "warning",
  notify_on_resolve: true,
  cooldown_seconds: 900,
  rate_limit_count: 10,
  rate_limit_window_seconds: 300,
  destination_count: 0,
  telegram_configured: false,
  updated_by: "system",
  updated_at: "",
};

const makeDelivery = (id: number): NotificationDeliveryItem => ({
  id,
  incident_key: `nas:disk_${id}:t1:triggered`,
  source_domain: "nas",
  severity: "warning",
  channel: "telegram",
  destination_masked: "***6789",
  message_redacted: `Alert message ${id}`,
  status: "sent",
  claimed_by: "",
  lease_expires_at: null,
  attempt_count: 1,
  next_attempt_at: null,
  last_error_redacted: "",
  created_at: "2026-11-17T14:00:00Z",
  sent_at: "2026-11-17T14:00:05Z",
});

describe("HomeAutomationPanel (P05-F05)", () => {
  const mockedClient = vi.mocked(homeAutomationClient);

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("displays clear disabled/not-configured messaging when HA and Telegram are disabled", async () => {
    mockedClient.getHaOverview.mockResolvedValueOnce(disabledHa);
    mockedClient.getNotificationPreferences.mockResolvedValueOnce(unconfiguredPrefs);
    mockedClient.listNotificationDeliveries.mockResolvedValueOnce([]);

    render(<HomeAutomationPanel user={ownerUser} />);

    expect(await screen.findByText(/Home Assistant Disabled \(Opt-In\):/i)).toBeTruthy();
    expect(screen.getByText(/Telegram Not Configured \/ Disabled:/i)).toBeTruthy();
    expect(
      (screen.getByRole("button", { name: /Collect HA Snapshot/i }) as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it("allows owner to collect HA, save preferences, and paginate delivery history", async () => {
    const page1 = Array.from({ length: 10 }, (_, idx) => makeDelivery(idx + 1));
    const page2 = [makeDelivery(11)];

    mockedClient.getHaOverview.mockResolvedValue(onlineHa);
    mockedClient.collectHaSnapshot.mockResolvedValue({
      ...onlineHa,
      status: "stale",
      reason: "Last Home Assistant snapshot is stale (400s old).",
    });
    mockedClient.getNotificationPreferences.mockResolvedValue({
      ...unconfiguredPrefs,
      telegram_configured: true,
      destination_count: 1,
    });
    mockedClient.updateNotificationPreferences.mockResolvedValue({
      ...unconfiguredPrefs,
      telegram_enabled: true,
      telegram_configured: true,
      destination_count: 1,
      cooldown_seconds: 600,
    });
    mockedClient.listNotificationDeliveries.mockImplementation(async (params) =>
      params?.offset === 10 ? page2 : page1,
    );

    render(<HomeAutomationPanel user={ownerUser} />);

    expect(await screen.findByText("NAS UPS Load")).toBeTruthy();
    expect(screen.getByText("22 %")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /Collect HA Snapshot/i }));
    await waitFor(() =>
      expect(mockedClient.collectHaSnapshot).toHaveBeenCalledWith("owner-csrf-token"),
    );
    expect(await screen.findByText(/Status \(STALE\):/i)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /Save Preferences/i }));
    await waitFor(() =>
      expect(mockedClient.updateNotificationPreferences).toHaveBeenCalledWith(
        expect.objectContaining({ min_severity: "warning" }),
        "owner-csrf-token",
      ),
    );

    // Pagination Next -> offset 10
    const nextBtn = screen.getByRole("button", { name: "Next" }) as HTMLButtonElement;
    expect(nextBtn.disabled).toBe(false);
    fireEvent.click(nextBtn);
    expect(await screen.findByText("Alert message 11")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Next" }) as HTMLButtonElement).disabled).toBe(
      true,
    );
    expect((screen.getByRole("button", { name: "Previous" }) as HTMLButtonElement).disabled).toBe(
      false,
    );
  });

  it("enforces read-only controls for viewer role", async () => {
    mockedClient.getHaOverview.mockResolvedValueOnce(onlineHa);
    mockedClient.getNotificationPreferences.mockResolvedValueOnce(unconfiguredPrefs);
    mockedClient.listNotificationDeliveries.mockResolvedValueOnce([makeDelivery(1)]);

    render(<HomeAutomationPanel user={viewerUser} />);

    expect(await screen.findByText(/Viewer role: read-only/i)).toBeTruthy();
    expect(screen.getByText(/Viewer role: notification preferences are read-only/i)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Save Preferences/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /Collect HA Snapshot/i })).toBeNull();
  });
});
