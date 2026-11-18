# HomeAgentP — Product Vision

> Document ID: HAP-PV-001  
> Version: v0.1.0  
> Phase: 1 — Step 1.1 (Product Vision)  
> Status: **APPROVED**  
> Approved by: Product Owner  
> Approval date: 2026-11-18  
> Repository: https://github.com/Tb3c123/HomeAgentP

## 1. Product Overview

- **Product Name:** HomeAgentP
- **Product Category:** Smart Home AI Orchestrator
- **Primary Interface:** Antigravity CLI (`agy`), subject to technical and policy validation.
- **Automation Model:** Level B — Controlled Automation / Human-in-the-Loop.

HomeAgentP là hệ thống AI đa tác nhân hỗ trợ điều phối, giám sát và tự động hóa hoạt động quản lý nhà thông minh. Sản phẩm tổ chức một Main Chat (Director) và nhiều Sub-Chats (Workers) chuyên trách theo miền, ghi nhớ kinh nghiệm dài hạn, và tối ưu token trong khi duy trì quyền kiểm soát của chủ nhà.

## 2. Product Vision

Xây dựng một trợ lý AI quản lý nhà thông minh có khả năng phân công nhiệm vụ cho các agent chuyên trách, duy trì và tái sử dụng tri thức giữa các phiên, học từ phản hồi, cải thiện quy trình theo thời gian và tự động thực hiện **chỉ các hành động ít rủi ro đã được cho phép**. Hệ thống ưu tiên quyền kiểm soát của chủ nhà, an toàn, minh bạch, bảo vệ quyền riêng tư, hiệu quả token và tuân thủ chính sách nền tảng.

## 3. Problem Statement

- Ngữ cảnh quản lý nhà phân tán giữa nhiều tác vụ và phiên làm việc; dễ mất lịch sử quyết định.
- Một chat xử lý mọi miền công việc dễ tạo context lớn và tốn token.
- Khó phân định quyền hạn và trách nhiệm của từng agent.
- Người dùng phải lặp lại các hướng dẫn và kinh nghiệm đã cung cấp.
- Thiếu kiểm soát thống nhất đối với việc tự động thực thi, quota và khả năng truy vết.

## 4. Target Users

- **Primary User:** Chủ nhà / Product Owner, người quản trị hệ thống.
- **Secondary Users (potential):** Thành viên gia đình hoặc người được ủy quyền theo phạm vi cho phép.

Chân dung người dùng, phân quyền và phạm vi MVP cụ thể chưa chốt ở Step 1.1.

## 5. Core Product Principles

1. **Human Authority:** Chủ nhà có quyền phê duyệt, từ chối, tạm dừng và thu hồi quyền tự động hóa.
2. **Multi-Agent Responsibility:** Director định tuyến và giám sát; Worker xử lý công việc trong miền được cấp.
3. **Context Isolation:** Worker giữ ngữ cảnh cục bộ, hạn chế truyền dữ liệu không liên quan.
4. **Persistent and Governed Memory:** Trí nhớ và phản hồi có khả năng kiểm tra, chỉnh sửa, xóa; việc học không được nâng quyền.
5. **Token-Aware Execution:** Giảm context dư thừa, theo dõi quota và có phương án xử lý khi gần giới hạn.
6. **Compliance First:** Chỉ dùng các chức năng, cơ chế truy cập và tự động hóa được chính sách nền tảng cho phép.
7. **Auditability and Least Privilege:** Hành động quan trọng phải truy vết được; quyền tối thiểu theo nhiệm vụ.

## 6. Conceptual Architecture (Non-implementation Commitment)

```text
Product Owner
     |
Main Chat — Director
     |
     +-- Worker: IoT (illustrative)
     +-- Worker: Maintenance (illustrative)
     +-- Worker: Security/Energy (illustrative)
     +-- Worker: Inventory (illustrative)
     |
Shared Capabilities (conceptual)
Memory / Feedback / Policies / Quota / Audit
     |
Authorized Home Infrastructure
```

**Director:** tiếp nhận yêu cầu, phân rã và định tuyến, theo dõi tiến độ, tổng hợp kết quả, điều tiết ngân sách token và kiểm soát chính sách.

**Workers:** xử lý miền nhiệm vụ độc lập, giữ context cục bộ, báo cáo kết quả và trạng thái theo cơ chế được cho phép.

**Shared Capabilities:** ghi nhớ dài hạn, học từ phản hồi, kiểm tra chính sách, giám sát quota, lưu vết quyết định.

Các Worker kể trên **chỉ minh họa**, không phải danh mục chính thức. Không giả định Antigravity hỗ trợ chia sẻ bộ nhớ hoặc điều khiển các phiên CLI tự động. Chi tiết đồng bộ liên phiên sẽ được quyết định trong bước thiết kế tiếp theo sau khi được phép.

## 7. Controlled Automation Policy — Level B

| Action class | Rule |
|---|---|
| Đọc trạng thái, thống kê | Được phép trong phạm vi quyền đã cấp |
| Phân tích, khuyến nghị, lập kế hoạch, nhắc lịch | Tự động |
| Tác vụ ít rủi ro | Tự động **chỉ** trong chính sách và quyền đã duyệt |
| Thao tác ảnh hưởng an toàn, điện, thiết bị có rủi ro | Cần phê duyệt rõ ràng |
| Mua sắm, thanh toán, mở khóa cửa, vô hiệu hóa bảo vệ | Cần phê duyệt rõ ràng |
| Tác vụ chưa phân loại được rủi ro | Mặc định không thực thi; yêu cầu xác nhận |
| Tự nâng quyền, tự sửa quy tắc phê duyệt | Không được phép |

