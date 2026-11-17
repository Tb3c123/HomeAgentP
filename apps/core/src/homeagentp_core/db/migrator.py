"""Atomic SQLite schema migration runner with SHA-256 checksum verification."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def apply_migrations(conn: sqlite3.Connection, migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply all unapplied SQL migrations atomically and verify SHA-256 checksums.

    Atomicity Guarantee:
    Each migration file and its corresponding INSERT INTO schema_migrations are executed
    inside an explicit 'BEGIN IMMEDIATE ... COMMIT' transaction block. If any statement in
    the migration fails, the entire migration (including DDL statements) is rolled back.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            checksum TEXT NOT NULL,
            applied_at TEXT NOT NULL
        );
        """
    )
    conn.commit()

    existing_rows = conn.execute(
        "SELECT version, checksum FROM schema_migrations ORDER BY version ASC"
    ).fetchall()
    applied = {str(row["version"]): str(row["checksum"]) for row in existing_rows}

    applied_now: list[str] = []
    sql_files = sorted(migrations_dir.glob("*.sql"))
    for sql_file in sql_files:
        version = sql_file.stem
        sql_content = sql_file.read_text(encoding="utf-8")
        checksum = hashlib.sha256(sql_content.encode("utf-8")).hexdigest()

        if version in applied:
            if applied[version] != checksum:
                raise RuntimeError(
                    f"Migration checksum mismatch for {version}: "
                    f"expected {applied[version]}, got {checksum}"
                )
            continue

        if conn.in_transaction:
            conn.commit()

        try:
            conn.executescript(f"BEGIN IMMEDIATE;\n{sql_content}")
            conn.execute(
                "INSERT INTO schema_migrations (version, checksum, applied_at) VALUES (?, ?, ?)",
                (version, checksum, datetime.now(UTC).isoformat()),
            )
            conn.commit()
        except Exception:
            if conn.in_transaction:
                conn.rollback()
            raise

        applied_now.append(version)

    return applied_now


def get_current_schema_version(conn: sqlite3.Connection) -> str | None:
    """Return the latest applied migration version or None."""
    row = conn.execute(
        "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1"
    ).fetchone()
    return str(row["version"]) if row else None
