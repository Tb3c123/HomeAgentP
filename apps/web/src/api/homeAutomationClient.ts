import { requestJson } from "./client";
import type {
  DeliveryStatus,
  HaOverviewResponse,
  NotificationDeliveryItem,
  NotificationEvaluateResponse,
  NotificationPreferences,
  NotificationPreferencesUpdate,
} from "./types";

export const homeAutomationClient = {
  getHaOverview: () => requestJson<HaOverviewResponse>("/api/v1/home-assistant/overview"),

  collectHaSnapshot: (csrfToken: string) =>
    requestJson<HaOverviewResponse>(
      "/api/v1/home-assistant/collect",
      { method: "POST" },
      csrfToken,
    ),

  getNotificationPreferences: () =>
    requestJson<NotificationPreferences>("/api/v1/notifications/preferences"),

  updateNotificationPreferences: (
    payload: NotificationPreferencesUpdate,
    csrfToken: string,
  ) =>
    requestJson<NotificationPreferences>(
      "/api/v1/notifications/preferences",
      { method: "PUT", body: JSON.stringify(payload) },
      csrfToken,
    ),

  listNotificationDeliveries: (params?: {
    status?: DeliveryStatus | "";
    limit?: number;
    offset?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.status) qs.set("status", params.status);
    if (params?.limit !== undefined) qs.set("limit", String(params.limit));
    if (params?.offset !== undefined) qs.set("offset", String(params.offset));
    const query = qs.toString();
    return requestJson<NotificationDeliveryItem[]>(
      `/api/v1/notifications/deliveries${query ? `?${query}` : ""}`,
    );
  },

  evaluateNotifications: (csrfToken: string) =>
    requestJson<NotificationEvaluateResponse>(
      "/api/v1/notifications/evaluate",
      { method: "POST" },
      csrfToken,
    ),
};
