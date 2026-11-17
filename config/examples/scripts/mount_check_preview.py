#!/usr/bin/env python3
"""HomeAgentP Sample Script (Read-Only Registry Example)
Slug: mount-check-preview
Purpose: Verify expected mount paths exist in /proc/mounts (read-only).
NOTE: Execution from HomeAgentP Web/Core is disabled in Phase 01.
"""

from pathlib import Path


def check_mounts(targets: list[str]) -> dict[str, bool]:
    mounts_text = Path("/proc/mounts").read_text(encoding="utf-8")
    mounted_paths = {line.split()[1] for line in mounts_text.splitlines() if len(line.split()) > 1}
    return {target: (target in mounted_paths) for target in targets}


if __name__ == "__main__":
    print(check_mounts(["/mnt/disk1", "/mnt/disk2"]))
