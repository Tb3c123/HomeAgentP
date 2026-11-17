# HomeAgentP

HomeAgentP is a personal AI workspace and home NAS operations platform.

## Architecture: B+ (Antigravity-first, Dashboard-light)

- Official Google Antigravity is used directly by the owner for AI coding, research and generating scripts. HomeAgentP does not wrap or programmatically control consumer Antigravity CLI.
- `homeagentp-web`: NAS dashboard, media/downloads overview, task board, script registry, reports and artifacts.
- `homeagentp-core`: read-only NAS/media monitoring, scheduled rules, alerts and scoped integrations.
- Git and files are the handoff mechanism between AI work and HomeAgentP.

## Development scope

1. Foundation: dashboard, authentication, SQLite metadata, task registry, two-container structure.
2. NAS Guardian: metrics, mount checks, service health, read-only alerts.
3. Media and downloads: Jellyfin, Sonarr, Radarr, Bazarr, Prowlarr, Seerr, qBittorrent.
4. Workspace: scripts, tasks, artifacts, Git handoff and task briefs.
5. Home Assistant, notifications, backup and operations.

## Safety

- No NAS deployment without explicit approval.
- No host root or Docker socket in HomeAgentP containers.
- No credentials or real `.env` in Git.
- No consumer OAuth proxy to Antigravity.
- Verify security and restore before production use.

## Status

Planning and documentation only. No HomeAgentP application has been deployed.


## Start here — Antigravity / external implementer (Tiếng Việt)

**Không giao lệnh “cài tất cả HomeAgentP lên NAS” ngay trong prompt đầu tiên.** Repo hiện là baseline tài liệu, chưa có Web/Core source hoặc Docker Compose đã được kiểm thử.

1. Đọc [Product scope](docs/00-project-scope.md): HomeAgentP bao gồm NAS, media, downloads, Home Assistant, alerts, AI workspace, developer, security; **không chỉ Dev**.
2. Đọc [AGENTS.md](AGENTS.md): các giới hạn mà AI coding agent và nhà thầu phải tuân thủ.
3. Đọc [Antigravity handoff & ready-to-copy prompts](docs/ANTIGRAVITY_HANDOFF.md): cách kết nối GitHub bằng Antigravity chính thức, quy trình giao việc, PR và deployment authorization.
4. Thực hiện [Phase 01 — Foundation](docs/plans/01-foundation.md) đầu tiên: Web/Core skeleton, auth, tasks, SQLite, script viewer, kiểm thử local. Không động tới NAS.
5. Mỗi Phase bắt buộc có Git branch/PR, evidence thực tế và owner review. Merge code không tự cấp quyền triển khai.
6. Chỉ sau khi Phase 01 đã được kiểm thử và review, xin **phê duyệt triển khai NAS riêng** với commands, ports, volumes, secrets, backup và rollback.

### Một prompt mở đầu ngắn cho Antigravity Remote Agent

```text
Hãy mở repository Tb3c123/HomeAgentP bằng Antigravity chính thức.
Đọc README.md, AGENTS.md, docs/00-project-scope.md,
docs/ANTIGRAVITY_HANDOFF.md và docs/plans/01-foundation.md.
Chỉ phân tích và lập implementation plan cho Phase 01.
Không thay đổi NAS, không deploy, không truy cập Docker Socket hay credentials,
không dùng Antigravity consumer CLI làm backend của HomeAgentP.
Trình bày danh sách file, API, schema, test cases, security risks,
sau đó dừng chờ tôi duyệt trước khi viết code.
```

**Alternative:** Google Antigravity Remote Control cho phép người dùng trực tiếp vận hành phiên CLI chính thức trên máy đang chạy; không đồng nghĩa HomeAgentP được gọi `agy` thay người dùng. Tham khảo [Remote Control](https://antigravity.google/docs/remote-control/) và [Remote Agents](https://antigravity.google/docs/remote-agents/).

**Safety notice:** NAS đang có container terminal Antigravity cũ dùng root và Docker Socket RW, với port ttyd rộng. Không dùng container đó để chạy AI-generated deployment scripts cho đến khi security review và hardening được hoàn tất. Không lưu credentials trong repo.
