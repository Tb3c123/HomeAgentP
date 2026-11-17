import React from "react";

interface StatusBadgeProps {
  value: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ value }) => {
  const normalized = value.toLowerCase();
  let tone = "badge-neutral";
  if (
    normalized === "online" ||
    normalized === "ok" ||
    normalized === "mounted" ||
    normalized === "running" ||
    normalized === "resolved" ||
    normalized === "allowlisted" ||
    normalized === "done" ||
    normalized === "succeeded"
  ) {
    tone = "badge-success";
  } else if (
    normalized === "unavailable" ||
    normalized === "not_configured" ||
    normalized === "not_tested" ||
    normalized === "draft" ||
    normalized === "warning" ||
    normalized === "degraded"
  ) {
    tone = "badge-warning";
  } else if (
    normalized === "in_progress" ||
    normalized === "reviewed" ||
    normalized === "ready" ||
    normalized === "review"
  ) {
    tone = "badge-info";
  } else if (
    normalized === "blocked" ||
    normalized === "failed" ||
    normalized === "revoked" ||
    normalized === "critical" ||
    normalized === "missing" ||
    normalized === "unmounted_fallback" ||
    normalized === "permission_denied" ||
    normalized === "error"
  ) {
    tone = "badge-danger";
  }

  return <span className={`status-badge ${tone}`}>{value.toUpperCase()}</span>;
};
