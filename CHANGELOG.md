# Changelog

All notable product-definition and documentation changes are recorded here. Versions below refer to **documentation milestones**, not necessarily Git tags.

## [Home NAS Environment Survey — draft] — 2026-11-18

### In progress
- Thu thập OS, CPU, RAM, shell, kiến trúc runtime và quyền sử dụng trên Home NAS.
- Chưa xác minh local compatibility và chưa phê duyệt cài đặt.

## [v0.6.0] — 2026-11-18

### Approved
- Native CLI Capability Matrix: [docs/06-native-cli-capabilities.md](docs/06-native-cli-capabilities.md).
- Ưu tiên Native Agents & Swarm, nhưng chỉ sử dụng Swarm khi thích hợp và được phép; tránh tiêu hao quota không cần thiết.
- Các năng lực có trong tài liệu **chưa** được kiểm chứng trên Home NAS, gói tài khoản hoặc phiên bản CLI thực tế.
- Hoãn Hermes integration và custom UI/UX cho đến khi đủ điều kiện; UI/UX chỉ đánh giá lại sau khi hệ thống chạy thành công trên Home NAS.

## [Native-First Redesign decision] — 2026-11-18

### Approved
- Ưu tiên sử dụng **native Antigravity CLI (`agy`)**; không xây Director CLI hoặc UI riêng trong MVP.
- **Hoãn custom UI/UX** đến sau khi HomeAgentP được thiết kế, cài đặt, cấu hình và **xác nhận chạy thành công trên Home NAS**, rồi mới đánh giá nhu cầu.
- Giữ lại các tài liệu Approved v0.1.0–v0.5.0 như quyết định sản phẩm; đánh giá lại các giả định kỹ thuật và luồng session theo năng lực native đã được xác minh.
- Áp dụng **native-first, configuration-first, custom-code-last**; không triển khai tích hợp trái ToS.

### Validation boundaries
- Quyết định Native-First vẫn có hiệu lực; kiểm tra môi trường Home NAS là bước tiếp theo.
- Không xem Capability Matrix ở mức tài liệu như bằng chứng chạy thật hoặc cho phép tích hợp ngoài ToS.

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

- **Latest approved documentation milestone:** v0.6.0 — Native CLI Capability Matrix.
- **Current work:** Home NAS Environment Survey (draft; pending approval). Custom UI/UX deferred until confirmed successful Home NAS operation.
