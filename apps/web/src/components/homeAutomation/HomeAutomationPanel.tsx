import React from "react";
import type { AuthUser } from "../../api/types";
import { useHomeAutomationData } from "../../hooks/useHomeAutomationData";
import { HaOverviewPanel } from "./HaOverviewPanel";
import { NotificationDeliveriesPanel } from "./NotificationDeliveriesPanel";
import { NotificationPreferencesPanel } from "./NotificationPreferencesPanel";

interface HomeAutomationPanelProps {
  user: AuthUser;
}

export const HomeAutomationPanel: React.FC<HomeAutomationPanelProps> = ({ user }) => {
  const {
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
    handleCollectHa,
    handleSavePreferences,
    handleEvaluateNotifications,
    handleStatusFilterChange,
    handlePrevPage,
    handleNextPage,
  } = useHomeAutomationData(user);

  return (
    <section aria-label="Home Automation and Notifications">
      {errorMsg && (
        <div className="banner-error" role="alert" style={{ marginBottom: "1rem" }}>
          {errorMsg}
        </div>
      )}

      <HaOverviewPanel
        haOverview={haOverview}
        isOwner={isOwner}
        collectBusy={busyAction === "ha_collect"}
        onCollect={() => void handleCollectHa()}
      />

      <NotificationPreferencesPanel
        preferences={preferences}
        isOwner={isOwner}
        saveBusy={busyAction === "prefs_save"}
        evaluateBusy={busyAction === "evaluate"}
        lastEvaluate={lastEvaluate}
        onSave={(payload) => void handleSavePreferences(payload)}
        onEvaluate={() => void handleEvaluateNotifications()}
      />

      <NotificationDeliveriesPanel
        deliveries={deliveries}
        statusFilter={statusFilter}
        offset={offset}
        loading={loading}
        onStatusFilterChange={handleStatusFilterChange}
        onPrevPage={handlePrevPage}
        onNextPage={handleNextPage}
      />
    </section>
  );
};