Chủ nhà có thể dừng hoặc thu hồi quyền tự động hóa. Các thao tác có tác động đến mạng, NAS, Home Lab, thiết bị IoT, dữ liệu hoặc hệ thống bảo vệ phải chịu chính sách phê duyệt tương ứng; không mặc định cấp quyền quản trị hay quyền shell toàn hệ thống.

## 8. Self-Learning Vision

Tham khảo và đánh giá khả năng tái sử dụng các nguyên lý từ **Hermes Agent** (https://github.com/NousResearch/hermes-agent):

- Persistent memory.
- Session / experience retrieval.
- Feedback-driven improvement.
- Reusable skills / workflows.

Không mặc định nhúng toàn bộ mã nguồn Hermes Agent hoặc cho phép tự sửa đổi hành vi không kiểm soát. Kiến thức học được cần có thể kiểm tra, sửa hoặc xóa và không được làm thay đổi chính sách an toàn hay quyền hạn.

## 9. Hard Constraints

- **HC-01 — ToS:** Tuân thủ Antigravity Terms và tính năng được hỗ trợ; không giả định quyền tự động hóa nhiều phiên.
- **HC-02 — No Circumvention:** Không bypass quota, account rotation, proxy, reverse-engineering endpoint nội bộ hoặc lạm dụng dịch vụ.
- **HC-03 — Token Control:** Kiểm soát token, context window và xử lý khi thiếu quota; không hứa mức tiết kiệm định lượng khi chưa đo.
- **HC-04 — Privacy:** Bảo vệ thông tin gia đình, thông tin xác thực, dữ liệu camera/an ninh; không để lộ secrets trong prompt hoặc logs.
- **HC-05 — Approval:** Hành động rủi ro cao phải có phê duyệt trước khi thực thi.
- **HC-06 — No Privilege Escalation:** Agent không được tự nâng quyền hoặc thay đổi chính sách duyệt.
- **HC-07 — Audit & Recovery:** Có khả năng truy vết các hành động quan trọng và xác định trạng thái khi tác vụ lỗi.

## 10. Vision-Level Success Criteria

HomeAgentP đi đúng tầm nhìn nếu có thể:

1. Điều phối công việc qua các agent chuyên trách.
2. Duy trì và tái sử dụng thông tin phù hợp giữa các phiên.
3. Tự động xử lý các tác vụ ít rủi ro được cho phép.
4. Yêu cầu phê duyệt đối với thao tác nhạy cảm.
5. Theo dõi và hạn chế tiêu thụ tài nguyên AI.
6. Hoạt động qua các giao diện tích hợp được phép, không vi phạm chính sách dịch vụ.

Các KPI định lượng sẽ được xác định ở bước sau.

## 11. Out of Scope — Step 1.1

- Chốt danh mục Worker hoặc tính năng MVP.
- Thiết kế giao thức giao tiếp, đồng bộ, vòng đời phiên.
- Thiết kế cấu trúc memory, cơ sở dữ liệu, API, thuật toán quota.
- Triển khai mã nguồn, tự động hóa thật hoặc cấu hình thiết bị.
- Quyết định tích hợp Hermes Agent ở mức code.
- Thiết kế UI, wireframe hoặc các edge cases chi tiết.

## 12. Open Decisions and Validation Gates

- Persona và ưu tiên nghiệp vụ / MVP.
- Danh sách Worker và cơ chế tương tác Director–Worker.
- Cơ chế phê duyệt và chính sách phân loại rủi ro chi tiết.
- Kỹ thuật memory, đồng bộ và tối ưu token.
- Xác minh ToS, tài liệu CLI và quyền tích hợp chính thức trước triển khai.
- Kiểm định tính tương thích Hermes Agent với thiết kế.

Nếu một cơ chế tự động điều khiển CLI không được hỗ trợ hoặc không được phép, phải sử dụng quy trình chuyển giao có người tham gia hoặc phương thức chính thức được nhà cung cấp cho phép.

## 13. Decision Log

| Date | ID | Decision | Status |
|---|---|---|---|
| 2026-11-18 | DEC-001 | Phê duyệt Product Vision HomeAgentP Phase 1, Step 1.1 | Approved |
| 2026-11-18 | DEC-002 | Chọn Level B — Controlled Automation / Human-in-the-Loop | Approved |
| 2026-11-18 | DEC-003 | Giữ nguyên Step 1.1 sau khi lưu và commit; chưa bắt đầu Step 1.2 | Approved |

## 14. References

- Antigravity: https://antigravity.google/
- Antigravity Terms: https://antigravity.google/terms
- Hermes Agent: https://github.com/nousresearch/hermes-agent
- HomeAgentP Repository: https://github.com/Tb3c123/HomeAgentP

## 15. Approval Gate

**Phase 1 — Step 1.1: APPROVED.**

**Phase 1 — Step 1.2: NOT STARTED.** Chỉ bắt đầu khi Product Owner yêu cầu.
