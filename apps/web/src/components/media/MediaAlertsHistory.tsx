import type { MediaAlertItem, MediaHistoryItem } from "../../api/types";
import { formatSpeedBps } from "../../utils/format";
import { StatusBadge } from "../StatusBadge";

interface MediaAlertsHistoryProps {
  mediaAlerts: MediaAlertItem[];
  overviewAlerts: MediaAlertItem[];
  mediaHistory: MediaHistoryItem[];
  includeResolvedMediaAlerts: boolean;
  onToggleIncludeResolved: (checked: boolean) => void | Promise<void>;
}

export function MediaAlertsHistory({
  mediaAlerts,
  overviewAlerts,
  mediaHistory,
  includeResolvedMediaAlerts,
  onToggleIncludeResolved,
}: MediaAlertsHistoryProps) {
  return (
    <div className="card-grid">
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">
            Unified Media &amp; Download Alerts ({mediaAlerts.length})
          </h3>
          <div style={{ display: "flex", gap: "0.65rem", alignItems: "center" }}>
            <label
              style={{
                fontSize: "0.78rem",
                display: "flex",
                alignItems: "center",
                gap: "0.3rem",
                margin: 0,
                cursor: "pointer",
              }}
            >
              <input
                type="checkbox"
                checked={includeResolvedMediaAlerts}
                onChange={(e) => void onToggleIncludeResolved(e.target.checked)}
              />
              Show resolved
            </label>
            <StatusBadge
              value={
                overviewAlerts.some((a) => a.severity === "critical")
                  ? "critical"
                  : overviewAlerts.length > 0
                    ? "warning"
                    : "ok"
              }
            />
          </div>
        </div>
        {mediaAlerts.length === 0 ? (
          <p style={{ fontSize: "0.84rem", color: "var(--text-muted)" }}>
            No active Media or Downloads alerts.
          </p>
        ) : (
          <ul className="kv-list">
            {mediaAlerts.slice(0, 10).map((alert) => (
              <li key={`${alert.id ?? alert.alert_key}-${alert.status}`}>
                <div>
                  <strong>{alert.service}</strong> · {alert.target} ({alert.code})
                  <div style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                    {alert.message}
                  </div>
                  {alert.first_seen_at && (
                    <div style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
                      First: <code>{alert.first_seen_at}</code> · Last:{" "}
                      <code>{alert.last_seen_at}</code>
                      {alert.occurrences ? ` · Count: ${alert.occurrences}` : ""}
                      {alert.resolved_at ? ` · Resolved: ${alert.resolved_at}` : ""}
                    </div>
                  )}
                </div>
                <div style={{ display: "flex", gap: "0.4rem", alignItems: "center" }}>
                  <StatusBadge value={alert.severity} />
                  <StatusBadge value={alert.status} />
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="card">
        <h3 className="card-title">
          Recent Media Collection History ({mediaHistory.length} snapshots)
        </h3>
        {mediaHistory.length === 0 ? (
          <p style={{ fontSize: "0.84rem", color: "var(--text-muted)" }}>
            No persisted media snapshots yet. Click &ldquo;Poll Read-Only Media Snapshot&rdquo; when
            connectors are enabled.
          </p>
        ) : (
          <ul className="kv-list">
            {mediaHistory.slice(0, 8).map((item) => (
              <li key={item.id}>
                <span>
                  <code>{item.collected_at}</code> · Streams:{" "}
                  <strong>{item.jellyfin_active_streams}</strong> (Transcode:{" "}
                  {item.jellyfin_transcoding_streams}) · DL:{" "}
                  <code>{formatSpeedBps(item.qb_dl_speed_bytes)}</code> · Stalled:{" "}
                  <code>{item.qb_stalled_count ?? 0}</code>
                </span>
                <StatusBadge value={item.overall_status} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
