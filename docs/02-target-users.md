# HomeAgentP — Target Users & Core Needs

> Document ID: HAP-USR-002  
> Version: v0.2.0  
> Phase: 1 — Step 1.2 (Target Users & Core Needs)  
> Status: **APPROVED**  
> Approved by: Product Owner  
> Approval date: 2026-11-18  
> Depends on: [Product Vision v0.1.0](01-product-vision.md)

## 1. Purpose

Xác định người dùng ưu tiên, nhu cầu cốt lõi và giới hạn mô hình người dùng của HomeAgentP, làm đầu vào cho bước lựa chọn Core Features/MVP về sau. Tài liệu này không lựa chọn hoặc cam kết triển khai các tính năng cụ thể.

## 2. Target User Model

**Approved: Model A — Single Administrator.**

MVP phục vụ một người quản trị chính, đồng thời là **Product Owner**, **Home Administrator**, **AI System Operator** và **Approval Authority**.

- Không yêu cầu tài khoản đa người dùng, nhiều administrator hoặc phân quyền đa vai trò trong MVP.
- Các AI Agent (Director, Workers) là **system actors**, không phải người dùng.
- Single Administrator không đồng nghĩa AI có quyền tự trị toàn phần: hành động nhạy cảm vẫn phải được người quản trị phê duyệt theo Product Vision.
- Quyền agent phải giới hạn theo nhiệm vụ và tài nguyên (least privilege), dù hệ thống chỉ có một người dùng.

## 3. Primary Persona

**Persona ID:** PERSONA-001  
**Name:** Home Administrator  
**Type:** Proto-persona (giả định từ yêu cầu, chưa qua user research)

### Goals

- Quản lý công việc tại nhà qua một điểm điều phối thống nhất.
- Giảm thao tác thủ công và hướng dẫn lặp lại.
- Theo dõi kết quả, tiến độ và lỗi tác vụ.
- Cho phép tự động hóa mức B với quyền phê duyệt của chủ nhà.
- Bảo vệ quyền riêng tư, bảo mật và tối ưu tài nguyên AI.

### Assumed characteristics

- Sử dụng được giao diện dòng lệnh (CLI).
- Chịu trách nhiệm vận hành thiết bị hoặc dịch vụ gia đình.
- Muốn AI hỗ trợ chủ động trong giới hạn kiểm soát.
- Quan tâm quota, an toàn và khả năng truy vết.

### Pain points

- Nhiều hệ thống, công việc và ngữ cảnh rời rạc.
- Khó ghi nhớ lịch sử cấu hình, sự cố và quyết định.
- Phải nhắc lại thông tin đã từng cung cấp.
- Khó biết agent đang làm gì và tác vụ đã thực sự hoàn thành chưa.
- Nguy cơ tác vụ AI thực thi ngoài ý muốn hoặc chạm quota.

## 4. Core User Needs

**P0** = thiết yếu ở cấp nhu cầu; **P1** = quan trọng nhưng có thể cải tiến theo giai đoạn. Ưu tiên nhu cầu **không phải** cam kết đưa tính năng tương ứng vào MVP.

### NEED-01 — Centralized Task Coordination (P0)

**User need:** Là Home Administrator, tôi muốn giao yêu cầu qua một điểm điều phối trung tâm, thay vì tự phân công cho từng Worker.

**Expected outcome:** Biết yêu cầu đã được tiếp nhận và ai chịu trách nhiệm xử lý.

### NEED-02 — Task Visibility (P0)

**User need:** Tôi muốn xem trạng thái, kết quả và lỗi tác vụ để hiểu hệ thống đã làm gì.

**Expected outcome:** Trạng thái minh bạch; không báo hoàn thành nếu kết quả chưa được xác minh.

### NEED-03 — Controlled Automation (P0)

**User need:** Tôi muốn AI tự thực hiện tác vụ ít rủi ro nằm trong phạm vi được phép và xin phê duyệt trước hành động nhạy cảm.

**Expected outcome:** Tuân thủ Level B — Controlled Automation / Human-in-the-Loop.

### NEED-04 — Persistent Memory (P0)

**User need:** Tôi muốn HomeAgentP ghi nhớ, truy xuất thông tin hữu ích từ tương tác trước để không phải lặp lại hướng dẫn.

**Expected outcome:** Memory có liên quan và có thể kiểm tra, sửa, xóa.

### NEED-05 — Token and Quota Awareness (P0)

**User need:** Tôi muốn biết và hạn chế tiêu thụ tài nguyên AI, tránh context không cần thiết và rủi ro đạt giới hạn.

**Expected outcome:** Nhận biết rủi ro quota và có hành vi an toàn khi không đủ tài nguyên.

### NEED-06 — Feedback-Driven Improvement (P1)

**User need:** Tôi muốn hệ thống học từ phản hồi và kinh nghiệm sử dụng để cải thiện quy trình theo thời gian.

**Expected outcome:** Cải thiện mà không tự thay đổi chính sách, quyền hạn hoặc giới hạn an toàn.

## 5. User Model Boundaries

### In scope

- Một Administrator là người sử dụng và phê duyệt chính.
- CLI-first workflow theo Product Vision, phụ thuộc khả năng tích hợp hợp lệ.
- Agent chỉ hành động theo quyền được cấp.
- Có nhu cầu kiểm soát, truy vết và phản hồi trạng thái.

### Out of scope for MVP user model

- Multiple user accounts.
- Family member profiles.
- Multiple administrators.
- Role-based access control cho nhiều người dùng.
- Quy trình duyệt đa cấp giữa các thành viên.

Không loại trừ việc thêm các nhóm người dùng này trong tương lai.

## 6. Constraints

- Giữ nguyên Product Vision v0.1.0 và mô hình tự động hóa Level B.
- Agent không được tự nâng quyền hoặc tự duyệt hành động nhạy cảm.
- Không giả định Antigravity CLI cho phép tự động giao tiếp liên phiên nếu chưa xác minh.
- Không bypass quota, rate limit hoặc chính sách sử dụng.
- Bảo vệ thông tin cá nhân, secrets, thông tin thiết bị và dữ liệu gia đình.
- Khi lỗi, quota cạn hoặc đồng bộ chưa xác nhận: không báo tác vụ thành công giả.
- Triển khai kỹ thuật, cơ chế xác thực, memory storage và quota monitoring chưa chốt tại bước này.

## 7. Acceptance Criteria

- [x] Chọn Model A — Single Administrator.
- [x] Xác định Primary Persona (proto-persona).
- [x] Xác định sáu Core User Needs.
- [x] Phân loại P0/P1 ở cấp nhu cầu.
- [x] Xác nhận không yêu cầu multi-user trong MVP.
- [x] Duy trì Controlled Automation Level B.
- [x] Product Owner phê duyệt nội dung Step 1.2.

## 8. Decision Log

| Date | ID | Decision | Status |
|---|---|---|---|
| 2026-11-18 | DEC-004 | Chọn Single Administrator cho mô hình người dùng MVP | Approved |
| 2026-11-18 | DEC-005 | Phê duyệt Target Users & Core Needs v0.2.0 | Approved |
| 2026-11-18 | DEC-006 | Không bắt đầu bước tiếp theo khi chưa có chỉ đạo | Approved |

## 9. Gate

**Phase 1 — Step 1.2: APPROVED and documented.**

**Next step: NOT STARTED.** Chỉ bắt đầu khi Product Owner yêu cầu.
