# HomeAgentP — Main User Flow

> Document ID: HAP-FLOW-004  
> Version: v0.4.0  
> Phase: 2 — User Flows & Information Architecture  
> Step: 2.1 — Main User Flow  
> Status: **APPROVED**  
> Approved by: Product Owner  
> Approval date: 2026-11-18  
> Depends on: [Product Vision v0.1.0](01-product-vision.md), [Target Users v0.2.0](02-target-users.md), [MVP Scope v0.3.0](03-mvp-scope.md)

## 1. Purpose

Xác định Main User Flow cho MVP Orchestration-first.

**Approved interaction model: A — Centralized Director.** Administrator giao yêu cầu cho Director; Director làm đầu mối quản lý Task và điều phối các Worker. Đây là mô hình logic, không phải cam kết rằng Antigravity CLI hỗ trợ tự động gọi phiên khác.

## 2. Actors and Responsibilities

### Administrator
- Gửi yêu cầu và bổ sung thông tin khi cần.
- Phê duyệt hoặc từ chối những hành động nhạy cảm.
- Nhận kết quả và phản hồi.

### Director — Main Chat
- Tiếp nhận, phân tích, tạo Task và định tuyến.
- Kiểm tra quyền, rủi ro và điều kiện phê duyệt.
- Theo dõi trạng thái; xác minh kết quả Worker.
- Tổng hợp báo cáo; ghi lại trạng thái và tri thức có giá trị.

### Worker — Sub-Chat
- Nhận nhiệm vụ có phạm vi rõ ràng.
- Xử lý theo quyền và ràng buộc đã được giao.
- Trả kết quả, trạng thái, bằng chứng hoặc lý do bị chặn.
- Không tự nâng quyền hoặc tự quyết định Task tổng thể đã hoàn tất.

### Shared Project Knowledge
- Lưu Task Records, kết quả và quyết định phê duyệt.
- Lưu memory/audit có kiểm soát, ưu tiên nội dung đã xác minh.
- Là nguồn tham chiếu dùng chung, **không** giả định session tự đồng bộ bộ nhớ.

## 3. Main User Flow — Happy Path

1. Administrator gửi yêu cầu đến Director.
2. Director phân tích mục tiêu, phạm vi và dữ liệu cần thiết.
3. Nếu thiếu thông tin quan trọng, Director hỏi Administrator trước khi tiếp tục.
4. Director tạo Task Record (Task ID, priority, assigned Worker, expected output).
5. Director kiểm tra quyền và mức rủi ro của các hành động dự kiến.
6. Với hành động nhạy cảm hoặc chưa phân loại: giữ lại để Administrator phê duyệt.
7. Director chuẩn bị gói giao việc chuẩn, chỉ chứa context liên quan.
8. Nhiệm vụ được chuyển đến Worker bằng cơ chế hợp lệ (có thể thủ công).
9. Worker xử lý trong phạm vi cho phép và trả status, output, evidence.
10. Director đối chiếu kết quả với yêu cầu và kiểm tra tính đầy đủ.
11. Nếu đạt tiêu chí, Director chuyển Task sang `completed`.
12. Director lưu Task state, audit và tri thức quan trọng đã xác minh.
13. Director báo cáo kết quả cho Administrator và ghi nhận feedback nếu có.

Nếu nhiệm vụ chỉ cần hành động được cấp quyền và ít rủi ro, có thể tiếp tục mà không cần phê duyệt riêng. Phê duyệt không thay thế việc kiểm tra quyền thực thi.

## 4. Task Lifecycle

Các trạng thái tối thiểu đã được chốt trong MVP Scope:

| State | Meaning |
|---|---|
| `pending` | Task được tạo, chưa giao |
| `assigned` | Đã chỉ định Worker / chuẩn bị chuyển giao |
| `in_progress` | Đã xác nhận xử lý đang diễn ra |
| `blocked` | Đang chờ điều kiện, phê duyệt hoặc nguồn lực |
| `completed` | Kết quả đã được Director xác minh |
| `failed` | Không thể hoàn thành theo phương án hiện tại |

