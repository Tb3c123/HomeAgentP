import React, { useState } from "react";
import type {
  DomainCategory,
  ProjectItem,
  TaskItem,
  TaskPriority,
  TaskStatus,
} from "../../api/types";
import type { CreateTaskInput } from "../../hooks/useDashboardData";
import { StatusBadge } from "../StatusBadge";

interface TasksSectionProps {
  projects: ProjectItem[];
  tasks: TaskItem[];
  onCreateTask: (input: CreateTaskInput) => Promise<boolean>;
  onTaskStatusChange: (taskId: number, status: TaskStatus) => Promise<void>;
}

export function TasksSection({
  projects,
  tasks,
  onCreateTask,
  onTaskStatusChange,
}: TasksSectionProps) {
  const [newTaskTitle, setNewTaskTitle] = useState<string>("");
  const [newTaskDesc, setNewTaskDesc] = useState<string>("");
  const [newTaskCategory, setNewTaskCategory] = useState<DomainCategory>("nas_guardian");
  const [newTaskPriority, setNewTaskPriority] = useState<TaskPriority>("medium");
  const [newTaskBranch, setNewTaskBranch] = useState<string>("");
  const [newTaskBrief, setNewTaskBrief] = useState<string>("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const created = await onCreateTask({
      title: newTaskTitle,
      description: newTaskDesc,
      category: newTaskCategory,
      priority: newTaskPriority,
      task_brief_md: newTaskBrief,
      git_branch: newTaskBranch,
    });
    if (created) {
      setNewTaskTitle("");
      setNewTaskDesc("");
      setNewTaskBranch("");
      setNewTaskBrief("");
    }
  };

  return (
    <section aria-label="Tasks and AI Handoff">
      <h2>Tasks, Projects &amp; Antigravity Handoff</h2>
      <div className="card-grid">
        <div className="card">
          <h3 className="card-title" style={{ marginBottom: "0.75rem" }}>
            Create New Task / Handoff Brief
          </h3>
          <form onSubmit={handleSubmit}>
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
                  onChange={(e) => void onTaskStatusChange(t.id, e.target.value as TaskStatus)}
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
  );
}
