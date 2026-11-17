import { useCallback, useEffect, useState } from "react";
import { homeAutomationClient } from "../api/homeAutomationClient";
import type {
  AuthUser,
  DeliveryStatus,
  HaOverviewResponse,
  NotificationDeliveryItem,
  NotificationEvaluateResponse,
  NotificationPreferences,
  NotificationPreferencesUpdate,
} from "../api/types";

export const DELIVERIES_PAGE_LIMIT = 10;

export function useHomeAutomationData(user: AuthUser) {
  const [haOverview, setHaOverview] = useState<HaOverviewResponse | null>(null);
  const [preferences, setPreferences] = useState<NotificationPreferences | null>(null);
  const [deliveries, setDeliveries] = useState<NotificationDeliveryItem[]>([]);
  const [statusFilter, setStatusFilter] = useState<DeliveryStatus | "">("");
  const [offset, setOffset] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(true);
  const [busyAction, setBusyAction] = useState<string>("");
  const [errorMsg, setErrorMsg] = useState<string>("");
  const [lastEvaluate, setLastEvaluate] = useState<NotificationEvaluateResponse | null>(null);

  const isOwner = user.role === "owner";

  const loadAll = useCallback(
    async (nextStatus: DeliveryStatus | "" = statusFilter, nextOffset: number = offset) => {
      setLoading(true);
      setErrorMsg("");
      try {
        const [ha, prefs, deliv] = await Promise.all([
          homeAutomationClient.getHaOverview(),
          homeAutomationClient.getNotificationPreferences(),
          homeAutomationClient.listNotificationDeliveries({
            status: nextStatus,
            limit: DELIVERIES_PAGE_LIMIT,
            offset: nextOffset,
          }),
        ]);
        setHaOverview(ha);
        setPreferences(prefs);
        setDeliveries(deliv);
      } catch (err) {
        setErrorMsg(err instanceof Error ? err.message : "Failed to load Home Automation data.");
      } finally {
        setLoading(false);
      }
    },
    [statusFilter, offset],
  );

  useEffect(() => {
    void loadAll(statusFilter, offset);
  }, [loadAll, statusFilter, offset]);

  const handleCollectHa = async () => {
    if (!isOwner) return;
    setBusyAction("ha_collect");
    setErrorMsg("");
    try {
      const updated = await homeAutomationClient.collectHaSnapshot(user.csrf_token);
      setHaOverview(updated);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to collect HA snapshot.");
    } finally {
      setBusyAction("");
    }
  };

  const handleSavePreferences = async (payload: NotificationPreferencesUpdate) => {
    if (!isOwner) return;
    setBusyAction("prefs_save");
    setErrorMsg("");
    try {
      const updated = await homeAutomationClient.updateNotificationPreferences(
        payload,
        user.csrf_token,
      );
      setPreferences(updated);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to save notification preferences.");
    } finally {
      setBusyAction("");
    }
  };

  const handleEvaluateNotifications = async () => {
    if (!isOwner) return;
    setBusyAction("evaluate");
    setErrorMsg("");
    try {
      const result = await homeAutomationClient.evaluateNotifications(user.csrf_token);
      setLastEvaluate(result);
      const deliv = await homeAutomationClient.listNotificationDeliveries({
        status: statusFilter,
        limit: DELIVERIES_PAGE_LIMIT,
        offset,
      });
      setDeliveries(deliv);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to evaluate notifications.");
    } finally {
      setBusyAction("");
    }
  };

  const handleStatusFilterChange = (nextStatus: DeliveryStatus | "") => {
    setStatusFilter(nextStatus);
    setOffset(0);
  };

  const handlePrevPage = () => {
    setOffset((prev) => Math.max(0, prev - DELIVERIES_PAGE_LIMIT));
  };

  const handleNextPage = () => {
    if (deliveries.length === DELIVERIES_PAGE_LIMIT) {
      setOffset((prev) => prev + DELIVERIES_PAGE_LIMIT);
    }
  };

  return {
    haOverview,
    preferences,
    deliveries,
    statusFilter,
    offset,
    loading,
    busyAction,
    errorMsg,
    lastEvaluate,
    isOwner,
    refreshAll: () => loadAll(statusFilter, offset),
    handleCollectHa,
    handleSavePreferences,
    handleEvaluateNotifications,
    handleStatusFilterChange,
    handlePrevPage,
    handleNextPage,
  };
}
