# Phase 06 — Live CLI preservation and read-only security review

**As of 2026-11-18:** Owner explicitly confirms the NAS-hosted `antigravity-cli` is actively used via multiple access methods (browser/remote domain/SSH). Do **not** remove it, require migration to a desktop app, stop it, restart it, rotate its secrets, remove its socket, edit its Compose definition, or change firewall/ingress without separate explicit approval. This security review does not authorize NAS mutations.

## Confirmed evidence (owner-supplied, not independently connected live inspection)

- Debian 12 (6.1.0-27-amd64); Docker Engine 29.9.2; Docker Compose v5.6.1.
- `antigravity-cli` listens on host TCP 7681 on 0.0.0.0 and IPv6, with `ttyd` and `agy` processes running as root.
- `antigravity-cli` has a writable bind mount at `/var/run/docker.sock`, `Privileged=false` and writable root filesystem.
- Portainer also mounts writable Docker socket; do not remove this without separate operational review.
- The observed socket binding does **not** prove Internet reachability; authentication, firewalls, Cloudflare routes, access policies and remote reachability remain UNKNOWN.
- HomeAgentP itself must not inherit this socket or privileged control surface.

## Owner-run read-only follow-up (do not paste secrets)

Use a trusted SSH session. Commands below do not modify services or read container environment/commandline arguments; if access is denied, record UNKNOWN instead of adding `sudo`:

```bash
# Do SSH and management proxies run as systemd services? No environment or secrets.
systemctl is-active ssh nginx caddy cloudflared tailscaled 2>/dev/null

# Socket exposure status, including loopback/IPv6 (no process arguments).
ss -lnt | grep -E '(:7681|:22|:80|:443|:9443|:8310|:8311)[[:space:]]'

# Docker restart policy and health for CLI only (no credentials).
docker inspect --format 'Restart={{.HostConfig.RestartPolicy.Name}} Health={{if .State.Health}}{{.State.Health.Status}}{{else}}not-configured{{end}}' antigravity-cli

# Whether relevant firewall tooling exists (does not interrogate or change policy).
command -v nft || true
command -v ufw || true
```

**Never post:** `docker inspect` with no explicit format, `docker compose config` with injected environment, process commandlines (`ps aux`), tokens, `.env`, ttyd authentication flags, Cloudflare Tunnel credentials, user session cookies, real public URLs or IPs. Redact host names and public endpoints.

## 2026-11-18 owner read-only follow-up observations

Observed from owner-supplied terminal outputs, not from a direct NAS connection:

- `systemctl is-active ssh nginx caddy cloudflared tailscaled`: `active`, `inactive`, `inactive`, `active`, `inactive` in that order. A running `cloudflared` service does not prove the tunnel's ingress rule or authentication policy.
- `ss -lnt`: TCP 7681 listening on `0.0.0.0` and `[::]`; SSH 22 also on both families; Portainer 9443 on both; TCP 80 listening. No TCP 8310/8311 observed. Open sockets alone do not prove Internet reachability.
- `antigravity-cli` Docker restart policy is `unless-stopped`; no Docker healthcheck configured.
- `command -v nft` and `command -v ufw` produced no path. This cannot establish whether kernel firewall, Docker chains, router rules or Cloudflare Access policies exist.
- `HomeAgentP CI` for commit `cbcfcf9` on PR #7 (run `44237669887`) reports completed/success, **isolated** CI only; deployment remains blocked.

### Next read-only gate (owner-operated)

Only disclose sanitized status, not routes, secrets or command-line contents:

```bash
# Service unit metadata only; never show cloudflared environment or full service commandline.
systemctl show cloudflared -p ActiveState -p SubState -p FragmentPath
# Whether tunnel process owns listening sockets; no secret command-line flags.
ss -lnt
# Cloudflared container check, if any (no environment).
docker ps --format '{{.Names}}'
```

For Internet reachability and authentication, use a trusted existing external client and manually verify the established approved URL requires authentication; do not post real public hostnames or URLs. A local tunnel service being active is not evidence that port 7681 is protected.

## Threat model and staged mitigation proposal (NOT EXECUTED)

1. **Access boundary first:** inventory LAN and remote paths and check authenticated access to ttyd/port 7681 from existing clients; document whether any domain/tunnel points to 7681. Prefer an authenticated reverse proxy / Cloudflare Access with a tested break-glass SSH route before limiting ingress.
2. **Constrain exposed port after separate approval:** allow required access paths only (e.g., localhost proxy + VPN for direct access). Do not change port mappings or firewall rules until login routes, rollback and maintenance window have been independently tested.
3. **Privilege separation:** identify why `agy` requires Docker socket write access. Where feasible, replace it with narrower scoped operations or a tightly constrained Docker socket proxy; do not assume `:ro` bind of Unix socket blocks daemon operations. The current root+socket setup remains high risk until fixed.
4. **CLI continuity:** capture persistent directories and state-dependency plan without copying secrets into Git, verify backup/restore for CLI workspace, preserve existing workflows and sessions. Any container recreation is a separate change.
5. **Portainer review separately:** it has a management reason for Docker socket access but still needs authenticated access, TLS and ingress restrictions; do not perturb existing Portainer while handling CLI.
6. **HomeAgentP B+ boundary:** keep HomeAgentP Core/Web non-root and without Docker socket; interact with CLI using task briefs, Git and artifact files rather than invoking CLI through unapproved consumer OAuth/API proxy or shell execution from Dashboard.

### Evidence gates

| Gate | Status |
|---|---|
| CLI is in active use and must remain online | CONFIRMED by owner |
| ttyd root + writable Docker socket + multi-interface port bind | CONFIRMED by owner command output |
| Public Internet reachability and ttyd authentication policy | UNKNOWN |
| Safe replacement ingress and independent SSH recovery path | NOT_TESTED |
| Container privilege reduction without disrupting CLI | NOT_TESTED |
| HomeAgentP deployment approval | NOT_APPROVED |

**No immediate hardening command is authorized.** A proposed change needs exact approved commands, dependency checks, downtime estimate, access rollback and owner signoff.
