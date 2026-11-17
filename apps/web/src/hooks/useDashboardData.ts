import { useCallback, useEffect, useState } from "react";
import { apiClient, ApiError } from "../api/client";
import type {
  AuditLogItem,
  AuthUser,
  DomainCategory,
  MediaAlertItem,
  MediaHistoryItem,
  MediaOverviewResponse,
  NasAlertItem,
  NasHistoryItem,
  NasStatusResponse,
  OverviewResponse,
  ProjectItem,
  RedactedSettings,
  ReportDetailItem,
  ReportSummaryItem,
  ScriptDetailItem,
  ScriptManifestItem,
  TaskItem,
  TaskPriority,
  TaskStatus,
} from "../api/types";

interface UseDashboardDataOptions {
  user: AuthUser | null;
  setUser: (user: AuthUser | null) => void;
  setErrorMsg: (msg: string) => void;
}

export interface CreateTaskInput {
  title: string;
  description: string;
  category: DomainCategory;
  priority: TaskPriority;
  task_brief_md: string;
  git_branch: string;
}

export function useDashboardData({ user, setUser, setErrorMsg }: UseDashboardDataOptions) {
  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [nasStatus, setNasStatus] = useState<NasStatusResponse | null>(null);
  const [nasHistory, setNasHistory] = useState<NasHistoryItem[]>([]);
  const [nasAlerts, setNasAlerts] = useState<NasAlertItem[]>([]);
  const [includeResolvedAlerts, setIncludeResolvedAlerts] = useState<boolean>(false);
  const [nasCollectBusy, setNasCollectBusy] = useState<boolean>(false);

  const [mediaOverview, setMediaOverview] = useState<MediaOverviewResponse | null>(null);
  const [mediaHistory, setMediaHistory] = useState<MediaHistoryItem[]>([]);
  const [mediaAlerts, setMediaAlerts] = useState<MediaAlertItem[]>([]);
  const [includeResolvedMediaAlerts, setIncludeResolvedMediaAlerts] =
    useState<boolean>(false);
  const [mediaCollectBusy, setMediaCollectBusy] = useState<boolean>(false);

  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [scripts, setScripts] = useState<ScriptManifestItem[]>([]);
  const [selectedScript, setSelectedScript] = useState<ScriptDetailItem | null>(null);
  const [reports, setReports] = useState<ReportSummaryItem[]>([]);
  const [selectedReport, setSelectedReport] = useState<ReportDetailItem | null>(null);
  const [auditLogs, setAuditLogs] = useState<AuditLogItem[]>([]);
  const [settingsData, setSettingsData] = useState<RedactedSettings | null>(null);

  const loadWorkspaceData = useCallback(async () => {
    try {
      setErrorMsg("");
      const [
        ov,
        nasSt,
        nasHist,
        nasAl,
        medOv,
        medHist,
        medAl,
        projs,
        tsks,
        scrs,
        reps,
        audits,
        cfg,
      ] = await Promise.all([
        apiClient.getOverview(),
        apiClient.getNasStatus(),
        apiClient.listNasHistory(15),
        apiClient.listNasAlerts(includeResolvedAlerts),
        apiClient.getMediaOverview().catch(() => null),
        apiClient.listMediaHistory(15).catch(() => []),
        apiClient.listMediaAlerts(includeResolvedMediaAlerts).catch(() => []),
        apiClient.listProjects(),
        apiClient.listTasks(),
        apiClient.listScripts(),
        apiClient.listReports(),
        apiClient.listAuditLogs(),
        apiClient.getSettings(),
      ]);
      setOverview(ov);
      setNasStatus(nasSt);
      setNasHistory(nasHist);
      setNasAlerts(nasAl);
      setMediaOverview(medOv);
      setMediaHistory(medHist);
      setMediaAlerts(medAl);
      setProjects(projs);
      setTasks(tsks);
      setScripts(scrs);
      setReports(reps);
      setAuditLogs(audits);
      setSettingsData(cfg);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setUser(null);
      } else if (err instanceof Error) {
        setErrorMsg(err.message);
      }
    }
  }, [includeResolvedAlerts, includeResolvedMediaAlerts, setErrorMsg, setUser]);

  useEffect(() => {
    if (user) {
      void loadWorkspaceData();
    }
  }, [user, loadWorkspaceData]);

  const resetDashboardData = useCallback(() => {
    setOverview(null);
    setNasStatus(null);
    setMediaOverview(null);
  }, []);

  const handleCollectNasSnapshot = async () => {
    if (!user) return;
    setNasCollectBusy(true);
    setErrorMsg("");
    try {
      const latest = await apiClient.collectNasSnapshot(user.csrf_token);
      setNasStatus(latest);
      const [hist, al, ov] = await Promise.all([
        apiClient.listNasHistory(15),
        apiClient.listNasAlerts(includeResolvedAlerts),
        apiClient.getOverview(),
      ]);
      setNasHistory(hist);
      setNasAlerts(al);
      setOverview(ov);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to collect NAS snapshot.");
    } finally {
      setNasCollectBusy(false);
    }
  };

  const handleToggleIncludeResolved = async (checked: boolean) => {
    setIncludeResolvedAlerts(checked);
    try {
      const al = await apiClient.listNasAlerts(checked);
      setNasAlerts(al);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to load alerts.");
    }
  };

  const handleCollectMediaSnapshot = async () => {
    if (!user) return;
    setMediaCollectBusy(true);
    setErrorMsg("");
    try {
      const latest = await apiClient.collectMediaSnapshot(user.csrf_token);
      setMediaOverview(latest);
      const [hist, al, ov] = await Promise.all([
        apiClient.listMediaHistory(15),
        apiClient.listMediaAlerts(includeResolvedMediaAlerts),
        apiClient.getOverview(),
      ]);
      setMediaHistory(hist);
      setMediaAlerts(al);
      setOverview(ov);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to collect Media snapshot.");
    } finally {
      setMediaCollectBusy(false);
    }
  };

  const handleToggleIncludeResolvedMedia = async (checked: boolean) => {
    setIncludeResolvedMediaAlerts(checked);
    try {
      const al = await apiClient.listMediaAlerts(checked);
      setMediaAlerts(al);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to load media alerts.");
    }
  };

  const createTask = async (input: CreateTaskInput): Promise<boolean> => {
    if (!user || !input.title.trim()) return false;
    try {
      setErrorMsg("");
      await apiClient.createTask(
        {
          title: input.title.trim(),
          description: input.description.trim(),
          category: input.category,
          status: "ready",
          priority: input.priority,
          task_brief_md: input.task_brief_md.trim(),
          git_branch: input.git_branch.trim(),
        },
        user.csrf_token,
      );
      await loadWorkspaceData();
      return true;
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to create task.");
      return false;
    }
  };

  const handleTaskStatusChange = async (taskId: number, status: TaskStatus) => {
    if (!user) return;
    try {
      setErrorMsg("");
      await apiClient.updateTask(taskId, { status }, user.csrf_token);
      await loadWorkspaceData();
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to update task.");
    }
  };

  const handleSelectScript = async (slug: string) => {
    try {
      setErrorMsg("");
      const detail = await apiClient.getScriptDetail(slug);
      setSelectedScript(detail);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to load script.");
    }
  };

  const handleSelectReport = async (slug: string) => {
    try {
      setErrorMsg("");
      const detail = await apiClient.getReportDetail(slug);
      setSelectedReport(detail);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to load report.");
    }
  };

  return {
    overview,
    nasStatus,
    nasHistory,
    nasAlerts,
    includeResolvedAlerts,
    nasCollectBusy,
    mediaOverview,
    mediaHistory,
    mediaAlerts,
    includeResolvedMediaAlerts,
    mediaCollectBusy,
    projects,
    tasks,
    scripts,
    selectedScript,
    reports,
    selectedReport,
    auditLogs,
    settingsData,
    loadWorkspaceData,
    resetDashboardData,
    handleCollectNasSnapshot,
    handleToggleIncludeResolved,
    handleCollectMediaSnapshot,
    handleToggleIncludeResolvedMedia,
    createTask,
    handleTaskStatusChange,
    handleSelectScript,
    handleSelectReport,
  };
}
