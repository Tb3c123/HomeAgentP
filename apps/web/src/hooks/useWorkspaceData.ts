import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../api/client";
import type {
  ArtifactFilterParams,
  AuthUser,
  GitProvenanceCreateInput,
  GitProvenanceItem,
  GitProvenanceUpdateInput,
  TaskBriefCreateInput,
  TaskBriefExportItem,
  TaskBriefItem,
  TaskItem,
  WorkspaceArtifactCreateInput,
  WorkspaceArtifactDetailItem,
  WorkspaceArtifactItem,
} from "../api/types";
import { workspaceClient } from "../api/workspaceClient";

function toErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    return err.message;
  }
  if (err instanceof Error) {
    return err.message;
  }
  return "Workspace operation failed.";
}

export function useWorkspaceData(user: AuthUser, tasks: TaskItem[]) {
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(
    tasks.length > 0 ? tasks[0].id : null,
  );
  const [briefs, setBriefs] = useState<TaskBriefItem[]>([]);
  const [exportedBrief, setExportedBrief] = useState<TaskBriefExportItem | null>(null);
  const [briefBusy, setBriefBusy] = useState(false);

  const [artifacts, setArtifacts] = useState<WorkspaceArtifactItem[]>([]);
  const [selectedArtifact, setSelectedArtifact] =
    useState<WorkspaceArtifactDetailItem | null>(null);
  const [artifactFilters, setArtifactFilters] = useState<ArtifactFilterParams>({
    kind: "",
    source_type: "",
    tag: "",
    q: "",
    limit: 50,
    offset: 0,
  });
  const [artifactBusy, setArtifactBusy] = useState(false);

  const [provenanceLinks, setProvenanceLinks] = useState<GitProvenanceItem[]>([]);
  const [provenanceBusy, setProvenanceBusy] = useState(false);

  const [workspaceError, setWorkspaceError] = useState("");
  const [workspaceNotice, setWorkspaceNotice] = useState("");

  useEffect(() => {
    if (selectedTaskId === null && tasks.length > 0) {
      setSelectedTaskId(tasks[0].id);
    }
  }, [selectedTaskId, tasks]);

  const loadBriefs = useCallback(async (taskId: number) => {
    setBriefBusy(true);
    try {
      const items = await workspaceClient.listTaskBriefs(taskId);
      setBriefs(items);
    } catch (err) {
      setWorkspaceError(toErrorMessage(err));
    } finally {
      setBriefBusy(false);
    }
  }, []);

  const loadArtifacts = useCallback(async (filters: ArtifactFilterParams) => {
    setArtifactBusy(true);
    try {
      const items = await workspaceClient.listArtifacts(filters);
      setArtifacts(items);
    } catch (err) {
      setWorkspaceError(toErrorMessage(err));
    } finally {
      setArtifactBusy(false);
    }
  }, []);

  const loadProvenance = useCallback(async () => {
    setProvenanceBusy(true);
    try {
      const items = await workspaceClient.listProvenance();
      setProvenanceLinks(items);
    } catch (err) {
      setWorkspaceError(toErrorMessage(err));
    } finally {
      setProvenanceBusy(false);
    }
  }, []);

  useEffect(() => {
    if (selectedTaskId !== null) {
      void loadBriefs(selectedTaskId);
    } else {
      setBriefs([]);
    }
  }, [selectedTaskId, loadBriefs]);

  useEffect(() => {
    void loadArtifacts(artifactFilters);
  }, [artifactFilters, loadArtifacts]);

  useEffect(() => {
    void loadProvenance();
  }, [loadProvenance]);

  const createBrief = async (
    taskId: number,
    payload: TaskBriefCreateInput,
  ): Promise<boolean> => {
    setWorkspaceError("");
    setWorkspaceNotice("");
    setBriefBusy(true);
    try {
      const created = await workspaceClient.createTaskBrief(
        taskId,
        payload,
        user.csrf_token,
      );
      setBriefs((prev) => [created, ...prev]);
      setWorkspaceNotice(`Created Task Brief v${created.version}.`);
      return true;
    } catch (err) {
      setWorkspaceError(toErrorMessage(err));
      return false;
    } finally {
      setBriefBusy(false);
    }
  };

  const exportBrief = async (taskId: number, version?: number): Promise<void> => {
    setWorkspaceError("");
    setWorkspaceNotice("");
    try {
      const exported = await workspaceClient.exportTaskBrief(taskId, version);
      setExportedBrief(exported);
      if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
        try {
          await navigator.clipboard.writeText(exported.rendered_text);
          setWorkspaceNotice(
            `Copied Task Brief v${exported.version} to clipboard (manual handoff).`,
          );
          return;
        } catch {
          // Clipboard permission may be unavailable in some browsers
        }
      }
      setWorkspaceNotice(
        `Exported Task Brief v${exported.version} for manual copy.`,
      );
    } catch (err) {
      setWorkspaceError(toErrorMessage(err));
    }
  };

  const registerArtifact = async (
    payload: WorkspaceArtifactCreateInput,
  ): Promise<boolean> => {
    setWorkspaceError("");
    setWorkspaceNotice("");
    setArtifactBusy(true);
    try {
      const created = await workspaceClient.createArtifact(
        payload,
        user.csrf_token,
      );
      setArtifacts((prev) => [created, ...prev]);
      setWorkspaceNotice(
        `Registered artifact "${created.slug}" rev ${created.revision}.`,
      );
      return true;
    } catch (err) {
      setWorkspaceError(toErrorMessage(err));
      return false;
    } finally {
      setArtifactBusy(false);
    }
  };

  const selectArtifact = async (slug: string, revision?: number): Promise<void> => {
    setWorkspaceError("");
    setArtifactBusy(true);
    try {
      const detail = await workspaceClient.getArtifactDetail(slug, revision);
      setSelectedArtifact(detail);
    } catch (err) {
      setWorkspaceError(toErrorMessage(err));
    } finally {
      setArtifactBusy(false);
    }
  };

  const createProvenance = async (
    payload: GitProvenanceCreateInput,
  ): Promise<boolean> => {
    setWorkspaceError("");
    setWorkspaceNotice("");
    setProvenanceBusy(true);
    try {
      const created = await workspaceClient.createProvenance(
        payload,
        user.csrf_token,
      );
      setProvenanceLinks((prev) => [created, ...prev]);
      setWorkspaceNotice(
        `Attached Git provenance #${created.id} (${created.verification_source}).`,
      );
      return true;
    } catch (err) {
      setWorkspaceError(toErrorMessage(err));
      return false;
    } finally {
      setProvenanceBusy(false);
    }
  };

  const updateProvenance = async (
    linkId: number,
    payload: GitProvenanceUpdateInput,
  ): Promise<boolean> => {
    setWorkspaceError("");
    setWorkspaceNotice("");
    setProvenanceBusy(true);
    try {
      const updated = await workspaceClient.updateProvenance(
        linkId,
        payload,
        user.csrf_token,
      );
      setProvenanceLinks((prev) =>
        prev.map((item) => (item.id === linkId ? updated : item)),
      );
      setWorkspaceNotice(`Updated Git provenance #${updated.id}.`);
      return true;
    } catch (err) {
      setWorkspaceError(toErrorMessage(err));
      return false;
    } finally {
      setProvenanceBusy(false);
    }
  };

  return {
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
  };
}
