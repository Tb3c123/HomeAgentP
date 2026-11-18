# Phase 06 — Final code review packet (owner decision required)

**Prepared 2026-11-18. Scope: GitHub code/isolated CI only. Not a production or NAS staging authorization.**

## Reviewed snapshot and evidence
- PR: https://github.com/Tb3c123/HomeAgentP/pull/7
- Snapshot with all-three-job CI PASS: `65d66236b7b103fb521231bfcd40799518236ea8`
- Actions run: https://github.com/Tb3c123/HomeAgentP/actions/runs/44252434971
- Jobs: Core (Ruff/Mypy/Pytest) **SUCCESS**; Web (TypeScript/Vitest/build) **SUCCESS**; Docker staging (isolated, no NAS) **SUCCESS**.
- This packet is documentation added after the verified snapshot. Verify any newer PR HEAD before a merge decision; never carry CI success across a new code commit.

## Review concerns from PR review `5950603505`

| Concern | Evidence of fix | Remaining limitation |
|---|---|---|
| Compose preflight may PASS host namespace/device escalations | `apps/core/src/homeagentp_core/operations/preflight.py` rejects host PID/IPC/UTS/cgroup/userns, devices, capability additions, volume inheritance, unexpected security options and unreviewed build/runtime settings. `tests/core/test_phase06_preflight.py` adds parameterized unsafe-option regression coverage | Preflight accepts only supplied decoded Compose JSON. It does **not** execute Docker or establish live settings, network access policy, image provenance, or full Compose schema safety; release proposal requires separate live checks |
| Atomic publication followed by failing directory fsync mislabeled as clean abort | `PublicationDurabilityError` distinguishes a target already published but not verified durable. Backup/restore regression tests inject fsync errors and verify target remains in place; runbook clarifies uncertain durability after publication | No power-loss test on real hardware; no production in-place cutover API. Backup/restore on NAS and rollback remain NOT_TESTED |

## Owner read-only discovery

Evidence in `06-preproduction-checklist.md`. Debian 12, Docker 29.9.2, Compose 5.6.1, 4 logical CPUs, ~15 GiB RAM, NVMe SSD, two 10TB ext4 mounted disks; 10 existing containers; ports 8310/8311 unoccupied in sample. **No NAS access was performed by the coding assistant.**

Owner actively uses the NAS `antigravity-cli` via Remote Control and other access methods; preserve CLI. Its root ttyd/agy, writable Docker socket, and 7681 all-interface bind are **recorded unresolved risks**, not Phase 06 changes. Do not alter CLI or Cloudflare without separate approval.

## Requested review decisions (separate gates)

**Gate M: merge PR #7 into main (source-code only):** confirm reviewed HEAD and passing CI, inspect behavioral change to scratch-only SQLite restore, acknowledge explicit `PublicationDurabilityError` contract, and approve merge. No merge will be performed by documentation alone.

**Gate S: isolated staging deployment on Debian 12 NAS:** later, after Gate M, approve specific commands/image digests, SSD-backed DB volume, non-root UID/GID, localhost port 8310, isolated network, locked-down secrets, backups and rollback. Current `deploy/casaos-compose.draft.yml` is NOT deployable: unverified `0.1.0-draft` images. `06-debian12-staging-proposal.md` is an architecture proposal, not an approved command sequence.

**Gate P: production:** independent signoff after actual NAS restore drill, safe rollback, HTTPS/ingress and service non-interference evidence, with HA/Telegram disabled until separately opted in.

## Decision as of writing

- Gate M: **AWAITING OWNER REVIEW / NOT APPROVED**
- Gate S: **NO-GO, NOT APPROVED**
- Gate P: **NO-GO, NOT APPROVED**
- Existing NAS services and CLI: **UNCHANGED**
