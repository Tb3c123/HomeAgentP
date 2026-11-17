import type {
  AuditLogItem,
  RedactedSettings,
  ReportDetailItem,
  ReportSummaryItem,
  ScriptDetailItem,
  ScriptManifestItem,
} from "../../api/types";
import { StatusBadge } from "../StatusBadge";

interface ScriptsSectionProps {
  scripts: ScriptManifestItem[];
  selectedScript: ScriptDetailItem | null;
  onSelectScript: (slug: string) => Promise<void>;
}

export function ScriptsSection({
  scripts,
  selectedScript,
  onSelectScript,
}: ScriptsSectionProps) {
  return (
    <section aria-label="Read-Only Script Registry">
      <h2>Script Registry (Read-Only Inspection)</h2>
      <p style={{ color: "var(--text-muted)" }}>
        Arbitrary script execution is disabled in Phase 01. Scripts are verified against their
        manifest SHA-256 digest and read with strict symlink/traversal protection.
      </p>
      <div className="card-grid">
        <div className="card">
          <h3 className="card-title">Registered Manifests</h3>
          <ul className="kv-list">
            {scripts.map((s) => (
              <li key={s.slug}>
                <div>
                  <strong>{s.name}</strong> (<code>{s.rel_path}</code>)
                  <div style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                    {s.description}
                  </div>
                </div>
                <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                  <StatusBadge value={s.review_status} />
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => void onSelectScript(s.slug)}
                  >
                    Inspect
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </div>

        {selectedScript && (
          <div className="card">
            <div className="card-header">
              <h3 className="card-title">{selectedScript.name}</h3>
              <StatusBadge
                value={selectedScript.checksum_verified ? "SHA256_VERIFIED" : "UNVERIFIED"}
              />
            </div>
            <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
              Relative Path: <code>{selectedScript.rel_path}</code> · Policy:{" "}
              <code>{selectedScript.execution_policy}</code> · SHA-256:{" "}
              <code>{selectedScript.sha256.slice(0, 16)}…</code>
            </p>
            <pre className="code-viewer">{selectedScript.content}</pre>
          </div>
        )}
      </div>
    </section>
  );
}

interface ReportsSectionProps {
  reports: ReportSummaryItem[];
  selectedReport: ReportDetailItem | null;
  auditLogs: AuditLogItem[];
  onSelectReport: (slug: string) => Promise<void>;
}

export function ReportsSection({
  reports,
  selectedReport,
  auditLogs,
  onSelectReport,
}: ReportsSectionProps) {
  return (
    <section aria-label="Reports and Security Audit Logs">
      <h2>Reports, Artifacts &amp; Security Audit Log</h2>
      <div className="card-grid">
        <div className="card">
          <h3 className="card-title">Available Reports</h3>
          <ul className="kv-list">
            {reports.map((r) => (
              <li key={r.slug}>
                <div>
                  <strong>{r.title}</strong>
                  <div style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                    {r.summary}
                  </div>
                </div>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => void onSelectReport(r.slug)}
                >
                  Read Report
                </button>
              </li>
            ))}
          </ul>
        </div>

        {selectedReport && (
          <div className="card">
            <div className="card-header">
              <h3 className="card-title">{selectedReport.title}</h3>
              <StatusBadge value={selectedReport.category} />
            </div>
            <pre className="code-viewer">{selectedReport.content}</pre>
          </div>
        )}
      </div>

      <div className="card">
        <h3 className="card-title">Recent Security &amp; State Audit Logs</h3>
        <ul className="kv-list">
          {auditLogs.slice(0, 15).map((log) => (
            <li key={log.id}>
              <span>
                <strong>{log.action}</strong> by <code>{log.actor}</code> on{" "}
                <code>
                  {log.target_type}:{log.target_id || "-"}
                </code>
              </span>
              <span style={{ color: "var(--text-muted)" }}>{log.created_at}</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

interface SettingsSectionProps {
  settingsData: RedactedSettings;
}

export function SettingsSection({ settingsData }: SettingsSectionProps) {
  return (
    <section aria-label="Settings and Safety Boundaries">
      <h2>Runtime Settings &amp; Enforced B+ Safety Constraints</h2>
      <div className="card-grid">
        <div className="card">
          <h3 className="card-title">Redacted Configuration</h3>
          <ul className="kv-list">
            <li>
              <span>Environment</span>
              <code>{settingsData.env}</code>
            </li>
            <li>
              <span>Candidate Web Port</span>
              <code>{settingsData.port}</code>
            </li>
            <li>
              <span>SQLite Path</span>
              <code>{settingsData.db_path}</code>
            </li>
            <li>
              <span>Allowlisted Scripts Dir</span>
              <code>{settingsData.scripts_dir}</code>
            </li>
            <li>
              <span>Allowlisted Reports Dir</span>
              <code>{settingsData.reports_dir}</code>
            </li>
            <li>
              <span>Secret Key</span>
              <code>{settingsData.secret_key}</code>
            </li>
          </ul>
        </div>

        <div className="card">
          <h3 className="card-title">Hard Security Constraints</h3>
          <ul className="kv-list">
            <li>
              <span>Architecture Mode</span>
              <strong>{settingsData.architecture_mode}</strong>
            </li>
            <li>
              <span>Arbitrary Script Execution</span>
              <StatusBadge
                value={settingsData.script_execution_enabled ? "enabled" : "disabled"}
              />
            </li>
            <li>
              <span>Docker Socket Mounted</span>
              <StatusBadge value={settingsData.docker_socket_mounted ? "yes" : "no"} />
            </li>
            <li>
              <span>Consumer Antigravity CLI Wrapper</span>
              <StatusBadge value={settingsData.antigravity_cli_wrapper} />
            </li>
          </ul>
        </div>
      </div>
    </section>
  );
}
