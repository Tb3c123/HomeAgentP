"""SQLite connection and consistent online backup management."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def create_connection(db_path: Path) -> sqlite3.Connection:
    """Create a configured SQLite connection with WAL mode and foreign keys enforced."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=15.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn


@contextmanager
def db_session(db_path: Path) -> Iterator[sqlite3.Connection]:
    """Provide a transactional SQLite connection that closes cleanly."""
    conn = create_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def backup_sqlite_database(source_db_path: Path, target_backup_path: Path) -> Path:
    """Perform a consistent atomic online backup of the SQLite database."""
    if not source_db_path.exists():
        raise FileNotFoundError(f"Source database does not exist: {source_db_path}")
    target_backup_path.parent.mkdir(parents=True, exist_ok=True)

    src_conn = create_connection(source_db_path)
    dst_conn = sqlite3.connect(str(target_backup_path))
    try:
        with dst_conn:
            src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()
    return target_backup_path
