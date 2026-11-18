"""Phase 06 isolated SQLite backup/restore regressions; never touch host databases."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from homeagentp_core.db.connection import (
    BackupError,
    backup_sqlite_database,
    create_connection,
    restore_sqlite_database,
    verify_sqlite_integrity,
)


def _init_db(path: Path) -> None:
    conn = create_connection(path)
    conn.execute("CREATE TABLE records(id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("INSERT INTO records(value) VALUES ('first')")
    conn.commit()
    conn.close()


def test_wal_online_backup_and_independent_restore(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    backup = tmp_path / "backup" / "verified.db"
    restored = tmp_path / "scratch" / "restored.db"
    _init_db(source)
    writer = create_connection(source)
    try:
        writer.execute("INSERT INTO records(value) VALUES ('second')")
        writer.commit()
        assert backup_sqlite_database(source, backup) == backup
        verify_sqlite_integrity(backup)
        digest_before = hashlib.sha256(backup.read_bytes()).hexdigest()
        assert restore_sqlite_database(backup, restored) == restored
        verify_sqlite_integrity(restored)
        assert hashlib.sha256(backup.read_bytes()).hexdigest() == digest_before
        with sqlite3.connect(restored) as conn:
            assert conn.execute("SELECT COUNT(*) FROM records").fetchone()[0] == 2
        assert writer.execute("SELECT COUNT(*) FROM records").fetchone()[0] == 2
    finally:
        writer.close()


def test_restore_never_overwrites_existing_target_or_sidecars(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    backup = tmp_path / "backup.db"
    target = tmp_path / "active.db"
    _init_db(source)
    backup_sqlite_database(source, backup)
    _init_db(target)
    conn = create_connection(target)
    try:
        conn.execute("INSERT INTO records(value) VALUES ('uncommitted')")
        original = target.read_bytes()
        with pytest.raises(BackupError, match="already exist"):
            restore_sqlite_database(backup, target)
        assert target.read_bytes() == original
        assert conn.execute("SELECT COUNT(*) FROM records").fetchone()[0] == 1
    finally:
        conn.close()

    sidecar_target = tmp_path / "sidecar-only.db"
    sidecar = Path(f"{sidecar_target}-wal")
    sidecar.write_text("sentinel", encoding="utf-8")
    with pytest.raises(BackupError, match="sidecars"):
        restore_sqlite_database(backup, sidecar_target)
    assert sidecar.read_text(encoding="utf-8") == "sentinel"


def test_restore_symlink_and_corrupt_backup_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    backup = tmp_path / "backup.db"
    _init_db(source)
    backup_sqlite_database(source, backup)
    link = tmp_path / "link.db"
    link.symlink_to(source)
    with pytest.raises(BackupError, match="symlink"):
        restore_sqlite_database(backup, link)

    corrupt = tmp_path / "corrupt.db"
    corrupt.write_bytes(b"not a sqlite database")
    with pytest.raises(BackupError):
        restore_sqlite_database(corrupt, tmp_path / "never-created.db")
    assert not (tmp_path / "never-created.db").exists()


def test_failed_backup_preserves_previous_valid_backup(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    backup = tmp_path / "saved.db"
    _init_db(source)
    backup_sqlite_database(source, backup)
    previous = backup.read_bytes()
    with pytest.raises(FileNotFoundError):
        backup_sqlite_database(tmp_path / "missing.db", backup)
    assert backup.read_bytes() == previous
