"""Strict read-only file reader that prevents path traversal and symlink escape."""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path

MAX_READ_BYTES = 256 * 1024  # 256 KiB cap for script/report viewing


class PathSecurityError(PermissionError):
    """Raised when a file access violates allowlist, traversal, or symlink policies."""


@dataclass(frozen=True)
class SafeFileContent:
    rel_path: str
    content: str
    sha256: str
    size_bytes: int


def read_allowlisted_text_file(
    base_dir: Path,
    relative_path: str,
    *,
    expected_sha256: str | None = None,
) -> SafeFileContent:
    """Safely read a UTF-8 text file inside base_dir without following symlinks.

    Security checks enforced:
    1. Reject empty paths, null bytes, absolute paths, or '..' segments.
    2. Reject if base_dir itself is a symlink or does not exist.
    3. Walk every path component from base_dir to target and reject any symlink.
    4. Resolve canonical paths and verify target is strictly inside resolved base_dir.
    5. Open file descriptor with O_RDONLY | O_NOFOLLOW (when supported by OS) and
       verify fstat confirms a regular file within size limits.
    6. Optionally verify SHA-256 digest matches expected_sha256.
    """
    cleaned = relative_path.strip()
    if not cleaned or "\x00" in cleaned:
        raise PathSecurityError("Empty or invalid file path.")

    candidate_rel = Path(cleaned)
    if candidate_rel.is_absolute():
        raise PathSecurityError("Absolute paths are not permitted.")

    if any(part in {"..", ""} for part in candidate_rel.parts):
        raise PathSecurityError("Path traversal segments ('..') are not permitted.")

    if not base_dir.exists():
        raise FileNotFoundError(f"Allowlisted base directory does not exist: {base_dir}")
    if base_dir.is_symlink():
        raise PathSecurityError("Allowlisted base directory must not be a symlink.")

    resolved_base = base_dir.resolve(strict=True)

    # Walk each segment and ensure no intermediate or leaf symlink exists
    current = base_dir
    for part in candidate_rel.parts:
        current = current / part
        if current.is_symlink():
            raise PathSecurityError(f"Symlinks are prohibited in allowlisted directory: {part}")

    if not current.exists():
        raise FileNotFoundError(f"File not found in allowlisted directory: {cleaned}")

    resolved_target = current.resolve(strict=True)
    if not resolved_target.is_relative_to(resolved_base) or resolved_target == resolved_base:
        raise PathSecurityError("Target resolves outside allowlisted base directory.")

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW

    try:
        fd = os.open(str(current), flags)
    except OSError as exc:
        raise PathSecurityError(f"Failed to safely open file: {exc}") from exc

    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise PathSecurityError("Target is not a regular file.")
        if st.st_size > MAX_READ_BYTES:
            raise PathSecurityError(
                f"File size ({st.st_size} bytes) exceeds maximum "
                f"read limit ({MAX_READ_BYTES} bytes)."
            )
        raw_bytes = os.read(fd, MAX_READ_BYTES + 1)
    finally:
        os.close(fd)

    if len(raw_bytes) > MAX_READ_BYTES:
        raise PathSecurityError("File exceeds maximum read limit.")

    actual_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    if expected_sha256 and actual_sha256.lower() != expected_sha256.lower():
        raise PathSecurityError(
            f"SHA-256 checksum mismatch for {cleaned}: "
            f"expected {expected_sha256}, got {actual_sha256}"
        )

    try:
        text_content = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PathSecurityError("Binary files cannot be viewed in the text viewer.") from exc

    return SafeFileContent(
        rel_path=str(candidate_rel.as_posix()),
        content=text_content,
        sha256=actual_sha256,
        size_bytes=len(raw_bytes),
    )
