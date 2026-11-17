import React, { useCallback, useEffect, useState } from "react";
import { apiClient, ApiError } from "./api/client";
import type {
  AuditLogItem,
  AuthUser,
  DomainCategory,
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
} from "./api/types";
import { StatusBadge } from "./components/StatusBadge";

export type NavSection =
  | "overview"
  | "nas"
  | "media_downloads"
  | "home_automation"
  | "tasks"
  | "scripts"
  | "reports"
  | "settings";

export const App: React.FC = () => {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [authChecking, setAuthChecking] = useState<boolean>(true);
  const [activeSection, setActiveSection] = useState<NavSection>("overview");
  const [errorMsg, setErrorMsg] = useState<string>("");

  // Login form state
  const [usernameInput, setUsernameInput] = useState<string>("admin");
  const [passwordInput, setPasswordInput] = useState<string>("");
  const [loginBusy, setLoginBusy] = useState<boolean>(false);

  // Dashboard state
  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [scripts, setScripts] = useState<ScriptManifestItem[]>([]);
  const [selectedScript, setSelectedScript] = useState<ScriptDetailItem | null>(null);
  const [reports, setReports] = useState<ReportSummaryItem[]>([]);
  const [selectedReport, setSelectedReport] = useState<ReportDetailItem | null>(null);
  const [auditLogs, setAuditLogs] = useState<AuditLogItem[]>([]);
  const [settingsData, setSettingsData] = useState<RedactedSettings | null>(null);

  // New task form state
  const [newTaskTitle, setNewTaskTitle] = useState<string>("");
  const [newTaskDesc, setNewTaskDesc] = useState<string>("");
  const [newTaskCategory, setNewTaskCategory] = useState<DomainCategory>("nas_guardian");
  const [newTaskPriority, setNewTaskPriority] = useState<TaskPriority>("medium");
  const [newTaskBranch, setNewTaskBranch] = useState<string>("");
  const [newTaskBrief, setNewTaskBrief] = useState<string>("");

  const loadWorkspaceData = useCallback(async () => {
    try {
      setErrorMsg("");
      const [ov, projs, tsks, scrs, reps, audits, cfg] = await Promise.all([
        apiClient.getOverview(),
        apiClient.listProjects(),
        apiClient.listTasks(),
        apiClient.listScripts(),
        apiClient.listReports(),
        apiClient.listAuditLogs(),
        apiClient.getSettings(),
      ]);
      setOverview(ov);
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
  }, []);

  useEffect(() => {
    let mounted = true;
    apiClient
      .getMe()
      .then((me) => {
        if (!mounted) return;
        setUser(me);
        setAuthChecking(false);
      })
      .catch(() => {
        if (!mounted) return;
        setUser(null);
        setAuthChecking(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (user) {
      void loadWorkspaceData();
    }
  }, [user, loadWorkspaceData]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoginBusy(true);
    setErrorMsg("");
    try {
      const authenticated = await apiClient.login(usernameInput, passwordInput);
      setUser(authenticated);
      setPasswordInput("");
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Login failed.");
    } finally {
      setLoginBusy(false);
    }
  };

  const handleLogout = async () => {
    if (!user) return;
    try {
      await apiClient.logout(user.csrf_token);
    } finally {
      setUser(null);
      setOverview(null);
    }
  };

  const handleCreateTask = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!user || !newTaskTitle.trim()) return;
    try {
      setErrorMsg("");
      await apiClient.createTask(
        {
          title: newTaskTitle.trim(),
          description: newTaskDesc.trim(),
          category: newTaskCategory,
          status: "ready",
          priority: newTaskPriority,
          task_brief_md: newTaskBrief.trim(),
          git_branch: newTaskBranch.trim(),
        },
        user.csrf_token,
      );
      setNewTaskTitle("");
      setNewTaskDesc("");
      setNewTaskBranch("");
      setNewTaskBrief("");
      await loadWorkspaceData();
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to create task.");
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

  if (authChecking) {
    return (
      <div className="login-wrapper">
        <div className="card login-card">
          <p>Checking session status...</p>
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="login-wrapper">
        <div className="card login-card">
          <h1 className="brand-title">HomeAgentP B+</h1>
          <p className="brand-subtitle">
            Home NAS Operations &amp; Personal AI Workspace (Phase 01 Foundation)
          </p>
          {errorMsg && (
            <div className="banner-error" role="alert">
              {errorMsg}
            </div>
          )}
          <form onSubmit={handleLogin} style={{ marginTop: "1rem" }}>
            <div style={{ marginBottom: "0.85rem" }}>
              <label htmlFor="login-username">Username</label>
              <input
                id="login-username"
                className="input"
                type="text"
                value={usernameInput}
                onChange={(e) => setUsernameInput(e.target.value)}
                required
              />
            </div>
            <div style={{ marginBottom: "1rem" }}>
              <label htmlFor="login-password">Password</label>
              <input
                id="login-password"
                className="input"
                type="password"
                value={passwordInput}
                onChange={(e) => setPasswordInput(e.target.value)}
                required
              />
            </div>
            <button className="btn" type="submit" disabled={loginBusy}>
              {loginBusy ? "Signing in..." : "Sign in to Dashboard"}
            </button>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Main Navigation">
        <div>
          <h1 className="brand-title">HomeAgentP B+</h1>
          <p className="brand-subtitle">Antigravity-first · Dashboard-light</p>
        </div>

        <nav className="nav-list">
          <button
            type="button"
            className={`nav-btn ${activeSection === "overview" ? "active" : ""}`}
            onClick={() => setActiveSection("overview")}
          >
            Overview
          </button>
          <button
            type="button"
            className={`nav-btn ${activeSection === "nas" ? "active" : ""}`}
            onClick={() => setActiveSection("nas")}
          >
            NAS Guardian
          </button>
          <button
            type="button"
            className={`nav-btn ${activeSection === "media_downloads" ? "active" : ""}`}
            onClick={() => setActiveSection("media_downloads")}
          >
            Media &amp; Downloads
          </button>
          <button
            type="button"
            className={`nav-btn ${activeSection === "home_automation" ? "active" : ""}`}
            onClick={() => setActiveSection("home_automation")}
          >
            Home Automation &amp; Telegram
          </button>
          <button
            type="button"
            className={`nav-btn ${activeSection === "tasks" ? "active" : ""}`}
            onClick={() => setActiveSection("tasks")}
          >
            Tasks &amp; AI Handoff ({tasks.length})
          </button>
          <button
            type="button"
            className={`nav-btn ${activeSection === "scripts" ? "active" : ""}`}
            onClick={() => setActiveSection("scripts")}
          >
            Scripts Registry ({scripts.length})
          </button>
          <button
            type="button"
            className={`nav-btn ${activeSection === "reports" ? "active" : ""}`}
            onClick={() => setActiveSection("reports")}
          >
            Reports &amp; Audit ({reports.length})
          </button>
          <button
            type="button"
            className={`nav-btn ${activeSection === "settings" ? "active" : ""}`}
            onClick={() => setActiveSection("settings")}
          >
            Settings &amp; Safety
          </button>
        </nav>

        <div style={{ marginTop: "auto", paddingTop: "1rem", borderTop: "1px solid var(--border)" }}>
          <div style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginBottom: "0.5rem" }}>
            Signed in as <strong>{user.username}</strong> ({user.role})
          </div>
          <button type="button" className="btn btn-secondary" onClick={handleLogout}>
            Sign out
          </button>
        </div>
      </aside>

      <main className="main-content">
        <div className="banner-notice">
          <strong>B+ Boundary Notice:</strong> Google Antigravity is operated directly by the owner.
          HomeAgentP never wraps consumer Antigravity CLI, never mounts Docker Socket, and never
          fabricates live NAS telemetry.
        </div>

        {errorMsg && (
          <div className="banner-error" role="alert">
            {errorMsg}
          </div>
        )}

        {activeSection === "overview" && overview && (
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
                    <StatusBadge
                      value={overview.domains.nas_guardian.metrics.mounts["/mnt/disk1"]}
                    />
                  </li>
                  <li>
                    <span>Mount /mnt/disk2</span>
                    <StatusBadge
                      value={overview.domains.nas_guardian.metrics.mounts["/mnt/disk2"]}
                    />
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
                      {overview.workspace_counts.reports_total} /{" "}
                      {overview.workspace_counts.audit_events}
                    </strong>
                  </li>
                </ul>
              </div>
            </div>
          </section>
        )}

        {activeSection === "nas" && overview && (
          <section aria-label="NAS Guardian Details">
            <h2>NAS Guardian (CPU, RAM, Storage Mounts &amp; Containers)</h2>
            <div className="card">
              <div className="card-header">
                <h3 className="card-title">Host Telemetry &amp; Mount Integrity</h3>
                <StatusBadge value={overview.domains.nas_guardian.status} />
              </div>
              <p>
                Target profile: Debian 12 Bookworm · Intel N200 · ext4 HDDs (<code>/mnt/disk1</code>
                , <code>/mnt/disk2</code>).
              </p>
              <p style={{ color: "var(--text-muted)" }}>
                In Phase 01 Foundation, no host paths or Docker sockets are mounted into HomeAgentP.
                All metrics below explicitly display <code>UNAVAILABLE</code> until the scoped
                read-only adapter in Phase 02 is approved.
              </p>
              <ul className="kv-list">
                <li>
                  <span>CPU Load</span>
                  <StatusBadge value={overview.domains.nas_guardian.metrics.cpu_load} />
                </li>
                <li>
                  <span>Memory Usage</span>
                  <StatusBadge value={overview.domains.nas_guardian.metrics.ram_usage} />
                </li>
                <li>
                  <span>/mnt/disk1 Mount Check</span>
                  <StatusBadge
                    value={overview.domains.nas_guardian.metrics.mounts["/mnt/disk1"]}
                  />
                </li>
                <li>
                  <span>/mnt/disk2 Mount Check</span>
                  <StatusBadge
                    value={overview.domains.nas_guardian.metrics.mounts["/mnt/disk2"]}
                  />
                </li>
                <li>
                  <span>SMART Disk Health</span>
                  <StatusBadge value={overview.domains.nas_guardian.metrics.smart_health} />
                </li>
              </ul>
            </div>
          </section>
        )}

        {activeSection === "media_downloads" && overview && (
          <section aria-label="Media and Downloads Details">
            <h2>Media Stack &amp; Downloads</h2>
            <div className="card-grid">
              <div className="card">
                <div className="card-header">
                  <h3 className="card-title">Media Services (Jellyfin &amp; *arr)</h3>
                  <StatusBadge value={overview.domains.media.status} />
                </div>
                <p style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>
                  {overview.domains.media.reason}
                </p>
                <ul className="kv-list">
                  {Object.entries(overview.domains.media.services).map(([name, st]) => (
                    <li key={name}>
                      <span style={{ textTransform: "capitalize" }}>{name}</span>
                      <StatusBadge value={st} />
                    </li>
                  ))}
                </ul>
              </div>
              <div className="card">
                <div className="card-header">
                  <h3 className="card-title">qBittorrent Downloads</h3>
                  <StatusBadge value={overview.domains.downloads.status} />
                </div>
                <p style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>
                  {overview.domains.downloads.reason}
                </p>
                <ul className="kv-list">
                  {Object.entries(overview.domains.downloads.metrics).map(([name, st]) => (
                    <li key={name}>
                      <span>{name.replace(/_/g, " ")}</span>
                      <StatusBadge value={st} />
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </section>
        )}

        {activeSection === "home_automation" && overview && (
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
        )}

        {activeSection === "tasks" && (
          <section aria-label="Tasks and AI Handoff">
            <h2>Tasks, Projects &amp; Antigravity Handoff</h2>
            <div className="card-grid">
              <div className="card">
                <h3 className="card-title" style={{ marginBottom: "0.75rem" }}>
                  Create New Task / Handoff Brief
                </h3>
                <form onSubmit={handleCreateTask}>
                  <div style={{ marginBottom: "0.65rem" }}>
                    <label htmlFor="task-title">Task Title</label>
                    <input
                      id="task-title"
                      className="input"
                      value={newTaskTitle}
                      onChange={(e) => setNewTaskTitle(e.target.value)}
                      placeholder="e.g., Phase 02 read-only mount check adapter"
                      required
                    />
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.65rem" }}>
                    <div>
                      <label htmlFor="task-category">Domain Category</label>
                      <select
                        id="task-category"
                        className="select"
                        value={newTaskCategory}
                        onChange={(e) => setNewTaskCategory(e.target.value as DomainCategory)}
                      >
                        <option value="nas_guardian">nas_guardian</option>
                        <option value="media">media</option>
                        <option value="downloads">downloads</option>
                        <option value="home_assistant">home_assistant</option>
                        <option value="monitoring">monitoring</option>
                        <option value="telegram">telegram</option>
                        <option value="scripts">scripts</option>
                        <option value="tasks">tasks</option>
                        <option value="ai_workspace">ai_workspace</option>
                        <option value="developer">developer</option>
                        <option value="security">security</option>
                      </select>
                    </div>
                    <div>
                      <label htmlFor="task-priority">Priority</label>
                      <select
                        id="task-priority"
                        className="select"
                        value={newTaskPriority}
                        onChange={(e) => setNewTaskPriority(e.target.value as TaskPriority)}
                      >
                        <option value="low">low</option>
                        <option value="medium">medium</option>
                        <option value="high">high</option>
                        <option value="critical">critical</option>
                      </select>
                    </div>
                  </div>
                  <div style={{ marginTop: "0.65rem" }}>
                    <label htmlFor="task-branch">Target Git Branch</label>
                    <input
                      id="task-branch"
                      className="input"
                      value={newTaskBranch}
                      onChange={(e) => setNewTaskBranch(e.target.value)}
                      placeholder="feature/phase-02-nas-guardian"
                    />
                  </div>
                  <div style={{ marginTop: "0.65rem" }}>
                    <label htmlFor="task-desc">Description</label>
                    <textarea
                      id="task-desc"
                      className="textarea"
                      rows={2}
                      value={newTaskDesc}
                      onChange={(e) => setNewTaskDesc(e.target.value)}
                    />
                  </div>
                  <div style={{ marginTop: "0.65rem", marginBottom: "0.85rem" }}>
                    <label htmlFor="task-brief">
                      Antigravity Task Brief (Copy &amp; paste into official Google Antigravity)
                    </label>
                    <textarea
                      id="task-brief"
                      className="textarea"
                      rows={3}
                      value={newTaskBrief}
                      onChange={(e) => setNewTaskBrief(e.target.value)}
                      placeholder="Allowed scope, excluded scope, acceptance criteria..."
                    />
                  </div>
                  <button className="btn" type="submit">
                    Save Task to SQLite
                  </button>
                </form>
              </div>

              <div className="card">
                <h3 className="card-title" style={{ marginBottom: "0.75rem" }}>
                  Registered Domains &amp; Projects ({projects.length})
                </h3>
                <ul className="kv-list">
                  {projects.map((p) => (
                    <li key={p.id}>
                      <div>
                        <strong>{p.name}</strong>
                        <div style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                          {p.description}
                        </div>
                      </div>
                      <StatusBadge value={p.category} />
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            <h3>Task Registry ({tasks.length})</h3>
            <div className="card-grid">
              {tasks.map((t) => (
                <div key={t.id} className="card">
                  <div className="card-header">
                    <h4 className="card-title">{t.title}</h4>
                    <StatusBadge value={t.status} />
                  </div>
                  <p style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>{t.description}</p>
                  <ul className="kv-list">
                    <li>
                      <span>Category</span>
                      <strong>{t.category}</strong>
                    </li>
                    <li>
                      <span>Priority</span>
                      <StatusBadge value={t.priority} />
                    </li>
                    <li>
                      <span>Git Branch</span>
                      <code>{t.git_branch || "not_set"}</code>
                    </li>
                    <li>
                      <span>Update Status</span>
                      <select
                        aria-label={`Status for ${t.title}`}
                        className="select"
                        style={{ width: "auto", padding: "0.2rem 0.5rem" }}
                        value={t.status}
                        onChange={(e) =>
                          void handleTaskStatusChange(t.id, e.target.value as TaskStatus)
                        }
                      >
                        <option value="backlog">backlog</option>
                        <option value="ready">ready</option>
                        <option value="in_progress">in_progress</option>
                        <option value="review">review</option>
                        <option value="done">done</option>
                        <option value="blocked">blocked</option>
                      </select>
                    </li>
                  </ul>
                  {t.task_brief_md && (
                    <div style={{ marginTop: "0.75rem" }}>
                      <div style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                        Task Brief (Git Handoff):
                      </div>
                      <pre className="code-viewer">{t.task_brief_md}</pre>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>
        )}

        {activeSection === "scripts" && (
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
                          onClick={() => void handleSelectScript(s.slug)}
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
        )}

        {activeSection === "reports" && (
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
                        onClick={() => void handleSelectReport(r.slug)}
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
        )}

        {activeSection === "settings" && settingsData && (
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
        )}
      </main>
    </div>
  );
};
