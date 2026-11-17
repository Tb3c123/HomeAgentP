import type {
  BazarrMetrics,
  MediaServiceSnapshot,
  ProwlarrMetrics,
  SeerrMetrics,
} from "../../api/types";
import { StatusBadge } from "../StatusBadge";

interface AuxMediaCardsProps {
  bazarr: MediaServiceSnapshot<BazarrMetrics>;
  prowlarr: MediaServiceSnapshot<ProwlarrMetrics>;
  seerr: MediaServiceSnapshot<SeerrMetrics>;
}

export function AuxMediaCards({ bazarr, prowlarr, seerr }: AuxMediaCardsProps) {
  return (
    <div className="card-grid">
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Bazarr Subtitles</h3>
          <StatusBadge value={bazarr.status} />
        </div>
        <ul className="kv-list">
          <li>
            <span>Missing Episode Subtitles</span>
            <strong>{bazarr.metrics.missing_episode_subtitles ?? "unavailable"}</strong>
          </li>
          <li>
            <span>Missing Movie Subtitles</span>
            <strong>{bazarr.metrics.missing_movie_subtitles ?? "unavailable"}</strong>
          </li>
          <li>
            <span>Throttled / Unhealthy Providers</span>
            <code>{bazarr.metrics.unhealthy_providers_count}</code>
          </li>
          <li>
            <span>Health Issues</span>
            <code>{bazarr.metrics.health_issues.length}</code>
          </li>
        </ul>
      </div>

      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Prowlarr Indexers</h3>
          <StatusBadge value={prowlarr.status} />
        </div>
        <ul className="kv-list">
          <li>
            <span>Indexers (Enabled / Total)</span>
            <strong>
              {prowlarr.metrics.enabled_indexers ?? "unavailable"} /{" "}
              {prowlarr.metrics.total_indexers ?? "unavailable"}
            </strong>
          </li>
          <li>
            <span>Failing / Disabled Indexers</span>
            <strong>{prowlarr.metrics.failing_indexers_count}</strong>
          </li>
          <li>
            <span>Health Warnings</span>
            <code>{prowlarr.metrics.health_warnings.length}</code>
          </li>
        </ul>
      </div>

      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Seerr Media Requests</h3>
          <StatusBadge value={seerr.status} />
        </div>
        <ul className="kv-list">
          <li>
            <span>Total Requests (Movie / TV)</span>
            <strong>
              {seerr.metrics.requests.total ?? "unavailable"} (
              {seerr.metrics.requests.movie ?? "-"} / {seerr.metrics.requests.tv ?? "-"})
            </strong>
          </li>
          <li>
            <span>Pending / Approved</span>
            <code>
              {seerr.metrics.requests.pending ?? "unavailable"} /{" "}
              {seerr.metrics.requests.approved ?? "unavailable"}
            </code>
          </li>
          <li>
            <span>Processing / Available</span>
            <code>
              {seerr.metrics.requests.processing ?? "unavailable"} /{" "}
              {seerr.metrics.requests.available ?? "unavailable"}
            </code>
          </li>
        </ul>
      </div>
    </div>
  );
}
