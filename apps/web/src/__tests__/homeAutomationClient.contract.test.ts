import { afterEach, describe, expect, it, vi } from "vitest";
import { homeAutomationClient } from "../api/homeAutomationClient";

describe("homeAutomationClient API contract", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("calls expected Phase 05 HA and Notification endpoints with CSRF headers", async () => {
    const fetchMock = vi.fn().mockImplementation(
      async () =>
        new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await homeAutomationClient.getHaOverview();
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/home-assistant/overview",
      expect.objectContaining({ credentials: "include" }),
    );

    await homeAutomationClient.collectHaSnapshot("csrf-owner-1");
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/home-assistant/collect",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
      }),
    );
    const collectHeaders = fetchMock.mock.calls.at(-1)?.[1]?.headers as Headers;
    expect(collectHeaders.get("X-CSRF-Token")).toBe("csrf-owner-1");

    await homeAutomationClient.updateNotificationPreferences(
      {
        telegram_enabled: true,
        min_severity: "warning",
        notify_on_resolve: true,
        cooldown_seconds: 600,
        rate_limit_count: 5,
        rate_limit_window_seconds: 300,
      },
      "csrf-owner-2",
    );
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/notifications/preferences",
      expect.objectContaining({ method: "PUT", credentials: "include" }),
    );
    const prefsHeaders = fetchMock.mock.calls.at(-1)?.[1]?.headers as Headers;
    expect(prefsHeaders.get("X-CSRF-Token")).toBe("csrf-owner-2");

    await homeAutomationClient.listNotificationDeliveries({
      status: "failed",
      limit: 10,
      offset: 20,
    });
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/notifications/deliveries?status=failed&limit=10&offset=20",
      expect.objectContaining({ credentials: "include" }),
    );

    await homeAutomationClient.evaluateNotifications("csrf-owner-3");
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/notifications/evaluate",
      expect.objectContaining({ method: "POST", credentials: "include" }),
    );
  });
});
