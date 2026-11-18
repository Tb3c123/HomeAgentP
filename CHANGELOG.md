# Changelog

All notable product-definition and documentation changes are recorded here. Versions below refer to **documentation milestones**, not necessarily Git tags.

## [Native-First Redesign decision] — 2026-11-18

### Approved
- Ưu tiên sử dụng **native Antigravity CLI (`agy`)**; không xây Director CLI hoặc UI riêng trong MVP.
- **Hoãn custom UI/UX** đến sau khi HomeAgentP được thiết kế, cài đặt, cấu hình và **xác nhận chạy thành công trên Home NAS**, rồi mới đánh giá nhu cầu.
- Giữ lại các tài liệu Approved v0.1.0–v0.5.0 như quyết định sản phẩm; đánh giá lại các giả định kỹ thuật và luồng session theo năng lực native đã được xác minh.
- Áp dụng **native-first, configuration-first, custom-code-last**; không triển khai tích hợp trái ToS.

### In progress (not approved)
- Native Antigravity CLI Capability & Compliance Validation: xác minh CLI, sessions, agents, rules/skills, quota, permission, headless và giới hạn ToS trước khi thiết kế triển khai.
- Không tạo hoặc phê duyệt tài liệu kỹ thuật từ kết luận kiểm chứng khi chưa có quyết định của Product Owner.

## [v0.5.0] — 2026-11-18

### Approved
- Information Architecture & Sitemap tại [docs/05-information-architecture.md](docs/05-information-architecture.md).
- Chốt A — Modular Workspace, gồm sáu module logic: Tasks, Workers, Knowledge, Approvals, Resources, Activity.
- Giữ Centralized Director và Task ID làm tham chiếu chính cho điều phối.
- **Phase 2 completed:** Main User Flow và Information Architecture đã Approved.

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

- **Latest approved documentation milestone:** v0.5.0 — Phase 2 Step 2.2.
- **Current work:** Native CLI Capability & Compliance Validation (draft; pending approval). Custom UI/UX deferred until confirmed successful Home NAS operation.
