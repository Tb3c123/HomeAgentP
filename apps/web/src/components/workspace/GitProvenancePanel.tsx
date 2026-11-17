import React, { useState } from "react";
import type {
  GitProvenanceCreateInput,
  GitProvenanceItem,
  GitProvenanceUpdateInput,
  ProvenanceCiStatus,
  ProvenanceEntityType,
  ProvenanceReviewStatus,
  TaskItem,
  WorkspaceArtifactItem,
} from "../../api/types";

interface GitProvenancePanelProps {
  tasks: TaskItem[];
  artifacts: WorkspaceArtifactItem[];
  provenanceLinks: GitProvenanceItem[];
  isOwner: boolean;
  busy: boolean;
  onCreateProvenance: (payload: GitProvenanceCreateInput) => Promise<boolean>;
  onUpdateProvenance: (
    linkId: number,
    payload: GitProvenanceUpdateInput,
  ) => Promise<boolean>;
}

export function GitProvenancePanel({
  tasks,
  artifacts,
  provenanceLinks,
  isOwner,
  busy,
  onCreateProvenance,
  onUpdateProvenance,
}: GitProvenancePanelProps) {
  const [entityType, setEntityType] = useState<ProvenanceEntityType>("task");
  const [entityId, setEntityId] = useState<string>(
    tasks.length > 0 ? String(tasks[0].id) : "1",
  );
  const [repoUrl, setRepoUrl] = useState("https://github.com/Tb3c123/HomeAgentP");
  const [branch, setBranch] = useState("");
  const [commitSha, setCommitSha] = useState("");
  const [prUrl, setPrUrl] = useState("");
  const [reviewStatus, setReviewStatus] = useState<ProvenanceReviewStatus>("pending");
  const [ciStatus, setCiStatus] = useState<ProvenanceCiStatus>("unknown");
  const [ciUrl, setCiUrl] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const parsedId = Number(entityId);
    if (!Number.isFinite(parsedId) || parsedId < 1) return;

    const ok = await onCreateProvenance({
      entity_type: entityType,
      entity_id: parsedId,
      repo_url: repoUrl,
      branch,
      commit_sha: commitSha,
      pr_url: prUrl,
      review_status: reviewStatus,
      ci_status: ciStatus,
      ci_url: ciUrl,
    });
    if (ok) {
      setBranch("");
      setCommitSha("");
      setPrUrl("");
      setCiUrl("");
    }
  };

  return (
    <div className="card">
      <div className="card-header">
        <h3 className="card-title">Git Provenance &amp; Manual PR/CI Links</h3>
        <span style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>
          {provenanceLinks.length} link(s)
        </span>
      </div>

      {isOwner && (
        <form onSubmit={handleSubmit} style={{ marginTop: "0.75rem", marginBottom: "1rem" }}>
          <div style={{ display: "grid", gridTemplateColumns: "140px 120px 1fr", gap: "0.5rem" }}>
            <select
              aria-label="Provenance entity type"
              className="select"
              value={entityType}
              onChange={(e) => {
                const nextType = e.target.value as ProvenanceEntityType;
                setEntityType(nextType);
                if (nextType === "task" && tasks.length > 0) {
                  setEntityId(String(tasks[0].id));
                } else if (nextType === "artifact" && artifacts.length > 0) {
                  setEntityId(String(artifacts[0].id));
                }
              }}
            >
              <option value="task">task</option>
              <option value="artifact">artifact</option>
            </select>
            <input
              aria-label="Provenance entity ID"
              className="input"
              type="number"
              min={1}
              value={entityId}
              onChange={(e) => setEntityId(e.target.value)}
              required
            />
            <input
              aria-label="GitHub repository URL"
              className="input"
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
              placeholder="https://github.com/owner/repo"
              required
            />
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.5rem", marginTop: "0.5rem" }}>
            <input
              aria-label="Provenance branch"
              className="input"
              value={branch}
              onChange={(e) => setBranch(e.target.value)}
              placeholder="feature/phase-04-workspace-artifacts"
            />
            <input
              aria-label="Provenance commit SHA"
              className="input"
              value={commitSha}
              onChange={(e) => setCommitSha(e.target.value)}
              placeholder="Commit SHA (7-40 hex)"
            />
            <input
              aria-label="Provenance PR URL"
              className="input"
              value={prUrl}
              onChange={(e) => setPrUrl(e.target.value)}
              placeholder="https://github.com/owner/repo/pull/4"
            />
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.5rem", marginTop: "0.5rem" }}>
            <select
              aria-label="Provenance review status"
              className="select"
              value={reviewStatus}
              onChange={(e) =>
                setReviewStatus(e.target.value as ProvenanceReviewStatus)
              }
            >
              <option value="none">review: none</option>
              <option value="pending">review: pending</option>
              <option value="approved">review: approved</option>
              <option value="changes_requested">review: changes_requested</option>
            </select>
            <select
              aria-label="Provenance CI status"
              className="select"
              value={ciStatus}
              onChange={(e) => setCiStatus(e.target.value as ProvenanceCiStatus)}
            >
              <option value="unknown">ci: unknown</option>
              <option value="pending">ci: pending</option>
              <option value="success">ci: success</option>
              <option value="failure">ci: failure</option>
            </select>
            <input
              aria-label="Provenance CI URL"
              className="input"
              value={ciUrl}
              onChange={(e) => setCiUrl(e.target.value)}
              placeholder="https://github.com/owner/repo/actions/runs/..."
            />
          </div>
          <button type="submit" className="btn" disabled={busy} style={{ marginTop: "0.5rem" }}>
            {busy ? "Attaching..." : "Attach Git Provenance"}
          </button>
        </form>
      )}

      {provenanceLinks.length === 0 ? (
        <p style={{ color: "var(--text-muted)" }}>No Git provenance links recorded yet.</p>
      ) : (
        <div className="list-stack">
          {provenanceLinks.map((link) => (
            <div key={link.id} className="list-item">
              <div className="card-header">
                <strong>
                  {link.entity_type} #{link.entity_id}
                </strong>
                <span className="badge badge-warn">
                  {link.verification_source === "manual_unverified"
                    ? "Manual (unverified)"
                    : "External CI Verified"}
                </span>
              </div>
              <div style={{ fontSize: "0.85rem", marginTop: "0.35rem" }}>
                Repo:{" "}
                <a href={link.repo_url} target="_blank" rel="noopener noreferrer">
                  {link.repo_url}
                </a>
                {link.branch && ` · branch: ${link.branch}`}
                {link.commit_sha && ` · sha: ${link.commit_sha.slice(0, 12)}`}
              </div>
              <div style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
                review: {link.review_status} · ci: {link.ci_status}
                {link.pr_url && (
                  <>
                    {" · "}
                    <a href={link.pr_url} target="_blank" rel="noopener noreferrer">
                      PR Link
                    </a>
                  </>
                )}
                {link.ci_url && (
                  <>
                    {" · "}
                    <a href={link.ci_url} target="_blank" rel="noopener noreferrer">
                      CI Run
                    </a>
                  </>
                )}
              </div>
              {isOwner && link.review_status !== "approved" && (
                <button
                  type="button"
                  className="btn btn-secondary"
                  style={{ marginTop: "0.45rem" }}
                  onClick={() =>
                    onUpdateProvenance(link.id, { review_status: "approved" })
                  }
                >
                  Mark Review Approved (Manual)
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
