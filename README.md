# HomeAgentP

**Smart Home AI Orchestrator** — hệ thống trợ lý quản lý nhà thông minh định hướng CLI-first, tổ chức theo kiến trúc Main Chat (Director) và các Sub-Chats (Workers).

- **Product Owner / Primary User:** Single Administrator
- **Automation:** Level B — Controlled Automation / Human-in-the-Loop
- **AI memory:** Long-term memory và feedback learning có kiểm soát, tham khảo Hermes Agent
- **Constraints:** Antigravity CLI (`agy`) phải tuân thủ ToS, giới hạn quota và cơ chế tích hợp được phép
- **Current focus:** Native-First Redesign — xác minh khả năng và ToS của Antigravity CLI trước khi thiết kế triển khai.
- **Latest approved step:** Phase 2, Step 2.2 — Information Architecture & Sitemap (v0.5.0)
- **Current step:** Native CLI Capability & Compliance Validation (**draft; chưa phê duyệt kết luận kỹ thuật**).

## Approved documents

| Step | Document | Status |
|---|---|---|
| 1.1 | [Product Vision](docs/01-product-vision.md) | Approved, v0.1.0 |
| 1.2 | [Target Users & Core Needs](docs/02-target-users.md) | Approved, v0.2.0 |
| 1.3 | [Core Features & MVP Scope](docs/03-mvp-scope.md) | Approved, v0.3.0 |
| 2.1 | [Main User Flow](docs/04-main-user-flow.md) | Approved, v0.4.0 |
| 2.2 | [Information Architecture & Sitemap](docs/05-information-architecture.md) | Approved, v0.5.0 |

## Native-First Redesign — Approved 2026-11-18

- **Runtime/UI chính:** dùng trực tiếp Antigravity CLI (`agy`) chính thức; không xây Director CLI riêng, CLI wrapper, command parser hay web/mobile dashboard cho MVP.
- **Thiết kế trước:** ưu tiên chức năng native, project instructions/configuration, cơ chế session/agents/skills được hỗ trợ và phù hợp ToS. Chỉ cân nhắc custom code cho khoảng trống đã được chứng minh.
- **Các tài liệu v0.1.0–v0.5.0:** giữ nguyên quyết định sản phẩm, nhưng giả định triển khai đa phiên, handoff và IA kỹ thuật phải được kiểm chứng lại. Không coi tài liệu cũ là bằng chứng hỗ trợ tính năng native.
- **Home NAS:** máy triển khai đích; tính tương thích phần cứng/OS và phương thức cài đặt chưa được xác minh.
- **UI/UX riêng:** **DEFERRED**. Chỉ xem xét lại **sau khi** HomeAgentP được thiết kế, cài đặt, cấu hình và xác nhận chạy thành công trên Home NAS; PO quyết định có cần UI riêng hay không.
- **Hiện tại:** chỉ xác minh khả năng `agy`, ToS và ranh giới tích hợp; không tự chuyển sang cài đặt hay triển khai.

See [CHANGELOG.md](CHANGELOG.md) for version history.

## Collaboration and approval workflow

1. Mỗi lần chỉ phân tích và đề xuất **một bước**.
2. Product Owner phê duyệt hoặc yêu cầu sửa.
3. Khi Product Owner nói **“duyệt”**: hoàn thiện tài liệu ở trạng thái Approved, commit/push lên GitHub, rồi chuyển sang đúng **một bước tiếp theo** (trạng thái draft).
4. Không mặc định phê duyệt bước mới. Không xóa hoặc ghi đè quyết định lịch sử nếu không có lý do xác minh được.
5. Chỉ tạo file tài liệu mới khi có nội dung thực sự cần lưu; tài liệu draft mới cần được Product Owner duyệt trước khi chính thức ghi vào repository.
6. Chỉ tạo Git tag cho mốc phát hành hoặc hoàn tất phase theo quyết định; không tự coi phiên bản tài liệu là tag đã tồn tại.

## Safety and feasibility

AI không được tự nâng quyền; các hành động rủi ro cao cần được chủ nhà xác nhận. Không giả định chức năng điều phối đa phiên CLI, session synchronization hay agent-to-agent automation được nhà cung cấp cho phép trước khi xác minh chính thức. Không dùng bên thứ ba để vượt giới hạn tài khoản/quota hoặc truy cập dịch vụ trái ToS.

## Repository

https://github.com/Tb3c123/HomeAgentP
