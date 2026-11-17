import type { NasAlertItem, NasHistoryItem, NasStatusResponse } from "../../api/types";
import { NasContainersAlertsHistory } from "../nas/NasContainersAlertsHistory";
import { NasMetricsCards } from "../nas/NasMetricsCards";
import { NasMountsCard } from "../nas/NasMountsCard";

interface NasGuardianSectionProps {
  nasStatus: NasStatusResponse | null;
  nasAlerts: NasAlertItem[];
  nasHistory: NasHistoryItem[];
  nasCollectBusy: boolean;
  includeResolvedAlerts: boolean;
  onCollectSnapshot: () => void | Promise<void>;
  onToggleIncludeResolved: (checked: boolean) => void | Promise<void>;
}

export function NasGuardianSection({
  nasStatus,
  nasAlerts,
  nasHistory,
  nasCollectBusy,
  includeResolvedAlerts,
  onCollectSnapshot,
  onToggleIncludeResolved,
}: NasGuardianSectionProps) {
  return (
    <section aria-label="NAS Guardian Details">
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "0.75rem",
          marginBottom: "1rem",
        }}
      >
        <h2 style={{ margin: 0 }}>
          NAS Guardian (CPU, RAM, Mount Guardian &amp; Container Health)
        </h2>
        <button
          type="button"
          className="btn"
          onClick={() => void onCollectSnapshot()}
          disabled={nasCollectBusy}
        >
          {nasCollectBusy ? "Collecting..." : "Collect Read-Only Snapshot"}
        </button>
      </div>

      {nasStatus ? (
        <>
          <NasMetricsCards nasStatus={nasStatus} />
          <NasMountsCard mounts={nasStatus.mounts} />
          <NasContainersAlertsHistory
            nasStatus={nasStatus}
            nasAlerts={nasAlerts}
            nasHistory={nasHistory}
            includeResolvedAlerts={includeResolvedAlerts}
            onToggleIncludeResolved={onToggleIncludeResolved}
          />
        </>
      ) : (
        <div className="card">
          <p>Loading NAS Guardian status...</p>
        </div>
      )}
    </section>
  );
}
