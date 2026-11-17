import type { NasAlertItem, NasHistoryItem, NasStatusResponse } from "../../api/types";
import { formatBytes, formatPercent } from "../../utils/format";
import { StatusBadge } from "../StatusBadge";

interface NasContainersAlertsHistoryProps {
  nasStatus: NasStatusResponse;
  nasAlerts: NasAlertItem[];
  nasHistory: NasHistoryItem[];
  includeResolvedAlerts: boolean;
  onToggleIncludeResolved: (checked: boolean) => void | Promise<void>;
}

export function NasContainersAlertsHistory({
  nasStatus,
  nasAlerts,
  nasHistory,
  includeResolvedAlerts,
  onToggleIncludeResolved,
}: NasContainersAlertsHistoryProps) {
  return (
    <>
      <div className="card-grid">
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">Container Health (No Docker Socket)</h3>
            <StatusBadge value={nasStatus.containers.status} />
          </div>
          <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
            {nasStatus.containers.reason ||
              `Source: ${nasStatus.containers.source}${
                nasStatus.containers.age_seconds !== undefined &&
                nasStatus.containers.age_seconds !== null
                  ? ` · Age: ${nasStatus.containers.age_seconds.toFixed(0)}s / TTL ${nasStatus.containers.ttl_seconds ?? 180}s`
                  : ""
              }`}
          </p>
          <ul className="kv-list">
            {Object.values(nasStatus.containers.services).map((svc) => (
              <li key={svc.name}>
                <div>
                  <strong style={{ textTransform: "capitalize" }}>{svc.name}</strong>
                  <div style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>
                    {svc.memory_bytes !== null
                      ? `Mem: ${formatBytes(svc.memory_bytes)} / ${formatBytes(svc.memory_limit_bytes)} (${formatPercent(svc.memory_percent)}) · Restarts: ${svc.restart_count ?? 0}`
                      : svc.reason || "No snapshot configured"}
                  </div>
                </div>
                <StatusBadge value={svc.status} />
              </li>
            ))}
          </ul>
        </div>

        <div className="card">
          <div className="card-header">
            <h3 className="card-title">NAS Alerts ({nasAlerts.length})</h3>
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
                  checked={includeResolvedAlerts}
                  onChange={(e) => void onToggleIncludeResolved(e.target.checked)}
                />
                Show resolved
              </label>
              <StatusBadge
                value={
                  nasStatus.alerts.some((a) => a.severity === "critical")
                    ? "critical"
                    : nasStatus.alerts.length > 0
                      ? "warning"
                      : "ok"
                }
              />
            </div>
          </div>
          {nasAlerts.length === 0 ? (
            <p style={{ fontSize: "0.84rem", color: "var(--text-muted)" }}>
              No active NAS alerts.
            </p>
          ) : (
            <ul className="kv-list">
              {nasAlerts.slice(0, 10).map((alert) => (
                <li key={`${alert.id ?? alert.alert_key}-${alert.status}`}>
                  <div>
                    <strong>{alert.target}</strong> ({alert.code ?? alert.category})
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
      </div>

      <div className="card">
        <h3 className="card-title">Recent Metrics History ({nasHistory.length} snapshots)</h3>
        {nasHistory.length === 0 ? (
          <p style={{ fontSize: "0.84rem", color: "var(--text-muted)" }}>
            No persisted snapshots yet. Click &ldquo;Collect Read-Only Snapshot&rdquo; to record a
            baseline.
          </p>
        ) : (
          <ul className="kv-list">
            {nasHistory.slice(0, 8).map((item) => (
              <li key={item.id}>
                <span>
                  <code>{item.collected_at}</code> · CPU:{" "}
                  <strong>{formatPercent(item.cpu_usage_percent)}</strong> · Load 1m:{" "}
                  <code>{item.load_1m !== null ? item.load_1m.toFixed(2) : "unavailable"}</code> ·
                  RAM: <strong>{formatPercent(item.ram_usage_percent)}</strong>
                </span>
                <StatusBadge value={item.adapter_status} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </>
  );
}
