# Phase 06 — Live NAS read-only inventory (owner-operated)

**State:** Procedure prepared only; **NOT EXECUTED** on the NAS. Owner authorization covers read-only inspection, not deployment, restart, credentials, or config mutation.

## Allowed scope

Run only on NAS terminal after owner has checked each command. These commands request information and print it to the terminal; they do not install packages, write files, invoke `docker compose up`, stop services, or read environment/secrets. Do not run via an unreviewed privileged ttyd container or paste into an automated agent. Prefer the NAS's trusted SSH/console session.

```bash
# 1. Host/OS and resources (read-only)
date -Is
uname -srm
cat /etc/os-release
id
nproc
free -h
uptime

# 2. Docker availability (read-only)
docker version --format 'Client={{.Client.Version}} Server={{.Server.Version}}'
docker compose version
docker ps --format 'name={{.Names}} image={{.Image}} ports={{.Ports}} status={{.Status}}'

# 3. Disks and mounts (metadata only; no SMART scans or disk writes)
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS,MODEL
df -hT
findmnt -rn -o TARGET,SOURCE,FSTYPE

# 4. Listening sockets (no process arguments or secrets)
ss -lnt

# 5. Service health (read-only; optional, may show inactive if not installed)
systemctl is-active docker
```

**If a command says permission denied:** note it as UNKNOWN. Do not escalate to `sudo` automatically, change groups, grant Docker socket access, or restart anything.

## What to share

- OS/distribution and kernel; CPU/RAM; Docker/Compose version
- Container names, ports, and health; whether existing media/download services are running
- Storage filesystem types, mountpoints and available space; whether expected media mounts are present
- Listening TCP ports (focus 8310, 8311, 7681, 8080, 8101), and any existing reverse proxy
- Indicate sensitive details **privately**; never include passwords, API tokens, container environment, `docker inspect` output, `.env`, Compose resolved config, VPN credentials, private keys, or access URLs with auth tokens

Review and redact IP addresses, hostnames, usernames, disk serials, and identifying mount names before sending the inventory into any public issue or repository. **Do not commit raw output**. An inventory alone does not authorize a NAS change or prove backup/recovery readiness.

## Next steps (separately authorized)

1. Compare findings to [pre-production acceptance matrix](06-preproduction-checklist.md). Leave missing evidence UNKNOWN/NOT_TESTED.
2. Independently review ttyd exposure and ingress without changing existing services.
3. Prepare an exact proposed Compose configuration (read-only mounts, isolated network, loopback binding, immutable image digests), backup destination and rollback; request separate owner approval.
4. Only after approval may an operator perform state-changing deployment, test restore or enable outbound HA/Telegram.
