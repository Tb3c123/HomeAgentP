import type { AuthUser, TaskItem } from "../../api/types";
import { useWorkspaceData } from "../../hooks/useWorkspaceData";
import { ArtifactsKnowledgePanel } from "./ArtifactsKnowledgePanel";
import { GitProvenancePanel } from "./GitProvenancePanel";
import { TaskBriefPanel } from "./TaskBriefPanel";

interface WorkspaceSectionProps {
  user: AuthUser;
  tasks: TaskItem[];
}

export function WorkspaceSection({ user, tasks }: WorkspaceSectionProps) {
  const isOwner = user.role === "owner";
  const {
    selectedTaskId,
    setSelectedTaskId,
    briefs,
    exportedBrief,
    briefBusy,
    artifacts,
    selectedArtifact,
    artifactFilters,
    setArtifactFilters,
    artifactBusy,
    provenanceLinks,
    provenanceBusy,
    workspaceError,
    workspaceNotice,
    createBrief,
    exportBrief,
    registerArtifact,
    selectArtifact,
    createProvenance,
    updateProvenance,
  } = useWorkspaceData(user, tasks);

  return (
    <section aria-label="Workspace and Artifacts">
      <h2>Workspace, Task Briefs &amp; Artifacts</h2>

      {!isOwner && (
        <div className="banner-notice" style={{ marginBottom: "0.85rem" }}>
          <strong>Viewer Read-Only Mode:</strong> You can inspect Task Briefs,
          artifacts, and Git provenance links. Owner role + CSRF token are required
          to create or update workspace records.
        </div>
      )}

      {workspaceError && (
        <div className="banner-error" role="alert" style={{ marginBottom: "0.85rem" }}>
          {workspaceError}
        </div>
      )}

      {workspaceNotice && (
        <div className="banner-notice" role="status" style={{ marginBottom: "0.85rem" }}>
          {workspaceNotice}
        </div>
      )}

      <TaskBriefPanel
        tasks={tasks}
        selectedTaskId={selectedTaskId}
        onSelectTask={setSelectedTaskId}
        briefs={briefs}
        exportedBrief={exportedBrief}
        isOwner={isOwner}
        busy={briefBusy}
        onCreateBrief={createBrief}
        onExportBrief={exportBrief}
      />

      <ArtifactsKnowledgePanel
        artifacts={artifacts}
        selectedArtifact={selectedArtifact}
        filters={artifactFilters}
        isOwner={isOwner}
        busy={artifactBusy}
        onUpdateFilters={setArtifactFilters}
        onSelectArtifact={selectArtifact}
        onRegisterArtifact={registerArtifact}
      />

      <GitProvenancePanel
        tasks={tasks}
        artifacts={artifacts}
        provenanceLinks={provenanceLinks}
        isOwner={isOwner}
        busy={provenanceBusy}
        onCreateProvenance={createProvenance}
        onUpdateProvenance={updateProvenance}
      />
    </section>
  );
}
