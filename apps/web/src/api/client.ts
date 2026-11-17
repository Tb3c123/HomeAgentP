import type {
  AuditLogItem,
  AuthUser,
  DomainCategory,
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
  TaskAttemptItem,
  TaskItem,
  TaskPriority,
  TaskStatus,
} from "./types";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function requestJson<T>(
  path: string,
  options: RequestInit = {},
  csrfToken?: string,
): Promise<T> {
  const headers = new Headers(options.headers || {});
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (csrfToken) {
    headers.set("X-CSRF-Token", csrfToken);
  }
  const response = await fetch(path, {
    ...options,
    headers,
    credentials: "include",
  });
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const errBody = (await response.json()) as { detail?: string };
      if (errBody.detail) {
        detail = errBody.detail;
      }
    } catch {
      // Fallback to status code message
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

export const apiClient = {
  getMe: () => requestJson<AuthUser>("/api/v1/auth/me"),
  login: (username: string, password: string) =>
    requestJson<AuthUser>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  logout: (csrfToken: string) =>
    requestJson<{ status: string }>(
      "/api/v1/auth/logout",
      { method: "POST" },
      csrfToken,
    ),
  getOverview: () => requestJson<OverviewResponse>("/api/v1/overview"),
  getSettings: () => requestJson<RedactedSettings>("/api/v1/settings"),
  listProjects: () => requestJson<ProjectItem[]>("/api/v1/projects"),
  listTasks: (category?: string, status?: string) => {
    const params = new URLSearchParams();
    if (category) params.set("category", category);
    if (status) params.set("status", status);
    const qs = params.toString();
    return requestJson<TaskItem[]>(`/api/v1/tasks${qs ? `?${qs}` : ""}`);
  },
  createTask: (
    payload: {
      project_id?: number | null;
      title: string;
      description: string;
      category: DomainCategory;
      status: TaskStatus;
      priority: TaskPriority;
      task_brief_md: string;
      git_branch: string;
    },
    csrfToken: string,
  ) =>
    requestJson<TaskItem>(
      "/api/v1/tasks",
      { method: "POST", body: JSON.stringify(payload) },
      csrfToken,
    ),
  updateTask: (
    taskId: number,
    payload: Partial<{
      status: TaskStatus;
      priority: TaskPriority;
      pr_url: string;
      git_branch: string;
      task_brief_md: string;
    }>,
    csrfToken: string,
  ) =>
    requestJson<TaskItem>(
      `/api/v1/tasks/${taskId}`,
      { method: "PATCH", body: JSON.stringify(payload) },
      csrfToken,
    ),
  createAttempt: (
    taskId: number,
    payload: {
      executor_type: "human" | "antigravity_handoff" | "scheduled_job";
      status: "started" | "succeeded" | "failed" | "cancelled" | "not_tested";
      summary: string;
    },
    csrfToken: string,
  ) =>
    requestJson<TaskAttemptItem>(
      `/api/v1/tasks/${taskId}/attempts`,
      { method: "POST", body: JSON.stringify(payload) },
      csrfToken,
    ),
  listScripts: () => requestJson<ScriptManifestItem[]>("/api/v1/scripts"),
  getScriptDetail: (slug: string) =>
    requestJson<ScriptDetailItem>(`/api/v1/scripts/${encodeURIComponent(slug)}`),
  listReports: () => requestJson<ReportSummaryItem[]>("/api/v1/reports"),
  getReportDetail: (slug: string) =>
    requestJson<ReportDetailItem>(`/api/v1/reports/${encodeURIComponent(slug)}`),
  listAuditLogs: () => requestJson<AuditLogItem[]>("/api/v1/audit-logs"),
  getNasStatus: () => requestJson<NasStatusResponse>("/api/v1/nas/status"),
  collectNasSnapshot: (csrfToken: string) =>
    requestJson<NasStatusResponse>(
      "/api/v1/nas/collect",
      { method: "POST" },
      csrfToken,
    ),
  listNasHistory: (limit = 20) =>
    requestJson<NasHistoryItem[]>(`/api/v1/nas/history?limit=${limit}`),
  listNasAlerts: (includeResolved = false) =>
    requestJson<NasAlertItem[]>(
      `/api/v1/nas/alerts?include_resolved=${includeResolved ? "true" : "false"}`,
    ),
};
