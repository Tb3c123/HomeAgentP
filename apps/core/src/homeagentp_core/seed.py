"""Idempotent seeding of minimal example metadata for HomeAgentP Phase 01."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from homeagentp_core.config import Settings


def seed_example_data(conn: sqlite3.Connection, settings: Settings) -> None:
    """Seed minimal baseline projects, tasks, script manifests, and reports if not present."""
    now_iso = datetime.now(UTC).isoformat()

    # 1. Seed script manifests from manifest.json if present
    manifest_file = settings.scripts_dir / "manifest.json"
    if manifest_file.exists() and not manifest_file.is_symlink():
        try:
            manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
            scripts_list = manifest_data.get("scripts", [])
            for item in scripts_list:
                conn.execute(
                    """
                    INSERT INTO script_manifests (
                        slug, name, description, category, rel_path, sha256,
                        review_status, is_executable_allowed, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                    ON CONFLICT(slug) DO UPDATE SET
                        name = excluded.name,
                        description = excluded.description,
                        category = excluded.category,
                        rel_path = excluded.rel_path,
                        sha256 = excluded.sha256,
                        review_status = excluded.review_status,
                        updated_at = excluded.updated_at
                    """,
                    (
                        str(item["slug"]),
                        str(item["name"]),
                        str(item.get("description", "")),
                        str(item.get("category", "nas_guardian")),
                        str(item["rel_path"]),
                        str(item["sha256"]),
                        str(item.get("review_status", "draft")),
                        now_iso,
                        now_iso,
                    ),
                )
        except (OSError, KeyError, ValueError):
            pass

    # 2. Seed sample report if present
    report_file = settings.reports_dir / "sample_daily_report.md"
    if report_file.exists() and not report_file.is_symlink():
        conn.execute(
            """
            INSERT INTO reports (slug, title, category, summary, rel_path, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(slug) DO NOTHING
            """,
            (
                "foundation-baseline-report",
                "HomeAgentP B+ — Foundation Baseline Report",
                "nas_guardian",
                "Initial verification report for Phase 01 Foundation read-only artifact viewer.",
                "sample_daily_report.md",
                now_iso,
            ),
        )

    if not settings.seed_examples:
        return

    # 3. Seed baseline projects across the HomeAgentP domains if table is empty
    project_count = int(conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0])
    if project_count == 0:
        sample_projects = [
            (
                "nas-guardian",
                "NAS Guardian & Storage Safety",
                "nas_guardian",
                (
                    "CPU, RAM, /mnt/disk1 & /mnt/disk2 mount integrity, "
                    "and read-only container health."
                ),
                "https://github.com/Tb3c123/HomeAgentP",
            ),
            (
                "media-and-downloads",
                "Media & Downloads (*arr, Jellyfin, qBittorrent)",
                "media",
                (
                    "Read-only status and queue monitoring for Jellyfin, Sonarr, "
                    "Radarr, Bazarr, Prowlarr, Seerr, and qBittorrent."
                ),
                "https://github.com/Tb3c123/HomeAgentP",
            ),
            (
                "home-automation-alerts",
                "Home Assistant & Telegram Alerts",
                "home_assistant",
                (
                    "Read-only Home Assistant status events, scheduled non-AI "
                    "reports, and Telegram notifications."
                ),
                "https://github.com/Tb3c123/HomeAgentP",
            ),
            (
                "ai-workspace-dev",
                "AI Workspace & Developer Handoff",
                "ai_workspace",
                (
                    "Task briefs, script registry, research artifacts, and Git/PR "
                    "handoff with official Google Antigravity."
                ),
                "https://github.com/Tb3c123/HomeAgentP",
            ),
        ]
        for slug, name, category, description, repo_url in sample_projects:
            conn.execute(
                """
                INSERT INTO projects (
                    slug, name, category, description, repo_url, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (slug, name, category, description, repo_url, now_iso, now_iso),
            )

        nas_proj = conn.execute(
            "SELECT id FROM projects WHERE slug = 'nas-guardian'"
        ).fetchone()
        nas_proj_id = int(nas_proj["id"]) if nas_proj else None

        conn.execute(
            """
            INSERT INTO tasks (
                project_id, title, description, category, status, priority,
                task_brief_md, git_branch, pr_url, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                nas_proj_id,
                "Phase 01 Foundation — Verify Web/Core Skeleton & SQLite Persistence",
                (
                    "Establish two-service Web + Core baseline with authentication, "
                    "task registry, and read-only script viewer."
                ),
                "developer",
                "in_progress",
                "high",
                (
                    "Scope: Phase 01 Foundation.\n"
                    "Constraints: No NAS modifications, no Docker socket, "
                    "no consumer CLI wrapping."
                ),
                "feature/phase-01-foundation",
                "",
                now_iso,
                now_iso,
            ),
        )
