#!/usr/bin/env bash
# HomeAgentP Sample Script (Read-Only Registry Example)
# Slug: disk-usage-report
# Purpose: Inspect filesystem usage on standard mount points without root privileges.
# NOTE: Execution from HomeAgentP Web/Core is disabled in Phase 01.

set -euo pipefail

echo "=== HomeAgentP Storage Snapshot (Read-Only) ==="
df -h -x tmpfs -x devtmpfs
