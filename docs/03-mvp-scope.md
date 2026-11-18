# HomeAgentP — Core Features & MVP Scope

> Document ID: HAP-MVP-003  
> Version: v0.3.0  
> Phase: 1 — Step 1.3 (Core Features & MVP Scope)  
> Status: **APPROVED**  
> Approved by: Product Owner  
> Approval date: 2026-11-18  
> Depends on: [Product Vision v0.1.0](01-product-vision.md); [Target Users v0.2.0](02-target-users.md)

## 1. MVP Strategy

**Approved direction: A — Orchestration-first.**

MVP tập trung chứng minh khả năng điều phối Director–Worker, quản lý trạng thái tác vụ, duy trì trí nhớ cơ bản, phê duyệt hành động quan trọng và nhận biết giới hạn tài nguyên AI. Không cần kết nối hay điều khiển thiết bị nhà thông minh thực tế.

## 2. MVP Objective

Một Home Administrator có thể giao yêu cầu cho Director, có phương án phân công, chuyển giao nhiệm vụ cho Worker thông qua phương thức hợp lệ, thu hồi và xác minh kết quả, theo dõi trạng thái, phê duyệt khi cần, và tái sử dụng tri thức từ công việc trước.

Việc chuyển giao **thủ công** giữa các phiên là phương án chấp nhận được nếu Antigravity không hỗ trợ tự động hóa phiên theo chính sách áp dụng.

## 3. Approved Core Features

| ID | Feature | Priority | MVP commitment |
|---|---|---|---|
| CF-01 | Director — Task Intake & Routing | Must | Yes |
| CF-02 | Worker Task Execution Contract | Must | Yes |
| CF-03 | Task State & Result Tracking | Must | Yes |
| CF-04 | Shared Knowledge & Basic Memory | Must | Yes |
| CF-05 | Human Approval Gate | Must | Yes |
| CF-06 | Token / Quota Awareness | Must | Yes |
| CF-07 | Audit & Recovery Basics | Must | Yes |
| CF-08 | Feedback & Learning Loop | Should | Minimal |

**Must** là năng lực cốt lõi cần chứng minh trong MVP. **Should** được triển khai tối giản và không được làm chậm các Must. Mức độ tự động hóa phụ thuộc tính khả thi và ToS.

## 4. Minimum Functional Outcomes

### CF-01 — Director Task Intake & Routing
Director tiếp nhận yêu cầu, tạo Task ID, xác định mục tiêu, phân loại, chỉ định trách nhiệm và định nghĩa kết quả mong đợi. Không mặc định tự khởi chạy Sub-Chat.

### CF-02 — Worker Task Execution Contract
Một mẫu giao việc chuẩn phải chứa Task ID, input, scope, constraints, expected output và kết quả/trạng thái phản hồi. Có thể dùng chuyển giao thủ công giữa các phiên.

### CF-03 — Task State & Result Tracking
Hỗ trợ các trạng thái tối thiểu: `pending`, `assigned`, `in_progress`, `blocked`, `completed`, `failed`. Chỉ xác nhận `completed` nếu kết quả được kiểm tra.

### CF-04 — Shared Knowledge & Basic Memory
Lưu/truy xuất thông tin đã xác nhận, quyết định và kết quả bằng tài liệu hay dữ liệu nhẹ có cấu trúc. Người dùng có thể xem, sửa, xóa kiến thức. Chưa cần vector search.

### CF-05 — Human Approval Gate
Theo Level B: tự động hóa chỉ với hành động ít rủi ro đã được cấp phép; hành động nhạy cảm hoặc chưa phân loại cần Administrator phê duyệt trước khi thực thi.

### CF-06 — Token/Quota Awareness
Theo dõi usage nếu nền tảng cung cấp thông tin chính thức; hạn chế context dư thừa và dừng an toàn khi quota không đủ. Không cam kết số liệu token chính xác nếu thiếu nguồn đo được hỗ trợ.

### CF-07 — Audit & Recovery Basics
Lưu quyết định, trạng thái và lỗi quan trọng để truy vết, biết tác vụ còn dang dở và tiếp tục theo cơ chế được phép. Không đưa secrets vào log.

### CF-08 — Feedback & Learning Loop
Cho phép Administrator phản hồi và xác nhận bài học để tái sử dụng. Chưa hỗ trợ tự điều chỉnh policy, quyền hạn hoặc tự học không giới hạn.

## 5. Out of Scope — MVP

- Điều khiển thiết bị vật lý, điện, camera, NAS, IoT hoặc an ninh thật.
- Tự động hóa session qua cách thức trái ToS hoặc chưa xác minh hợp lệ.
- Multi-user hoặc RBAC cho nhiều người dùng.
- Web dashboard, mobile app, voice assistant.
- Nhúng toàn bộ Hermes Agent, autonomous self-modifying agents.
- Vector database, advanced RAG và workflow engine phức tạp.

## 6. Hard Constraints

- Model A — Single Administrator.
- Controlled Automation Level B / Human-in-the-Loop.
- Tuân thủ Antigravity Terms và cơ chế CLI được phép.
- Không bypass quota, xoay tài khoản hoặc gọi endpoint không chính thức.
- Least privilege, kiểm soát phê duyệt, privacy và auditability.
- Không mặc định hỗ trợ automatic multi-session invocation.

## 7. MVP Acceptance Scenarios

**A — Normal Task:** Administrator gửi yêu cầu → Director tạo và giao task → Worker xử lý qua phương thức hợp lệ → kết quả được xác minh → trạng thái `completed` → tri thức hữu ích được lưu.

**B — Sensitive Action:** Worker đề xuất hành động nhạy cảm → hành động bị giữ lại → Administrator đồng ý hoặc từ chối → quyết định được ghi nhận.

**C — Interrupted Task:** Lỗi hoặc gián đoạn phiên → lưu trạng thái chưa hoàn thành → có thể xác định bước tiếp tục, không báo thành công giả.

**D — Memory Reuse:** Tác vụ tương tự → truy xuất thông tin đã xác nhận trước đó → hạn chế lặp lại hướng dẫn.

**E — Quota Limit:** Khi có chỉ báo usage/quota → giới hạn hoặc dừng công việc an toàn, không vượt chính sách.

## 8. Validation Gates

Trước khi triển khai cần xác minh tài liệu chính thức và điều khoản áp dụng về:
- Antigravity CLI, quản lý session và tự động hóa liên phiên.
- Mức độ hỗ trợ thống kê usage/quota.
- Phương thức chuyển giao tác vụ hợp lệ.
- Tính tương thích và khả năng tái sử dụng mô hình memory/feedback từ Hermes Agent.

## 9. Decision Log

| Date | ID | Decision | Status |
|---|---|---|---|
| 2026-11-18 | DEC-007 | Chọn MVP hướng A — Orchestration-first | Approved |
| 2026-11-18 | DEC-008 | Phê duyệt CF-01 đến CF-07 Must, CF-08 Should (minimal) | Approved |
| 2026-11-18 | DEC-009 | Không điều khiển thiết bị thật trong MVP đầu tiên | Approved |

## 10. Approval and Next Gate

**Phase 1 — Step 1.3: APPROVED.**

**Phase 1: PRODUCT DEFINITION COMPLETED** (Product Vision, Target Users, MVP Scope).

**Phase 2 — Step 2.1: NOT APPROVED.** Chỉ nghiên cứu và đề xuất User Flow cho Product Owner ở bước tiếp theo.
