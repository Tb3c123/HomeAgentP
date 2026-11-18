# Changelog

All notable product-definition and documentation changes are recorded here. Versions below refer to **documentation milestones**, not necessarily Git tags.

## [Phase 2 — Step 2.2 draft] — 2026-11-18

### In progress
- Bắt đầu đề xuất Information Architecture / Sitemap cho MVP.
- Chưa phê duyệt cấu trúc thông tin hoặc tạo tài liệu Step 2.2.

## [v0.4.0] — 2026-11-18

### Approved
- Main User Flow tại [docs/04-main-user-flow.md](docs/04-main-user-flow.md).
- Chọn **Centralized Director**: Administrator giao việc qua Director; Worker xử lý theo hợp đồng giao việc.
- Chốt sáu Task states và bảy alternative flows; phê duyệt và quota là các điều kiện kiểm soát.
- Chuyển giao giữa session chỉ qua phương thức hợp lệ; không giả định cross-session invocation tự động.

## [v0.3.0] — 2026-11-18

### Approved
- Core Features & MVP Scope tại [docs/03-mvp-scope.md](docs/03-mvp-scope.md).
- Chốt MVP **A — Orchestration-first**: 7 Must (CF-01 đến CF-07) và 1 Should tối giản (CF-08).
- Không yêu cầu kết nối và điều khiển thiết bị nhà thực tế trong MVP.
- Tôn trọng ToS và có thể chuyển giao giữa các phiên thủ công.
- **Phase 1 completed:** Product Vision, Target Users và MVP Scope đã Approved.

## [v0.2.0] — 2026-11-18

### Approved
- Target Users & Core Needs tại [docs/02-target-users.md](docs/02-target-users.md).
- Chọn **Model A — Single Administrator**.
- Xác định một primary proto-persona và 6 user needs: 5 P0, 1 P1.
- Giữ nguyên **Controlled Automation Level B** và quyền phê duyệt của chủ nhà.
- Multi-user và RBAC nhiều người dùng chưa thuộc MVP user model.

## [v0.1.0] — 2026-11-18

### Approved
- Product Vision tại [docs/01-product-vision.md](docs/01-product-vision.md).
- Định hướng Smart Home AI Orchestrator dựa trên Director–Worker / Multi-session.
- Trí nhớ dài hạn và feedback learning tham khảo Hermes Agent.
- Các nguyên tắc: kiểm soát token, ToS compliance, least privilege, auditability và Human-in-the-Loop.
- Tách biệt kiến trúc mong muốn với khả năng Antigravity CLI đã xác minh.

## Status

- **Latest approved documentation milestone:** v0.4.0 — Phase 2 Step 2.1.
- **Current work:** Phase 2 Step 2.2 — Information Architecture / Sitemap (draft; pending approval).
