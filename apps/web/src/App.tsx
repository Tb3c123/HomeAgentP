import React, { useState } from "react";
import { MediaDashboard } from "./components/media/MediaDashboard";
import {
  ReportsSection,
  ScriptsSection,
  SettingsSection,
} from "./components/sections/AdminSections";
import { NasGuardianSection } from "./components/sections/NasGuardianSection";
import { HomeAutomationSection, OverviewSection } from "./components/sections/OverviewSection";
import { TasksSection } from "./components/sections/TasksSection";
import { useAuthSession } from "./hooks/useAuthSession";
import { useDashboardData } from "./hooks/useDashboardData";

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
  const [activeSection, setActiveSection] = useState<NavSection>("overview");
  const [errorMsg, setErrorMsg] = useState<string>("");

  const {
    user,
    setUser,
    authChecking,
    usernameInput,
    setUsernameInput,
    passwordInput,
    setPasswordInput,
    loginBusy,
    handleLogin,
    handleLogout: logoutSession,
  } = useAuthSession({ setErrorMsg });

  const {
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
    resetDashboardData,
    handleCollectNasSnapshot,
    handleToggleIncludeResolved,
    handleCollectMediaSnapshot,
    handleToggleIncludeResolvedMedia,
    createTask,
    handleTaskStatusChange,
    handleSelectScript,
    handleSelectReport,
  } = useDashboardData({ user, setUser, setErrorMsg });

  const handleLogout = async () => {
    await logoutSession();
    resetDashboardData();
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

        {activeSection === "overview" && overview && <OverviewSection overview={overview} />}

        {activeSection === "nas" && overview && (
          <NasGuardianSection
            nasStatus={nasStatus}
            nasAlerts={nasAlerts}
            nasHistory={nasHistory}
            nasCollectBusy={nasCollectBusy}
            includeResolvedAlerts={includeResolvedAlerts}
            onCollectSnapshot={handleCollectNasSnapshot}
            onToggleIncludeResolved={handleToggleIncludeResolved}
          />
        )}

        {activeSection === "media_downloads" && overview && (
          <MediaDashboard
            overview={overview}
            mediaOverview={mediaOverview}
            mediaAlerts={mediaAlerts}
            mediaHistory={mediaHistory}
            mediaCollectBusy={mediaCollectBusy}
            includeResolvedMediaAlerts={includeResolvedMediaAlerts}
            onCollectSnapshot={handleCollectMediaSnapshot}
            onToggleIncludeResolved={handleToggleIncludeResolvedMedia}
          />
        )}

        {activeSection === "home_automation" && overview && (
          <HomeAutomationSection overview={overview} />
        )}

        {activeSection === "tasks" && (
          <TasksSection
            projects={projects}
            tasks={tasks}
            onCreateTask={createTask}
            onTaskStatusChange={handleTaskStatusChange}
          />
        )}

        {activeSection === "scripts" && (
          <ScriptsSection
            scripts={scripts}
            selectedScript={selectedScript}
            onSelectScript={handleSelectScript}
          />
        )}

        {activeSection === "reports" && (
          <ReportsSection
            reports={reports}
            selectedReport={selectedReport}
            auditLogs={auditLogs}
            onSelectReport={handleSelectReport}
          />
        )}

        {activeSection === "settings" && settingsData && (
          <SettingsSection settingsData={settingsData} />
        )}
      </main>
    </div>
  );
};
