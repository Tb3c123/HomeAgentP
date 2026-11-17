import type { ArrV3Metrics, MediaServiceSnapshot } from "../../api/types";
import { formatBytes } from "../../utils/format";
import { StatusBadge } from "../StatusBadge";

interface ArrSuiteCardsProps {
  sonarr: MediaServiceSnapshot<ArrV3Metrics>;
  radarr: MediaServiceSnapshot<ArrV3Metrics>;
}

export function ArrSuiteCards({ sonarr, radarr }: ArrSuiteCardsProps) {
  const services = [
    { key: "sonarr", svc: sonarr },
    { key: "radarr", svc: radarr },
  ] as const;

  return (
    <div className="card-grid">
      {services.map(({ key, svc }) => {
        const m = svc.metrics;
        return (
          <div className="card" key={key}>
            <div className="card-header">
              <h3 className="card-title">
                {svc.title}
                {svc.version ? ` (v${svc.version})` : ""}
              </h3>
              <StatusBadge value={svc.status} />
            </div>
            <ul className="kv-list">
              <li>
                <span>Total / Monitored / Files</span>
                <strong>
                  {m.total_count ?? "unavailable"} / {m.monitored_count ?? "unavailable"} /{" "}
                  {m.available_file_count ?? "unavailable"}
                </strong>
              </li>
              <li>
                <span>Size on Disk</span>
                <code>{formatBytes(m.size_on_disk_bytes)}</code>
              </li>
              <li>
                <span>Wanted / Missing Monitored</span>
                <strong>{m.missing_count ?? "unavailable"}</strong>
              </li>
              <li>
                <span>Queue (Total / Import Failures)</span>
                <code>
                  {m.queue_total} / {m.queue_failed_count}
                </code>
              </li>
              <li>
                <span>System Health Issues</span>
                <strong>{m.health_warnings.length}</strong>
              </li>
            </ul>
          </div>
        );
      })}
    </div>
  );
}
