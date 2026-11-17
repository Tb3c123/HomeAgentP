import type { OverviewResponse } from "../../api/types";
import { StatusBadge } from "../StatusBadge";

interface OverviewSectionProps {
  overview: OverviewResponse;
}

export function OverviewSection({ overview }: OverviewSectionProps) {
  return (
    <section aria-label="System Overview">
      <h2>System Overview</h2>
      <div className="card-grid">
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">{overview.domains.nas_guardian.title}</h3>
            <StatusBadge value={overview.domains.nas_guardian.status} />
          </div>
          <p style={{ fontSize: "0.84rem", color: "var(--text-muted)" }}>
            {overview.domains.nas_guardian.reason}
          </p>
          <ul className="kv-list">
            <li>
              <span>CPU / RAM Telemetry</span>
              <StatusBadge value={overview.domains.nas_guardian.metrics.cpu_load} />
            </li>
            <li>
              <span>Mount /mnt/disk1</span>
              <StatusBadge value={overview.domains.nas_guardian.metrics.mounts["/mnt/disk1"]} />
            </li>
            <li>
              <span>Mount /mnt/disk2</span>
              <StatusBadge value={overview.domains.nas_guardian.metrics.mounts["/mnt/disk2"]} />
            </li>
            <li>
              <span>SMART &amp; Containers</span>
              <StatusBadge value={overview.domains.nas_guardian.metrics.smart_health} />
            </li>
          </ul>
        </div>

        <div className="card">
          <div className="card-header">
            <h3 className="card-title">{overview.domains.media.title}</h3>
            <StatusBadge value={overview.domains.media.status} />
          </div>
          <p style={{ fontSize: "0.84rem", color: "var(--text-muted)" }}>
            {overview.domains.media.reason}
          </p>
          <ul className="kv-list">
            {Object.entries(overview.domains.media.services).map(([svc, st]) => (
              <li key={svc}>
                <span style={{ textTransform: "capitalize" }}>{svc}</span>
                <StatusBadge value={st} />
              </li>
            ))}
          </ul>
        </div>

        <div className="card">
          <div className="card-header">
            <h3 className="card-title">{overview.domains.downloads.title}</h3>
            <StatusBadge value={overview.domains.downloads.status} />
          </div>
          <p style={{ fontSize: "0.84rem", color: "var(--text-muted)" }}>
            {overview.domains.downloads.reason}
          </p>
          <ul className="kv-list">
            {Object.entries(overview.domains.downloads.metrics).map(([k, v]) => (
              <li key={k}>
                <span>{k.replace(/_/g, " ")}</span>
                <StatusBadge value={v} />
              </li>
            ))}
          </ul>
        </div>

        <div className="card">
          <div className="card-header">
            <h3 className="card-title">{overview.domains.home_automation.title}</h3>
            <StatusBadge value={overview.domains.home_automation.status} />
          </div>
          <p style={{ fontSize: "0.84rem", color: "var(--text-muted)" }}>
            {overview.domains.home_automation.reason}
          </p>
          <ul className="kv-list">
            {Object.entries(overview.domains.home_automation.integrations).map(([k, v]) => (
              <li key={k}>
                <span>{k.replace(/_/g, " ")}</span>
                <StatusBadge value={v} />
              </li>
            ))}
          </ul>
        </div>

        <div className="card">
          <div className="card-header">
            <h3 className="card-title">Workspace &amp; Developer State</h3>
            <StatusBadge value={overview.domains.ai_workspace.status} />
          </div>
          <ul className="kv-list">
            <li>
              <span>Projects Registered</span>
              <strong>{overview.workspace_counts.projects}</strong>
            </li>
            <li>
              <span>Open Tasks</span>
              <strong>{overview.workspace_counts.tasks_open}</strong>
            </li>
            <li>
              <span>Allowlisted Scripts (Read-Only)</span>
              <strong>{overview.workspace_counts.scripts_allowlisted}</strong>
            </li>
            <li>
              <span>Reports &amp; Audit Events</span>
              <strong>
                {overview.workspace_counts.reports_total} / {overview.workspace_counts.audit_events}
              </strong>
            </li>
          </ul>
        </div>
      </div>
    </section>
  );
}

export function HomeAutomationSection({ overview }: OverviewSectionProps) {
  return (
    <section aria-label="Home Automation and Telegram Details">
      <h2>Home Assistant, Monitoring &amp; Telegram Alerts</h2>
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Home Automation &amp; Notification Channels</h3>
          <StatusBadge value={overview.domains.home_automation.status} />
        </div>
        <p style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>
          {overview.domains.home_automation.reason}
        </p>
        <ul className="kv-list">
          {Object.entries(overview.domains.home_automation.integrations).map(([k, v]) => (
            <li key={k}>
              <span>{k.replace(/_/g, " ")}</span>
              <StatusBadge value={v} />
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
