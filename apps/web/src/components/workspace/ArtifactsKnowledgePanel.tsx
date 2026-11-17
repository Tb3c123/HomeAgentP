import React, { useState } from "react";
import type {
  ArtifactFilterParams,
  ArtifactKind,
  ArtifactSourceType,
  WorkspaceArtifactCreateInput,
  WorkspaceArtifactDetailItem,
  WorkspaceArtifactItem,
} from "../../api/types";

interface ArtifactsKnowledgePanelProps {
  artifacts: WorkspaceArtifactItem[];
  selectedArtifact: WorkspaceArtifactDetailItem | null;
  filters: ArtifactFilterParams;
  isOwner: boolean;
  busy: boolean;
  onUpdateFilters: (next: ArtifactFilterParams) => void;
  onSelectArtifact: (slug: string, revision?: number) => Promise<void>;
  onRegisterArtifact: (payload: WorkspaceArtifactCreateInput) => Promise<boolean>;
}

export function ArtifactsKnowledgePanel({
  artifacts,
  selectedArtifact,
  filters,
  isOwner,
  busy,
  onUpdateFilters,
  onSelectArtifact,
  onRegisterArtifact,
}: ArtifactsKnowledgePanelProps) {
  const [slug, setSlug] = useState("");
  const [version, setVersion] = useState("1.0.0");
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState<ArtifactKind>("artifact");
  const [sourceType, setSourceType] = useState<ArtifactSourceType>("note");
  const [relPath, setRelPath] = useState("");
  const [gitUrl, setGitUrl] = useState("");
  const [summary, setSummary] = useState("");
  const [tagsText, setTagsText] = useState("");

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    const tags = tagsText
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    const ok = await onRegisterArtifact({
      slug,
      version,
      title,
      kind,
      source_type: sourceType,
      rel_path: relPath,
      git_url: gitUrl,
      summary,
      tags,
    });
    if (ok) {
      setSlug("");
      setTitle("");
      setRelPath("");
      setGitUrl("");
      setSummary("");
      setTagsText("");
    }
  };

  return (
    <div className="card" style={{ marginBottom: "1rem" }}>
      <div className="card-header">
        <h3 className="card-title">Artifacts &amp; Knowledge Index</h3>
        <span style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>
          {artifacts.length} item(s)
        </span>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr 1fr 1fr",
          gap: "0.5rem",
          marginTop: "0.75rem",
          marginBottom: "0.75rem",
        }}
      >
        <select
          aria-label="Filter artifact kind"
          className="select"
          value={filters.kind ?? ""}
          onChange={(e) =>
            onUpdateFilters({
              ...filters,
              kind: (e.target.value as ArtifactKind | "") || "",
              offset: 0,
            })
          }
        >
          <option value="">All kinds</option>
          <option value="artifact">artifact</option>
          <option value="knowledge">knowledge</option>
          <option value="plan">plan</option>
          <option value="runbook">runbook</option>
        </select>

        <select
          aria-label="Filter artifact source"
          className="select"
          value={filters.source_type ?? ""}
          onChange={(e) =>
            onUpdateFilters({
              ...filters,
              source_type: (e.target.value as ArtifactSourceType | "") || "",
              offset: 0,
            })
          }
        >
          <option value="">All sources</option>
          <option value="allowlisted_report">allowlisted_report</option>
          <option value="allowlisted_script">allowlisted_script</option>
          <option value="git_reference">git_reference</option>
          <option value="note">note</option>
        </select>

        <input
          aria-label="Filter artifact tag"
          className="input"
          value={filters.tag ?? ""}
          onChange={(e) =>
            onUpdateFilters({ ...filters, tag: e.target.value, offset: 0 })
          }
          placeholder="Filter by tag..."
        />

        <input
          aria-label="Search artifacts"
          className="input"
          value={filters.q ?? ""}
          onChange={(e) =>
            onUpdateFilters({ ...filters, q: e.target.value, offset: 0 })
          }
          placeholder="Search title or summary..."
        />
      </div>

      {isOwner && (
        <form onSubmit={handleRegister} style={{ marginBottom: "1rem" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 110px 1fr", gap: "0.5rem" }}>
            <input
              aria-label="Artifact slug"
              className="input"
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              placeholder="slug (e.g. phase-04-plan)"
              required
            />
            <input
              aria-label="Artifact version"
              className="input"
              value={version}
              onChange={(e) => setVersion(e.target.value)}
              placeholder="1.0.0"
              required
            />
            <input
              aria-label="Artifact title"
              className="input"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Artifact title"
              required
            />
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: "0.5rem", marginTop: "0.5rem" }}>
            <select
              aria-label="Artifact kind"
              className="select"
              value={kind}
              onChange={(e) => setKind(e.target.value as ArtifactKind)}
            >
              <option value="artifact">artifact</option>
              <option value="knowledge">knowledge</option>
              <option value="plan">plan</option>
              <option value="runbook">runbook</option>
            </select>
            <select
              aria-label="Artifact source type"
              className="select"
              value={sourceType}
              onChange={(e) => setSourceType(e.target.value as ArtifactSourceType)}
            >
              <option value="note">note</option>
              <option value="allowlisted_report">allowlisted_report</option>
              <option value="allowlisted_script">allowlisted_script</option>
              <option value="git_reference">git_reference</option>
            </select>
            <input
              aria-label="Artifact relative path"
              className="input"
              value={relPath}
              onChange={(e) => setRelPath(e.target.value)}
              placeholder="rel_path (optional)"
            />
            <input
              aria-label="Artifact tags"
              className="input"
              value={tagsText}
              onChange={(e) => setTagsText(e.target.value)}
              placeholder="tags: phase-04, design"
            />
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem", marginTop: "0.5rem" }}>
            <input
              aria-label="Artifact git URL"
              className="input"
              value={gitUrl}
              onChange={(e) => setGitUrl(e.target.value)}
              placeholder="https://github.com/owner/repo/blob/..."
            />
            <input
              aria-label="Artifact summary"
              className="input"
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
              placeholder="Short summary"
            />
          </div>
          <button type="submit" className="btn" disabled={busy} style={{ marginTop: "0.5rem" }}>
            {busy ? "Registering..." : "Register Artifact"}
          </button>
        </form>
      )}

      {artifacts.length === 0 ? (
        <p style={{ color: "var(--text-muted)" }}>No workspace artifacts match the current filter.</p>
      ) : (
        <div className="list-stack">
          {artifacts.map((art) => (
            <div key={art.id} className="list-item">
              <div className="card-header">
                <div>
                  <strong>{art.title}</strong>{" "}
                  <span style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>
                    ({art.slug} · rev {art.revision} · v{art.version})
                  </span>
                </div>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => onSelectArtifact(art.slug, art.revision)}
                >
                  Preview
                </button>
              </div>
              <div style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
                {art.kind} · {art.source_type}
                {art.tags.length > 0 ? ` · tags: ${art.tags.join(", ")}` : ""}
                {art.sha256 ? ` · sha256: ${art.sha256.slice(0, 12)}…` : ""}
              </div>
              {art.summary && <p style={{ margin: "0.35rem 0 0" }}>{art.summary}</p>}
            </div>
          ))}
        </div>
      )}

      {selectedArtifact && (
        <div style={{ marginTop: "0.85rem", paddingTop: "0.75rem", borderTop: "1px solid var(--border)" }}>
          <div className="card-header">
            <strong>
              Preview: {selectedArtifact.title} (rev {selectedArtifact.revision})
            </strong>
            <span className={`badge ${selectedArtifact.checksum_verified ? "badge-ok" : "badge-warn"}`}>
              {selectedArtifact.checksum_verified ? "SHA-256 Verified" : "Metadata / Unverified"}
            </span>
          </div>
          {selectedArtifact.git_url && (
            <div style={{ marginTop: "0.35rem", fontSize: "0.85rem" }}>
              Git Reference:{" "}
              <a
                href={selectedArtifact.git_url}
                target="_blank"
                rel="noopener noreferrer"
              >
                {selectedArtifact.git_url}
              </a>
            </div>
          )}
          {selectedArtifact.content !== null ? (
            <pre className="code-block" style={{ marginTop: "0.5rem" }}>
              {selectedArtifact.content}
            </pre>
          ) : (
            <p style={{ color: "var(--text-muted)", marginTop: "0.5rem" }}>
              No allowlisted file content attached for this artifact.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
