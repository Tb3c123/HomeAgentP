import type {
  MediaAlertItem,
  MediaHistoryItem,
  MediaOverviewResponse,
  OverviewResponse,
} from "../../api/types";
import { ArrSuiteCards } from "./ArrSuiteCards";
import { AuxMediaCards } from "./AuxMediaCards";
import { JellyfinCard } from "./JellyfinCard";
import { MediaAlertsHistory } from "./MediaAlertsHistory";
import { MediaFallbackCards, MediaOverviewCards } from "./MediaOverviewCards";
import { QBittorrentCard } from "./QBittorrentCard";

interface MediaDashboardProps {
  overview: OverviewResponse;
  mediaOverview: MediaOverviewResponse | null;
  mediaAlerts: MediaAlertItem[];
  mediaHistory: MediaHistoryItem[];
  mediaCollectBusy: boolean;
  includeResolvedMediaAlerts: boolean;
  onCollectSnapshot: () => void | Promise<void>;
  onToggleIncludeResolved: (checked: boolean) => void | Promise<void>;
}

export function MediaDashboard({
  overview,
  mediaOverview,
  mediaAlerts,
  mediaHistory,
  mediaCollectBusy,
  includeResolvedMediaAlerts,
  onCollectSnapshot,
  onToggleIncludeResolved,
}: MediaDashboardProps) {
  return (
    <section aria-label="Media and Downloads Details">
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
        <h2 style={{ margin: 0 }}>Media &amp; Downloads Monitoring Hub (Phase 03 Read-Only)</h2>
        <button
          type="button"
          className="btn"
          onClick={() => void onCollectSnapshot()}
          disabled={mediaCollectBusy}
        >
          {mediaCollectBusy ? "Polling..." : "Poll Read-Only Media Snapshot"}
        </button>
      </div>

      {mediaOverview ? (
        <>
          <MediaOverviewCards mediaOverview={mediaOverview} />

          <div className="card-grid">
            <JellyfinCard service={mediaOverview.services.jellyfin} />
            <QBittorrentCard service={mediaOverview.services.qbittorrent} />
          </div>

          <ArrSuiteCards
            sonarr={mediaOverview.services.sonarr}
            radarr={mediaOverview.services.radarr}
          />

          <AuxMediaCards
            bazarr={mediaOverview.services.bazarr}
            prowlarr={mediaOverview.services.prowlarr}
            seerr={mediaOverview.services.seerr}
          />

          <MediaAlertsHistory
            mediaAlerts={mediaAlerts}
            overviewAlerts={mediaOverview.alerts}
            mediaHistory={mediaHistory}
            includeResolvedMediaAlerts={includeResolvedMediaAlerts}
            onToggleIncludeResolved={onToggleIncludeResolved}
          />
        </>
      ) : (
        <MediaFallbackCards overview={overview} />
      )}
    </section>
  );
}
