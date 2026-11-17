import React, { useState } from "react";
import type {
  HumanBriefStatus,
  TaskBriefCreateInput,
  TaskBriefExportItem,
  TaskBriefItem,
  TaskItem,
} from "../../api/types";

interface TaskBriefPanelProps {
  tasks: TaskItem[];
  selectedTaskId: number | null;
  onSelectTask: (taskId: number | null) => void;
  briefs: TaskBriefItem[];
  exportedBrief: TaskBriefExportItem | null;
  isOwner: boolean;
  busy: boolean;
  onCreateBrief: (taskId: number, payload: TaskBriefCreateInput) => Promise<boolean>;
  onExportBrief: (taskId: number, version?: number) => Promise<void>;
}

export function TaskBriefPanel({
  tasks,
  selectedTaskId,
  onSelectTask,
  briefs,
  exportedBrief,
  isOwner,
  busy,
  onCreateBrief,
  onExportBrief,
}: TaskBriefPanelProps) {
  const [purpose, setPurpose] = useState("");
  const [scope, setScope] = useState("");
  const [excludedScope, setExcludedScope] = useState("");
  const [inputRefsText, setInputRefsText] = useState("");
  const [checksText, setChecksText] = useState("");
  const [securityConstraints, setSecurityConstraints] = useState("");
  const [rollbackPlan, setRollbackPlan] = useState("");
  const [humanStatus, setHumanStatus] = useState<HumanBriefStatus>("draft");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (selectedTaskId === null) return;

    const input_references = inputRefsText
      .split(/\r?\n|,/)
      .map((s) => s.trim())
      .filter(Boolean);
    const acceptance_checks = checksText
      .split(/\r?\n/)
      .map((s) => s.trim())
      .filter(Boolean);

    const ok = await onCreateBrief(selectedTaskId, {
      purpose,
      scope,
      excluded_scope: excludedScope,
      input_references,
      acceptance_checks,
      security_constraints: securityConstraints,
      rollback_plan: rollbackPlan,
      human_status: humanStatus,
      expected_latest_version: briefs.length > 0 ? briefs[0].version : 0,
    });
    if (ok) {
      setPurpose("");
      setScope("");
      setExcludedScope("");
      setInputRefsText("");
      setChecksText("");
      setSecurityConstraints("");
      setRollbackPlan("");
      setHumanStatus("draft");
    }
  };

  return (
    <div className="card" style={{ marginBottom: "1rem" }}>
      <div className="card-header">
        <h3 className="card-title">Task Briefs &amp; Manual Antigravity Handoff</h3>
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <label htmlFor="brief-task-select" style={{ marginBottom: 0 }}>
            Task:
          </label>
          <select
            id="brief-task-select"
            className="select"
            value={selectedTaskId ?? ""}
            onChange={(e) =>
              onSelectTask(e.target.value ? Number(e.target.value) : null)
            }
          >
            {tasks.length === 0 && <option value="">No tasks available</option>}
            {tasks.map((task) => (
              <option key={task.id} value={task.id}>
                #{task.id} — {task.title}
              </option>
            ))}
          </select>
        </div>
      </div>

      {isOwner && selectedTaskId !== null && (
        <form onSubmit={handleSubmit} style={{ marginTop: "0.75rem", marginBottom: "1rem" }}>
          <div style={{ marginBottom: "0.5rem" }}>
            <label htmlFor="brief-purpose">Purpose</label>
            <input
              id="brief-purpose"
              className="input"
              value={purpose}
              onChange={(e) => setPurpose(e.target.value)}
              placeholder="Concise goal for Antigravity handoff"
              required
            />
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
            <div>
              <label htmlFor="brief-scope">In-Scope</label>
              <textarea
                id="brief-scope"
                className="textarea"
                value={scope}
                onChange={(e) => setScope(e.target.value)}
                rows={2}
              />
            </div>
            <div>
              <label htmlFor="brief-excluded">Excluded Scope</label>
              <textarea
                id="brief-excluded"
                className="textarea"
                value={excludedScope}
                onChange={(e) => setExcludedScope(e.target.value)}
                rows={2}
              />
            </div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem", marginTop: "0.5rem" }}>
            <div>
              <label htmlFor="brief-refs">Input References (comma/newline)</label>
              <textarea
                id="brief-refs"
                className="textarea"
                value={inputRefsText}
                onChange={(e) => setInputRefsText(e.target.value)}
                placeholder="docs/plans/04-workspace-artifacts.md"
                rows={2}
              />
            </div>
            <div>
              <label htmlFor="brief-checks">Acceptance Checks (one per line)</label>
              <textarea
                id="brief-checks"
                className="textarea"
                value={checksText}
                onChange={(e) => setChecksText(e.target.value)}
                placeholder="Run pytest and vitest"
                rows={2}
              />
            </div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 160px", gap: "0.5rem", marginTop: "0.5rem" }}>
            <div>
              <label htmlFor="brief-security">Security Constraints</label>
              <input
                id="brief-security"
                className="input"
                value={securityConstraints}
                onChange={(e) => setSecurityConstraints(e.target.value)}
              />
            </div>
            <div>
              <label htmlFor="brief-rollback">Rollback Plan</label>
              <input
                id="brief-rollback"
                className="input"
                value={rollbackPlan}
                onChange={(e) => setRollbackPlan(e.target.value)}
              />
            </div>
            <div>
              <label htmlFor="brief-status">Status</label>
              <select
                id="brief-status"
                className="select"
                value={humanStatus}
                onChange={(e) => setHumanStatus(e.target.value as HumanBriefStatus)}
              >
                <option value="draft">draft</option>
                <option value="ready_for_handoff">ready_for_handoff</option>
                <option value="handed_off">handed_off</option>
                <option value="approved">approved</option>
                <option value="archived">archived</option>
              </select>
            </div>
          </div>
          <button
            type="submit"
            className="btn"
            disabled={busy}
            style={{ marginTop: "0.65rem" }}
          >
            {busy ? "Saving..." : "Create Brief Version"}
          </button>
        </form>
      )}

      {briefs.length === 0 ? (
        <p style={{ color: "var(--text-muted)" }}>
          No versioned task briefs recorded for this task yet.
        </p>
      ) : (
        <div className="list-stack">
          {briefs.map((brief) => (
            <div key={brief.id} className="list-item">
              <div className="card-header">
                <strong>
                  v{brief.version} · {brief.human_status}
                </strong>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => onExportBrief(brief.task_id, brief.version)}
                >
                  Copy Handoff Brief v{brief.version}
                </button>
              </div>
              <p style={{ margin: "0.35rem 0" }}>{brief.purpose}</p>
              <div style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                by {brief.created_by} · {brief.created_at}
              </div>
            </div>
          ))}
        </div>
      )}

      {exportedBrief && (
        <div style={{ marginTop: "0.75rem" }}>
          <div style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginBottom: "0.25rem" }}>
            Exported Handoff Text (v{exportedBrief.version} · {exportedBrief.handoff_mode})
          </div>
          <pre className="code-block" aria-label="Exported Task Brief">
            {exportedBrief.rendered_text}
          </pre>
        </div>
      )}
    </div>
  );
}
