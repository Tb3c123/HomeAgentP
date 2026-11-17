import React from "react";
import type { DeliveryStatus, NotificationDeliveryItem } from "../../api/types";
import { DELIVERIES_PAGE_LIMIT } from "../../hooks/useHomeAutomationData";
import { StatusBadge } from "../StatusBadge";

interface NotificationDeliveriesPanelProps {
  deliveries: NotificationDeliveryItem[];
  statusFilter: DeliveryStatus | "";
  offset: number;
  loading: boolean;
  onStatusFilterChange: (nextStatus: DeliveryStatus | "") => void;
  onPrevPage: () => void;
  onNextPage: () => void;
}

export const NotificationDeliveriesPanel: React.FC<NotificationDeliveriesPanelProps> = ({
  deliveries,
  statusFilter,
  offset,
  loading,
  onStatusFilterChange,
  onPrevPage,
  onNextPage,
}) => {
  const hasPrev = offset > 0;
  const hasNext = deliveries.length === DELIVERIES_PAGE_LIMIT;

  return (
    <div className="card">
      <div className="section-header">
        <div>
          <h3>Notification Delivery History</h3>
          <p className="muted">Redacted outbox records and delivery status.</p>
        </div>
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <label htmlFor="delivery-status-filter" className="muted" style={{ fontSize: "0.85rem" }}>
            Status:
          </label>
          <select
            id="delivery-status-filter"
            className="input"
            value={statusFilter}
            onChange={(e) => onStatusFilterChange(e.target.value as DeliveryStatus | "")}
          >
            <option value="">All</option>
            <option value="pending">Pending</option>
            <option value="in_flight">In Flight</option>
            <option value="sent">Sent</option>
            <option value="failed">Failed</option>
            <option value="dead_letter">Dead Letter</option>
            <option value="suppressed_cooldown">Suppressed (Cooldown)</option>
            <option value="suppressed_rate_limit">Suppressed (Rate Limit)</option>
            <option value="suppressed_overflow">Suppressed (Overflow)</option>
          </select>
        </div>
      </div>

      {loading ? (
        <p className="muted">Loading delivery history...</p>
      ) : deliveries.length === 0 ? (
        <p className="muted">No notification deliveries found for the selected filter.</p>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Incident</th>
                <th>Severity</th>
                <th>Destination</th>
                <th>Status</th>
                <th>Attempts</th>
                <th>Message</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {deliveries.map((item) => (
                <tr key={item.id}>
                  <td>
                    <code>{item.incident_key}</code>
                  </td>
                  <td>
                    <StatusBadge value={item.severity} />
                  </td>
                  <td>{item.destination_masked}</td>
                  <td>
                    <StatusBadge value={item.status} />
                  </td>
                  <td>{item.attempt_count}</td>
                  <td>
                    <div>{item.message_redacted}</div>
                    {item.last_error_redacted && (
                      <div className="muted" style={{ fontSize: "0.8rem" }}>
                        {item.last_error_redacted}
                      </div>
                    )}
                  </td>
                  <td>{item.created_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginTop: "0.75rem",
        }}
      >
        <span className="muted" style={{ fontSize: "0.85rem" }}>
          Showing offset {offset} ({deliveries.length} items)
        </span>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <button type="button" className="btn-secondary" disabled={!hasPrev} onClick={onPrevPage}>
            Previous
          </button>
          <button type="button" className="btn-secondary" disabled={!hasNext} onClick={onNextPage}>
            Next
          </button>
        </div>
      </div>
    </div>
  );
};
