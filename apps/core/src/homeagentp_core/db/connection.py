"""SQLite connection and atomic, integrity-verified online backup/restore management."""

from __future__ import annotations

import os
import secrets
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from pathlib import Path


class BackupError(RuntimeError):
    """Raised when an online SQLite backup or restore fails or fails integrity checks."""


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


def verify_sqlite_integrity(db_path: Path) -> None:
    """Verify that a SQLite database file passes integrity_check and foreign_key_check."""
    if not db_path.exists():
        raise BackupError(f"SQLite file does not exist: {db_path}")

    conn = sqlite3.connect(str(db_path))
    try:
        integrity_row = conn.execute("PRAGMA integrity_check;").fetchone()
        if integrity_row is None or str(integrity_row[0]).lower() != "ok":
            raise BackupError(f"SQLite integrity_check failed for {db_path}: {integrity_row}")

        fk_rows = conn.execute("PRAGMA foreign_key_check;").fetchall()
        if fk_rows:
            raise BackupError(
                f"SQLite foreign_key_check failed for {db_path}: {len(fk_rows)} errors"
            )
    except sqlite3.Error as exc:
        raise BackupError(f"SQLite verification failed for {db_path}: {exc}") from exc
    finally:
        conn.close()


def _fsync_file_and_parent(file_path: Path) -> None:
    """Flush file contents and parent directory entry to disk."""
    fd = os.open(str(file_path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

    if hasattr(os, "O_DIRECTORY"):
        dir_fd = os.open(str(file_path.parent), os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)


def backup_sqlite_database(
    source_db_path: Path,
    target_backup_path: Path,
    *,
    progress: Callable[[int, int, int], object] | None = None,
) -> Path:
    """Perform an atomic, integrity-verified online backup of the SQLite database (F03).

    Guarantees:
    - Writes to a hidden temporary file in the target directory first.
    - Runs PRAGMA integrity_check and PRAGMA foreign_key_check on the backup before publishing.
    - Converts backup journal mode to DELETE so the published backup is self-contained.
    - Uses os.replace() for atomic publication; any interruption or error unlinks the temp file
      and leaves any prior backup at target_backup_path untouched.
    """
    if not source_db_path.exists():
        raise FileNotFoundError(f"Source database does not exist: {source_db_path}")

    target_backup_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_backup_path = target_backup_path.parent / (
        f".{target_backup_path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
    )

    src_conn = create_connection(source_db_path)
    dst_conn: sqlite3.Connection | None = None
    try:
        dst_conn = sqlite3.connect(str(tmp_backup_path))
        with dst_conn:
            if progress is not None:
                src_conn.backup(dst_conn, pages=1, progress=progress)
            else:
                src_conn.backup(dst_conn)

        dst_conn.execute("PRAGMA journal_mode = DELETE;")
        dst_conn.commit()
        dst_conn.close()
        dst_conn = None

        verify_sqlite_integrity(tmp_backup_path)
        _fsync_file_and_parent(tmp_backup_path)
        os.replace(tmp_backup_path, target_backup_path)
        return target_backup_path
    except Exception as exc:
        if dst_conn is not None:
            with suppress(sqlite3.Error):
                dst_conn.close()
        for suffix in ("", "-wal", "-shm"):
            Path(f"{tmp_backup_path}{suffix}").unlink(missing_ok=True)
        if isinstance(exc, BackupError):
            raise
        raise BackupError(f"Database backup failed and was aborted cleanly: {exc}") from exc
    finally:
        src_conn.close()


def restore_sqlite_database(backup_path: Path, target_db_path: Path) -> Path:
    """Verify a backup file and atomically restore it to target_db_path."""
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup file does not exist: {backup_path}")

    verify_sqlite_integrity(backup_path)

    target_db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_restore_path = target_db_path.parent / (
        f".{target_db_path.name}.{os.getpid()}.{secrets.token_hex(4)}.restore.tmp"
    )

    src_conn = sqlite3.connect(str(backup_path))
    dst_conn: sqlite3.Connection | None = None
    try:
        dst_conn = sqlite3.connect(str(tmp_restore_path))
        with dst_conn:
            src_conn.backup(dst_conn)
        dst_conn.close()
        dst_conn = None

        verify_sqlite_integrity(tmp_restore_path)
        _fsync_file_and_parent(tmp_restore_path)

        # Remove stale WAL/SHM sidecars before atomic replacement
        for suffix in ("-wal", "-shm"):
            Path(f"{target_db_path}{suffix}").unlink(missing_ok=True)
        os.replace(tmp_restore_path, target_db_path)
        return target_db_path
    except Exception as exc:
        if dst_conn is not None:
            with suppress(sqlite3.Error):
                dst_conn.close()
        for suffix in ("", "-wal", "-shm"):
            Path(f"{tmp_restore_path}{suffix}").unlink(missing_ok=True)
        if isinstance(exc, BackupError):
            raise
        raise BackupError(f"Database restore failed and was aborted cleanly: {exc}") from exc
    finally:
        src_conn.close()
