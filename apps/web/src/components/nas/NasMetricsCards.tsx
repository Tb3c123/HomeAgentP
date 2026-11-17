import type { NasStatusResponse } from "../../api/types";
import { formatBytes, formatPercent } from "../../utils/format";
import { StatusBadge } from "../StatusBadge";

interface NasMetricsCardsProps {
  nasStatus: NasStatusResponse;
}

export function NasMetricsCards({ nasStatus }: NasMetricsCardsProps) {
  return (
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
            <StatusBadge value={nasStatus.storage_safety.media_tree_crawled ? "yes" : "no"} />
          </li>
          <li>
            <span>Docker Socket Used</span>
            <StatusBadge value={nasStatus.storage_safety.docker_socket_used ? "yes" : "no"} />
          </li>
        </ul>
      </div>
    </div>
  );
}
