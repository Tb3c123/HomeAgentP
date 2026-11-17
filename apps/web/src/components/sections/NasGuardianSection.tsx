import type { NasAlertItem, NasHistoryItem, NasStatusResponse } from "../../api/types";
import { formatBytes, formatPercent } from "../../utils/format";
import { StatusBadge } from "../StatusBadge";

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
          <div className="card-grid">
            <div className="card">
              <div className="card-header">
                <h3 className="card-title">CPU &amp; Load Pressure</h3>
                <StatusBadge value={nasStatus.cpu.status} />
              </div>
              <ul className="kv-list">
                <li>
                  <span>CPU Usage</span>
                  <strong>{formatPercent(nasStatus.cpu.usage_percent)}</strong>
                </li>
                <li>
                  <span>Logical Cores</span>
                  <strong>{nasStatus.cpu.logical_cores ?? "unavailable"}</strong>
                </li>
                <li>
                  <span>Load Average (1m / 5m / 15m)</span>
                  <code>
                    {nasStatus.cpu.load_1m !== null
                      ? `${nasStatus.cpu.load_1m.toFixed(2)} / ${nasStatus.cpu.load_5m?.toFixed(2) ?? "-"} / ${nasStatus.cpu.load_15m?.toFixed(2) ?? "-"}`
                      : "unavailable"}
                  </code>
                </li>
                <li>
                  <span>PSI Pressure (some avg10 / avg60)</span>
                  <code>
                    {nasStatus.cpu.pressure.some
                      ? `${nasStatus.cpu.pressure.some.avg10.toFixed(2)}% / ${nasStatus.cpu.pressure.some.avg60.toFixed(2)}%`
                      : "unavailable"}
                  </code>
                </li>
                <li>
                  <span>Thresholds (Warn / Crit)</span>
                  <code>
                    {nasStatus.thresholds.cpu_warn_percent}% /{" "}
                    {nasStatus.thresholds.cpu_critical_percent}%
                  </code>
                </li>
              </ul>
            </div>

            <div className="card">
              <div className="card-header">
                <h3 className="card-title">RAM, Swap &amp; Memory Pressure</h3>
                <StatusBadge value={nasStatus.memory.status} />
              </div>
              <ul className="kv-list">
                <li>
                  <span>RAM Usage</span>
                  <strong>
                    {formatPercent(nasStatus.memory.usage_percent)} (
                    {formatBytes(nasStatus.memory.used_bytes)} /{" "}
                    {formatBytes(nasStatus.memory.total_bytes)})
                  </strong>
                </li>
                <li>
                  <span>Available Memory</span>
                  <strong>{formatBytes(nasStatus.memory.available_bytes)}</strong>
                </li>
                <li>
                  <span>Swap Usage</span>
                  <code>
                    {formatPercent(nasStatus.memory.swap_usage_percent)} (
                    {formatBytes(nasStatus.memory.swap_used_bytes)} /{" "}
                    {formatBytes(nasStatus.memory.swap_total_bytes)})
                  </code>
                </li>
                <li>
                  <span>Memory PSI (some / full avg10)</span>
                  <code>
                    {nasStatus.memory.pressure.some
                      ? `${nasStatus.memory.pressure.some.avg10.toFixed(2)}% / ${nasStatus.memory.pressure.full?.avg10.toFixed(2) ?? "0.00"}%`
                      : "unavailable"}
                  </code>
                </li>
                <li>
                  <span>Thresholds (Warn / Crit)</span>
                  <code>
                    {nasStatus.thresholds.ram_warn_percent}% /{" "}
                    {nasStatus.thresholds.ram_critical_percent}%
                  </code>
                </li>
              </ul>
            </div>

            <div className="card">
              <div className="card-header">
                <h3 className="card-title">Host Boundary, Scheduler &amp; Safety</h3>
                <StatusBadge value={nasStatus.status} />
              </div>
              <ul className="kv-list">
                <li>
                  <span>Host Telemetry Boundary</span>
                  <StatusBadge
                    value={
                      nasStatus.telemetry_boundary?.host_verified
                        ? nasStatus.telemetry_boundary.mode
                        : "unavailable"
                    }
                  />
                </li>
                <li>
                  <span>Auto-Collection Scheduler</span>
                  <code>
                    {nasStatus.scheduler
                      ? `${nasStatus.scheduler.running ? "running" : nasStatus.scheduler.last_status} (${nasStatus.collection_interval_seconds}s)`
                      : `${nasStatus.collection_interval_seconds}s`}
                  </code>
                </li>
                <li>
                  <span>HDD Write Operations</span>
                  <code>{nasStatus.storage_safety.hdd_write_operations}</code>
                </li>
                <li>
                  <span>Media Directory Tree Crawled</span>
                  <StatusBadge
                    value={nasStatus.storage_safety.media_tree_crawled ? "yes" : "no"}
                  />
                </li>
                <li>
                  <span>Docker Socket Used</span>
                  <StatusBadge
                    value={nasStatus.storage_safety.docker_socket_used ? "yes" : "no"}
                  />
                </li>
              </ul>
            </div>
          </div>

          <div className="card">
            <div className="card-header">
              <h3 className="card-title">
                Mount Guardian (<code>/</code>, <code>/mnt/disk1</code>, <code>/mnt/disk2</code>)
              </h3>
              <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                Detects missing directories and unmounted root-filesystem fallbacks
              </span>
            </div>
            <ul className="kv-list">
              {Object.values(nasStatus.mounts).map((mnt) => (
                <li key={mnt.path}>
                  <div>
                    <strong>
                      <code>{mnt.path}</code>
                    </strong>{" "}
                    {mnt.device ? (
                      <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                        ({mnt.device} · {mnt.fstype || "unknown"})
                      </span>
                    ) : null}
                    <div style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                      {mnt.reason ||
                        `Used ${formatBytes(mnt.used_bytes)} of ${formatBytes(mnt.total_bytes)} (${formatBytes(mnt.available_bytes)} free)`}
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                    {mnt.usage_percent !== null && <code>{mnt.usage_percent.toFixed(1)}%</code>}
                    <StatusBadge value={mnt.status} />
                  </div>
                </li>
              ))}
            </ul>
          </div>

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
            <h3 className="card-title">
              Recent Metrics History ({nasHistory.length} snapshots)
            </h3>
            {nasHistory.length === 0 ? (
              <p style={{ fontSize: "0.84rem", color: "var(--text-muted)" }}>
                No persisted snapshots yet. Click &ldquo;Collect Read-Only Snapshot&rdquo; to record
                a baseline.
              </p>
            ) : (
              <ul className="kv-list">
                {nasHistory.slice(0, 8).map((item) => (
                  <li key={item.id}>
                    <span>
                      <code>{item.collected_at}</code> · CPU:{" "}
                      <strong>{formatPercent(item.cpu_usage_percent)}</strong> · Load 1m:{" "}
                      <code>
                        {item.load_1m !== null ? item.load_1m.toFixed(2) : "unavailable"}
                      </code>{" "}
                      · RAM: <strong>{formatPercent(item.ram_usage_percent)}</strong>
                    </span>
                    <StatusBadge value={item.adapter_status} />
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      ) : (
        <div className="card">
          <p>Loading NAS Guardian status...</p>
        </div>
      )}
    </section>
  );
}
