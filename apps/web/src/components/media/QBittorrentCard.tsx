import type { MediaServiceSnapshot, QBittorrentMetrics } from "../../api/types";
import { formatSpeedBps } from "../../utils/format";
import { StatusBadge } from "../StatusBadge";

interface QBittorrentCardProps {
  service: MediaServiceSnapshot<QBittorrentMetrics>;
}

export function QBittorrentCard({ service }: QBittorrentCardProps) {
  return (
    <div className="card">
      <div className="card-header">
        <h3 className="card-title">
          qBittorrent Downloads{service.version ? ` (${service.version})` : ""}
        </h3>
        <StatusBadge value={service.status} />
      </div>
      <p style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>
        {service.metrics.credential_scope_notice}
      </p>
      <ul className="kv-list">
        <li>
          <span>Connection Status</span>
          <StatusBadge value={service.metrics.connection_status} />
        </li>
        <li>
          <span>Download / Upload Speed</span>
          <strong>
            {formatSpeedBps(service.metrics.download_speed_bytes)} /{" "}
            {formatSpeedBps(service.metrics.upload_speed_bytes)}
          </strong>
        </li>
        <li>
          <span>Torrents (DL / Seed / Paused / Queued)</span>
          <code>
            {service.metrics.counts.downloading} / {service.metrics.counts.seeding} /{" "}
            {service.metrics.counts.paused} / {service.metrics.counts.queued}
          </code>
        </li>
        <li>
          <span>Stalled (Total / Exceeding Threshold)</span>
          <code>
            {service.metrics.counts.stalled} / {service.metrics.counts.stalled_over_threshold}
          </code>
        </li>
        <li>
          <span>Errored / Disk Missing Files</span>
          <strong>{service.metrics.counts.errored}</strong>
        </li>
      </ul>
      {service.metrics.stalled_torrents.length > 0 && (
        <div style={{ marginTop: "0.75rem" }}>
          <strong style={{ fontSize: "0.82rem" }}>Stalled Queue:</strong>
          <ul className="kv-list" style={{ marginTop: "0.35rem" }}>
            {service.metrics.stalled_torrents.slice(0, 5).map((t) => (
              <li key={t.hash || t.name}>
                <span>
                  <strong>{t.name}</strong> ({t.progress_percent}%)
                </span>
                <StatusBadge value={t.exceeds_threshold ? "warning" : "stale"} />
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
