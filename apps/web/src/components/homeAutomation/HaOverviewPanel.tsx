import React from "react";
import type { HaOverviewResponse } from "../../api/types";
import { StatusBadge } from "../StatusBadge";

interface HaOverviewPanelProps {
  haOverview: HaOverviewResponse | null;
  isOwner: boolean;
  collectBusy: boolean;
  onCollect: () => void;
}

export const HaOverviewPanel: React.FC<HaOverviewPanelProps> = ({
  haOverview,
  isOwner,
  collectBusy,
  onCollect,
}) => {
  return (
    <div className="card" style={{ marginBottom: "1rem" }}>
      <div className="section-header">
        <div>
          <h3>Home Assistant (Read-Only)</h3>
          <p className="muted">
            Opt-in allowlisted entity states. Never executes service calls or mutations on Home Assistant.
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          {haOverview && <StatusBadge value={haOverview.status} />}
          {isOwner ? (
            <button
              type="button"
              className="btn-primary"
              disabled={collectBusy || !haOverview?.enabled}
              onClick={onCollect}
            >
              {collectBusy ? "Collecting..." : "Collect HA Snapshot"}
            </button>
          ) : (
            <span className="muted" style={{ fontSize: "0.85rem" }}>
              Viewer role: read-only
            </span>
          )}
        </div>
      </div>

      {!haOverview ? (
        <p className="muted">Loading Home Assistant status...</p>
      ) : !haOverview.enabled ? (
        <div className="banner-notice" role="status">
          <strong>Home Assistant Disabled (Opt-In):</strong> {haOverview.reason}
        </div>
      ) : haOverview.status === "unavailable" || haOverview.status === "stale" ? (
        <div className="banner-notice" role="status">
          <strong>Status ({haOverview.status.toUpperCase()}):</strong> {haOverview.reason}
          {haOverview.collected_at && <span> (Last collected: {haOverview.collected_at})</span>}
        </div>
      ) : (
        <p className="muted" style={{ marginBottom: "0.75rem" }}>
          {haOverview.reason}
          {haOverview.collected_at && ` · Last collected: ${haOverview.collected_at}`}
        </p>
      )}

      {haOverview && haOverview.enabled && haOverview.entities.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Entity</th>
                <th>State</th>
                <th>Status</th>
                <th>Updated</th>
              </tr>
            </thead>
            <tbody>
              {haOverview.entities.map((ent) => (
                <tr key={ent.entity_id}>
                  <td>
                    <strong>{ent.friendly_name}</strong>
                    <div className="muted" style={{ fontSize: "0.8rem" }}>
                      {ent.entity_id}
                    </div>
                  </td>
                  <td>
                    {ent.state}
                    {ent.attributes.unit_of_measurement
                      ? ` ${String(ent.attributes.unit_of_measurement)}`
                      : ""}
                  </td>
                  <td>
                    <StatusBadge value={ent.status} />
                  </td>
                  <td>{ent.collected_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {haOverview && haOverview.enabled && haOverview.entities.length === 0 && (
        <p className="muted">No allowlisted Home Assistant entities recorded yet.</p>
      )}
    </div>
  );
};
