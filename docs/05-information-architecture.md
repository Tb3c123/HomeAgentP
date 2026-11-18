# HomeAgentP — Information Architecture & Sitemap

> Document ID: HAP-IA-005  
> Version: v0.5.0  
> Phase: 2 — User Flows & Information Architecture  
> Step: 2.2 — Information Architecture & Sitemap  
> Status: **APPROVED**  
> Approved by: Product Owner  
> Approval date: 2026-11-18  
> Depends on: [Main User Flow v0.4.0](04-main-user-flow.md), [MVP Scope v0.3.0](03-mvp-scope.md)

## 1. Purpose

Xác định cấu trúc thông tin logic, các khu vực chức năng và nguyên tắc truy cập thông tin cho HomeAgentP MVP. Không quyết định database schema, API, giao diện màn hình, CLI syntax hoặc danh sách Worker thực tế.

## 2. Approved Design Direction

**A — Modular Workspace**, gồm sáu module logic và một điểm tương tác chính: **Centralized Director**. Administrator tương tác chủ yếu với Director, Director truy xuất thông tin liên quan và điều phối nhiệm vụ.

Modular Workspace **không** đồng nghĩa với sáu dịch vụ, sáu tiến trình, sáu cửa sổ hay sáu Worker cố định.

## 3. Information Architecture Principles

- **IA-01 — Centralized Entry Point:** Director là đầu mối chính của Administrator.
- **IA-02 — Clear Information Ownership:** Mỗi loại thông tin có module sở hữu logic.
- **IA-03 — Cross-Module References:** Liên kết theo định danh, tránh bản sao độc lập dễ sai lệch.
- **IA-04 — Minimal Context Retrieval:** Chỉ truy xuất context cần thiết.
- **IA-05 — Human Control:** Hành động nhạy cảm tuân thủ Approval Level B.
- **IA-06 — Traceability:** Có thể truy vết Task, quyết định, phản hồi và sự kiện quan trọng.
- **IA-07 — CLI-First:** Cấu trúc không phụ thuộc một giao diện trực quan cụ thể.

## 4. Logical Sitemap

```text
HomeAgentP
└── Director Workspace
    ├── 01. Tasks
    │   ├── Task List
    │   ├── Task Detail
    │   └── Task Result
    ├── 02. Workers
    │   ├── Worker Directory
    │   ├── Worker Profile
    │   └── Assignments
    ├── 03. Knowledge
    │   ├── Memory Library
    │   ├── Knowledge Detail
    │   └── Feedback
    ├── 04. Approvals
    │   ├── Pending Approvals
    │   ├── Approval Detail
    │   └── Decision History
    ├── 05. Resources
    │   ├── Usage Overview
    │   ├── Quota Status
    │   └── Context Guidance
    └── 06. Activity
        ├── Audit Timeline
        ├── Error Records
        └── Recovery References
```

Các mục con biểu thị đơn vị thông tin logic, **không** phải màn hình bắt buộc.

## 5. Module Responsibilities

### MOD-01 — Tasks
**Purpose:** Quản lý nhiệm vụ và vòng đời xử lý.  
**Core Information:** Task ID, objective, assigned Worker reference, Task status, expected result, verified result, related records.  
**Related Features:** CF-01, CF-02, CF-03.  
**Not owned:** Memory dài hạn và audit log nguyên bản.

### MOD-02 — Workers
**Purpose:** Danh mục năng lực và trách nhiệm Worker.  
**Core Information:** Worker identifier, domain responsibility, supported capabilities, authorized scope, related Task references.  
**Related Features:** CF-01, CF-02.  
**Not owned:** Phê duyệt hành động. Danh sách Worker chính thức chưa được quyết định.

### MOD-03 — Knowledge
**Purpose:** Tri thức dài hạn, tài liệu tham chiếu và bài học được xác nhận.  
**Core Information:** Knowledge identifier, content/summary, source, verification status, Task references, feedback.  
**Related Features:** CF-04, CF-08.  
**Not owned:** Trạng thái Task tức thời.

### MOD-04 — Approvals
**Purpose:** Yêu cầu phê duyệt và quyết định Administrator.  
**Core Information:** Approval identifier, related Task ID, proposed action, risk/approval reason, decision status, Administrator decision.  
**Related Feature:** CF-05.  
**Not owned:** Thực thi tác vụ. Approval status độc lập với Task status.

### MOD-05 — Resources
**Purpose:** Nhận biết usage, quota và giới hạn context AI.  
**Core Information:** Available usage data, known quota information, source/availability status, context guidance.  
**Related Feature:** CF-06.  
**Not owned:** Phân quyền. Không tạo số liệu quota giả khi nền tảng không cung cấp.

### MOD-06 — Activity
**Purpose:** Truy vết hành động, sự cố và thông tin phục hồi.  
**Core Information:** Activity identifier, Task reference (nếu có), event type, timestamp, result/error reference, recovery reference.  
**Related Feature:** CF-07.  
**Not owned:** Sửa ngược quyết định lịch sử. Không ghi secrets chưa che giấu.

## 6. Cross-Module Relationships

**Task ID** là tham chiếu chính đối với hoạt động điều phối. Một Task có thể tham chiếu Worker, Approval, Knowledge, Resource Usage và Activity. Mỗi module giữ quyền sở hữu logic dữ liệu của mình; Task Detail chỉ tổng hợp các tham chiếu liên quan.

Knowledge hoặc Activity có thể áp dụng cho nhiều Task, hoặc không liên quan Task cụ thể. Không ép mọi dữ liệu phải có Task ID.

## 7. Information Access Rules

- Administrator truy cập thông tin chủ yếu qua Director.
- Director truy vấn module liên quan, không tải toàn bộ thông tin mặc định.
- Worker chỉ nhận context và references trong quyền được cấp.
- Không chia sẻ toàn bộ memory cho mọi Worker.
- Phân biệt thông tin đã xác minh với nội dung chưa xác minh.
- Thiếu dữ liệu phải được báo rõ, không suy diễn thành số liệu.
- Đánh giá chính sách quyền và yêu cầu phê duyệt trước hành động nhạy cảm.

## 8. MVP Boundaries

**In Scope:** Sáu module logic; Task-centric references; truy xuất chọn lọc; information ownership; đầu mối tương tác qua Director.

**Out of Scope:** Web/mobile sitemap, dashboard đồ họa, database schema, API contract, CLI syntax, advanced vector search, danh sách Worker chính thức, multi-user hierarchy.

## 9. Acceptance Criteria

- [x] Chọn phương án A — Modular Workspace.
- [x] Xác định sáu module logic.
- [x] Xác định information ownership.
- [x] Xác định sitemap và các mục con.
- [x] Xác định liên kết thông tin qua tham chiếu.
- [x] Duy trì Centralized Director.
- [x] Mapping tương ứng với tám Core Features.
- [x] Product Owner phê duyệt v0.5.0.

## 10. Decision Log

| Date | ID | Decision | Status |
|---|---|---|---|
| 2026-11-18 | DEC-012 | Chọn A — Modular Workspace | Approved |
| 2026-11-18 | DEC-013 | Phê duyệt Information Architecture & Sitemap v0.5.0 | Approved |

## 11. Next Step Gate

**Phase 2 — Step 2.2: APPROVED and documented.**

**Phase 2: COMPLETED** (Main User Flow, Information Architecture).

**Phase 3 — Step 3.1: DRAFT / NOT APPROVED.** Chỉ trình đề xuất thành phần UI/CLI đầu tiên; chưa triển khai hoặc duyệt thiết kế ở bước tiếp theo.
