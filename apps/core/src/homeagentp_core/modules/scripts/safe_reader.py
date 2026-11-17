"""TOCTOU-resistant read-only file reader using POSIX directory descriptors (openat).

Threat Model & Security Guarantees (F02):
1. Path Traversal ('..', absolute paths, null bytes, backslashes):
   - Input is parsed into pure single-segment component names; any '..', '.', empty, or
     rooted segment is rejected before touching the filesystem.
2. Symlink Escape & TOCTOU Race Mitigation:
   - User-space pre-checks (like Path.is_symlink() + Path.resolve() followed by open())
     are vulnerable to Time-of-Check to Time-of-Use (TOCTOU) races if an intermediate
     directory or file is swapped with a symlink between check and open.
   - Instead, this reader opens the allowlisted root directory with
     O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC and walks each single path segment
     using os.open(segment, ..., dir_fd=parent_fd).
   - Every intermediate component is opened with O_DIRECTORY | O_NOFOLLOW relative to its
     already-verified parent directory descriptor, and the leaf file is opened with
     O_RDONLY | O_NOFOLLOW relative to the final parent descriptor.
3. Hardlink, Special File, Size & Integrity Enforcement:
   - All validation (stat.S_ISREG, st_nlink == 1, st_size <= MAX_READ_BYTES) is performed
     via os.fstat(file_fd) on the already-open file descriptor, preventing post-open swaps.
   - Hardlinked files (st_nlink > 1), FIFOs, sockets, device nodes, and directories are
     rejected.
   - Optional expected_sha256 is verified against the exact bytes read from file_fd.
"""

from __future__ import annotations

import errno
import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

MAX_READ_BYTES = 256 * 1024  # 256 KiB cap for script/report viewing


class PathSecurityError(PermissionError):
    """Raised when a file access violates allowlist, traversal, symlink, or hardlink policies."""


@dataclass(frozen=True)
class SafeFileContent:
    rel_path: str
    content: str
    sha256: str
    size_bytes: int


def _parse_safe_relative_parts(relative_path: str) -> tuple[str, ...]:
    """Validate and split a relative path into safe single-component names."""
    cleaned = relative_path.strip()
    if not cleaned or "\x00" in cleaned or "\\" in cleaned:
        raise PathSecurityError("Empty or invalid file path.")
    if cleaned.startswith("/"):
        raise PathSecurityError("Absolute paths are not permitted.")

    raw_parts = cleaned.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise PathSecurityError(
            "Path traversal or redundant segments ('..', '.') are not permitted."
        )

    posix_path = PurePosixPath(*raw_parts)
    if posix_path.is_absolute() or any(p in {"", ".", ".."} for p in posix_path.parts):
        raise PathSecurityError("Path traversal segments are not permitted.")

    return posix_path.parts


def _open_allowlisted_root_fd(base_dir: Path) -> int:
    """Open the allowlisted base directory without following symlinks."""
    if not base_dir.exists() and not base_dir.is_symlink():
        raise FileNotFoundError(f"Allowlisted base directory does not exist: {base_dir}")

    dir_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        root_fd = os.open(str(base_dir), dir_flags)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Allowlisted base directory does not exist: {base_dir}") from exc
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR, errno.EACCES, errno.EPERM}:
            raise PathSecurityError("Allowlisted base directory must not be a symlink.") from exc
        raise PathSecurityError(f"Cannot open allowlisted base directory: {exc}") from exc

    try:
        st = os.fstat(root_fd)
        if not stat.S_ISDIR(st.st_mode):
            raise PathSecurityError("Allowlisted base path is not a directory.")
    except Exception:
        os.close(root_fd)
        raise

    return root_fd


def read_allowlisted_text_file(
    base_dir: Path,
    relative_path: str,
    *,
    expected_sha256: str | None = None,
) -> SafeFileContent:
    """Safely read a UTF-8 text file inside base_dir using kernel dir_fd traversal."""
    parts = _parse_safe_relative_parts(relative_path)

    dir_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    file_flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )

    current_dir_fd = _open_allowlisted_root_fd(base_dir)
    file_fd: int | None = None

    try:
        # Step through intermediate directories using openat(current_dir_fd, part)
        for part in parts[:-1]:
            try:
                next_dir_fd = os.open(part, dir_flags, dir_fd=current_dir_fd)
            except FileNotFoundError as exc:
                raise FileNotFoundError(
                    f"Directory component not found in allowlisted directory: {part}"
                ) from exc
            except OSError as exc:
                if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
                    raise PathSecurityError(
                        f"Symlinks are prohibited in allowlisted directory: {part}"
                    ) from exc
                raise PathSecurityError(
                    f"Failed to traverse directory component {part}: {exc}"
                ) from exc

            os.close(current_dir_fd)
            current_dir_fd = next_dir_fd

        # Open the leaf file relative to the final verified directory descriptor
        leaf_name = parts[-1]
        try:
            file_fd = os.open(leaf_name, file_flags, dir_fd=current_dir_fd)
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"File not found in allowlisted directory: {'/'.join(parts)}"
            ) from exc
        except OSError as exc:
            if exc.errno in {errno.ELOOP, errno.EISDIR}:
                raise PathSecurityError(
                    f"Symlinks or directories are prohibited as target file: {leaf_name}"
                ) from exc
            raise PathSecurityError(f"Failed to safely open file {leaf_name}: {exc}") from exc

        st = os.fstat(file_fd)
        if not stat.S_ISREG(st.st_mode):
            raise PathSecurityError("Target is not a regular file.")
        if st.st_nlink > 1:
            raise PathSecurityError(
                "Hardlinked files (st_nlink > 1) are prohibited in allowlisted directory."
            )
        if st.st_size > MAX_READ_BYTES:
            raise PathSecurityError(
                f"File size ({st.st_size} bytes) exceeds maximum "
                f"read limit ({MAX_READ_BYTES} bytes)."
            )

        chunks: list[bytes] = []
        bytes_read = 0
        while True:
            chunk = os.read(file_fd, 65536)
            if not chunk:
                break
            bytes_read += len(chunk)
            if bytes_read > MAX_READ_BYTES:
                raise PathSecurityError("File exceeds maximum read limit during read.")
            chunks.append(chunk)
        raw_bytes = b"".join(chunks)
    finally:
        if file_fd is not None:
            os.close(file_fd)
        os.close(current_dir_fd)

    actual_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    if expected_sha256 and actual_sha256.lower() != expected_sha256.lower():
        raise PathSecurityError(
            f"SHA-256 checksum mismatch for {'/'.join(parts)}: "
            f"expected {expected_sha256}, got {actual_sha256}"
        )

    try:
        text_content = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PathSecurityError("Binary files cannot be viewed in the text viewer.") from exc

    return SafeFileContent(
        rel_path="/".join(parts),
        content=text_content,
        sha256=actual_sha256,
        size_bytes=len(raw_bytes),
    )