Director sở hữu trạng thái Task ở cấp điều phối. Worker chỉ báo cáo trạng thái công việc của mình. `assigned` không được hiểu là Worker đã nhận việc khi chưa có xác nhận chuyển giao.

**Approval** là điều kiện thực thi riêng, không phải một trạng thái Task mới; Task chờ duyệt có thể ở `blocked`.

## 5. Alternative Flows

### AF-01 — Missing Information
Director yêu cầu bổ sung thông tin trọng yếu, chưa giao tác vụ thiếu dữ liệu cần thiết.

### AF-02 — Approval Required
Hành động nhạy cảm hoặc chưa phân loại bị chặn; Administrator phải phê duyệt trước khi thực thi.

### AF-03 — Approval Denied
Không thực hiện hành động đã bị từ chối; lưu quyết định, báo cáo và xác định hướng xử lý thay thế nếu có.

### AF-04 — Worker Failure
Ghi nhận lỗi và cập nhật `blocked` nếu còn điều kiện để tiếp tục, hoặc `failed` khi không thể hoàn thành.

### AF-05 — Invalid Result
Nếu output không đúng expected output hoặc thiếu bằng chứng, không chuyển `completed`; yêu cầu bổ sung, xử lý lại hoặc báo lỗi.

### AF-06 — Insufficient Quota
Giới hạn/dừng an toàn khi thiếu tài nguyên và ghi nhận trạng thái đang dang dở; không bypass giới hạn.

### AF-07 — Session Handoff Failure
Khi chuyển giao thất bại hoặc chưa được xác nhận, không mặc định Worker nhận nhiệm vụ; không báo Task hoàn thành.

Cơ chế chi tiết về retries, timeouts, rollback thuộc Technical Specs (Phase 4).

## 6. Logical Data Exchange Contract

Gói giao việc tối thiểu:
- Task ID
- Objective
- Scope
- Relevant Context
- Constraints
- Expected Output

Kết quả Worker tối thiểu:
- Task ID
- Status
- Output
- Evidence / References
- Errors / Blockers

Các trường trên là **logic contract**; schema kỹ thuật và định dạng lưu trữ chưa được chốt.

## 7. Memory, Context and Token Principles

- Chỉ chuyển cho Worker ngữ cảnh cần thiết, không gửi toàn bộ lịch sử Main Chat mặc định.
- Ưu tiên tri thức quan trọng đã được xác minh.
- Memory có thể xem, sửa và xóa.
- Quota/usage được theo dõi khi có thông tin chính thức; dừng an toàn khi thiếu tài nguyên.
- Không dùng phương thức né quota hoặc vượt giới hạn nền tảng.

## 8. Security and Compliance

- Single Administrator, Controlled Automation Level B.
- Least privilege và approval gate cho hành động nhạy cảm.
- Không giả định Antigravity hỗ trợ automatic cross-session invocation.
- Chuyển giao thủ công hoặc dùng cơ chế chính thức được phép.
- Không đưa secrets không được che giấu vào context, task records hoặc audit logs.
- Tác vụ không được coi hoàn thành khi chưa có bằng chứng xác minh.

## 9. Acceptance Criteria

- [x] Chọn A — Centralized Director.
- [x] Xác định Actors và trách nhiệm.
- [x] Xác định Main User Flow.
- [x] Xác định sáu Task states tối thiểu.
- [x] Xác định bảy alternative flows.
- [x] Đặt nguyên tắc context, memory, token, approval và compliance.
- [x] Product Owner phê duyệt Main User Flow v0.4.0.

## 10. Decision Log

| Date | ID | Decision | Status |
|---|---|---|---|
| 2026-11-18 | DEC-010 | Chọn A — Centralized Director | Approved |
| 2026-11-18 | DEC-011 | Phê duyệt Main User Flow v0.4.0 | Approved |

## 11. Next Step Gate

**Phase 2 — Step 2.1: APPROVED and documented.**

**Phase 2 — Step 2.2: DRAFT / NOT APPROVED.** Bước tiếp theo chỉ được đề xuất để Product Owner xem xét.
