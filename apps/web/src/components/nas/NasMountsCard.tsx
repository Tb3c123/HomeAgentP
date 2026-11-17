import type { NasStatusResponse } from "../../api/types";
import { formatBytes } from "../../utils/format";
import { StatusBadge } from "../StatusBadge";

interface NasMountsCardProps {
  mounts: NasStatusResponse["mounts"];
}

export function NasMountsCard({ mounts }: NasMountsCardProps) {
  return (
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
        {Object.values(mounts).map((mnt) => (
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
  );
}
