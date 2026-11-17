import { requestJson } from "./client";
import type {
  ArtifactFilterParams,
  GitProvenanceCreateInput,
  GitProvenanceItem,
  GitProvenanceUpdateInput,
  TaskBriefCreateInput,
  TaskBriefExportItem,
  TaskBriefItem,
  WorkspaceArtifactCreateInput,
  WorkspaceArtifactDetailItem,
  WorkspaceArtifactItem,
} from "./types";

export const workspaceClient = {
  listTaskBriefs: (taskId: number) =>
    requestJson<TaskBriefItem[]>(`/api/v1/workspace/tasks/${taskId}/briefs`),

  createTaskBrief: (
    taskId: number,
    payload: TaskBriefCreateInput,
    csrfToken: string,
  ) =>
    requestJson<TaskBriefItem>(
      `/api/v1/workspace/tasks/${taskId}/briefs`,
      { method: "POST", body: JSON.stringify(payload) },
      csrfToken,
    ),

  exportTaskBrief: (taskId: number, version: number) =>
    requestJson<TaskBriefExportItem>(
      `/api/v1/workspace/tasks/${taskId}/briefs/${version}/export`,
    ),

  listArtifacts: (filters: ArtifactFilterParams = {}) => {
    const params = new URLSearchParams();
    if (filters.kind) params.set("kind", filters.kind);
    if (filters.source_type) params.set("source_type", filters.source_type);
    if (filters.tag) params.set("tag", filters.tag);
    if (filters.q) params.set("q", filters.q);
    if (filters.limit !== undefined) params.set("limit", String(filters.limit));
    if (filters.offset !== undefined) params.set("offset", String(filters.offset));
    const qs = params.toString();
    return requestJson<WorkspaceArtifactItem[]>(
      `/api/v1/workspace/artifacts${qs ? `?${qs}` : ""}`,
    );
  },

  createArtifact: (
    payload: WorkspaceArtifactCreateInput,
    csrfToken: string,
  ) =>
    requestJson<WorkspaceArtifactItem>(
      "/api/v1/workspace/artifacts",
      { method: "POST", body: JSON.stringify(payload) },
      csrfToken,
    ),

  getArtifactDetail: (slug: string, revision?: number) => {
    const qs = revision !== undefined ? `?revision=${revision}` : "";
    return requestJson<WorkspaceArtifactDetailItem>(
      `/api/v1/workspace/artifacts/${encodeURIComponent(slug)}${qs}`,
    );
  },

  listProvenance: (entityType?: "task" | "artifact", entityId?: number) => {
    const params = new URLSearchParams();
    if (entityType) params.set("entity_type", entityType);
    if (entityId !== undefined) params.set("entity_id", String(entityId));
    const qs = params.toString();
    return requestJson<GitProvenanceItem[]>(
      `/api/v1/workspace/provenance${qs ? `?${qs}` : ""}`,
    );
  },

  createProvenance: (
    payload: GitProvenanceCreateInput,
    csrfToken: string,
  ) =>
    requestJson<GitProvenanceItem>(
      "/api/v1/workspace/provenance",
      { method: "POST", body: JSON.stringify(payload) },
      csrfToken,
    ),

  updateProvenance: (
    linkId: number,
    payload: GitProvenanceUpdateInput,
    csrfToken: string,
  ) =>
    requestJson<GitProvenanceItem>(
      `/api/v1/workspace/provenance/${linkId}`,
      { method: "PATCH", body: JSON.stringify(payload) },
      csrfToken,
    ),
};
