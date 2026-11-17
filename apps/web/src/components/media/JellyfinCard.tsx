import type { JellyfinMetrics, MediaServiceSnapshot } from "../../api/types";
import { StatusBadge } from "../StatusBadge";

interface JellyfinCardProps {
  service: MediaServiceSnapshot<JellyfinMetrics>;
}

export function JellyfinCard({ service }: JellyfinCardProps) {
  return (
    <div className="card">
      <div className="card-header">
        <h3 className="card-title">
          Jellyfin Media Server{service.version ? ` (${service.version})` : ""}
        </h3>
        <StatusBadge value={service.status} />
      </div>
      <ul className="kv-list">
        <li>
          <span>Libraries (Movies / Series / Episodes)</span>
          <strong>
            {service.metrics.libraries.movies ?? "unavailable"} /{" "}
            {service.metrics.libraries.series ?? "unavailable"} /{" "}
            {service.metrics.libraries.episodes ?? "unavailable"}
          </strong>
        </li>
        <li>
          <span>Active Sessions</span>
          <strong>{service.metrics.sessions.active_count}</strong>
        </li>
        <li>
          <span>Direct Play / Direct Stream / Transcode</span>
          <code>
            {service.metrics.sessions.direct_play_count} /{" "}
            {service.metrics.sessions.direct_stream_count} /{" "}
            {service.metrics.sessions.transcoding_count}
          </code>
        </li>
        <li>
          <span>Recent Playback Errors</span>
          <StatusBadge
            value={
              service.metrics.playback_errors.count > 0
                ? "warning"
                : service.enabled
                  ? "ok"
                  : "unavailable"
            }
          />
        </li>
      </ul>
      {service.metrics.sessions.streams.length > 0 && (
        <div style={{ marginTop: "0.75rem" }}>
          <strong style={{ fontSize: "0.82rem" }}>Active Playback Streams:</strong>
          <ul className="kv-list" style={{ marginTop: "0.35rem" }}>
            {service.metrics.sessions.streams.map((st) => (
              <li key={st.session_id || st.item_title}>
                <div>
                  <strong>{st.item_title}</strong> ({st.user_name} · {st.device_name})
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                    {st.video_codec ? `Codec: ${st.video_codec}` : "Direct stream"}
                    {st.transcode_reasons.length > 0
                      ? ` · Reasons: ${st.transcode_reasons.join(", ")}`
                      : ""}
                  </div>
                </div>
                <StatusBadge value={st.play_method} />
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
