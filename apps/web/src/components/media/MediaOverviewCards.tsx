import type { MediaOverviewResponse, OverviewResponse } from "../../api/types";
import { StatusBadge } from "../StatusBadge";

interface MediaOverviewCardsProps {
  mediaOverview: MediaOverviewResponse;
}

export function MediaOverviewCards({ mediaOverview }: MediaOverviewCardsProps) {
  return (
    <div className="card-grid">
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Media Services (Jellyfin &amp; *arr)</h3>
          <StatusBadge value={mediaOverview.overall_status} />
        </div>
        <p style={{ fontSize: "0.84rem", color: "var(--text-muted)" }}>{mediaOverview.reason}</p>
        <ul className="kv-list">
          {(
            [
              "jellyfin",
              "sonarr",
              "radarr",
              "bazarr",
              "prowlarr",
              "seerr",
              "qbittorrent",
            ] as const
          ).map((svcKey) => {
            const svc = mediaOverview.services[svcKey];
            return (
              <li key={svcKey}>
                <div>
                  <strong style={{ textTransform: "capitalize" }}>{svcKey}</strong>
                  {svc.version ? (
                    <span
                      style={{
                        fontSize: "0.76rem",
                        color: "var(--text-muted)",
                        marginLeft: "0.4rem",
                      }}
                    >
                      v{svc.version.replace(/^v/i, "")}
                    </span>
                  ) : null}
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                    {svc.reason}
                    {svc.latency_ms !== null ? ` · ${svc.latency_ms} ms` : ""}
                    {svc.consecutive_failures > 0
                      ? ` · Failures: ${svc.consecutive_failures}/${mediaOverview.failure_threshold}`
                      : ""}
                  </div>
                </div>
                <StatusBadge value={svc.status} />
              </li>
            );
          })}
        </ul>
      </div>

      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Scheduler, Failure Policy &amp; Safety</h3>
          <StatusBadge value={mediaOverview.adapter_enabled ? "online" : "unavailable"} />
        </div>
        <ul className="kv-list">
          <li>
            <span>Auto-Polling Scheduler</span>
            <code>
              {mediaOverview.scheduler
                ? `${mediaOverview.scheduler.running ? "running" : mediaOverview.scheduler.last_status} (${mediaOverview.collection_interval_seconds}s)`
                : `${mediaOverview.collection_interval_seconds}s`}
            </code>
          </li>
          <li>
            <span>Offline Failure Threshold</span>
            <code>{mediaOverview.failure_threshold} consecutive polls</code>
          </li>
          <li>
            <span>Read-Only API Enforcement</span>
            <StatusBadge value={mediaOverview.safety.read_only_enforced ? "ok" : "error"} />
          </li>
          <li>
            <span>SSRF Host Allowlist &amp; Redirect Block</span>
            <StatusBadge
              value={
                mediaOverview.safety.ssrf_allowlist_enforced &&
                mediaOverview.safety.redirects_blocked
                  ? "ok"
                  : "error"
              }
            />
          </li>
          <li>
            <span>Media HDD Mounted in Web/Core</span>
            <StatusBadge
              value={mediaOverview.safety.media_filesystem_mounted ? "error" : "ok"}
            />
          </li>
        </ul>
      </div>
    </div>
  );
}

interface MediaFallbackCardsProps {
  overview: OverviewResponse;
}

export function MediaFallbackCards({ overview }: MediaFallbackCardsProps) {
  return (
    <div className="card-grid">
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Media Services (Jellyfin &amp; *arr)</h3>
          <StatusBadge value={overview.domains.media.status} />
        </div>
        <p style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>
          {overview.domains.media.reason}
        </p>
        <ul className="kv-list">
          {Object.entries(overview.domains.media.services).map(([name, st]) => (
            <li key={name}>
              <span style={{ textTransform: "capitalize" }}>{name}</span>
              <StatusBadge value={st} />
            </li>
          ))}
        </ul>
      </div>
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">qBittorrent Downloads</h3>
          <StatusBadge value={overview.domains.downloads.status} />
        </div>
        <p style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>
          {overview.domains.downloads.reason}
        </p>
        <ul className="kv-list">
          {Object.entries(overview.domains.downloads.metrics).map(([name, st]) => (
            <li key={name}>
              <span>{name.replace(/_/g, " ")}</span>
              <StatusBadge value={st} />
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
