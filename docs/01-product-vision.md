# HomeAgentP — Product Vision

> Version: v0.1.0  
> Phase: 1 — Step 1.1 (Product Vision)  
> Status: APPROVED  
> Approved by: Product Owner  
> Approval date: 2026-11-18  
> Repository: https://github.com/Tb3c123/HomeAgentP

## 1. Product statement

**HomeAgentP — A Unified Home Intelligence & Orchestration Workspace**

HomeAgentP là hệ thống không gian làm việc hỗ trợ quản trị Home Lab, Home Network, NAS, Smart Home và dịch vụ tại gia, được định hướng vận hành trên nền tảng Google Antigravity CLI (`agy`). Sản phẩm tổ chức công việc bằng một Main Chat đóng vai trò điều phối logic và nhiều Sub-chats chuyên trách; kết quả quan trọng được quản lý trong bộ tài liệu dùng chung có phiên bản.

Hệ thống ưu tiên **AI-assisted, human-in-control**: AI đề xuất, phân tích, phân rã và tổng hợp; Product Owner phê duyệt các hành động nhạy cảm hoặc ảnh hưởng đến hạ tầng thật.

## 2. Problem statement

Quản trị hệ sinh thái Home có nhiều miền nghiệp vụ và thông tin phân tán: mạng, NAS, máy chủ, IoT, bảo trì, trạng thái dịch vụ và lịch sử quyết định. Việc sử dụng nhiều phiên AI riêng lẻ dễ mất ngữ cảnh, khó truy vết trách nhiệm và có nguy cơ phát sinh hành động thiếu kiểm soát.

HomeAgentP nhằm tạo một quy trình điều phối thống nhất, dễ kiểm toán và an toàn, thay vì cấp quyền tự trị không giới hạn cho AI.

## 3. Target user

- **Primary user:** Product Owner, đồng thời là người quản trị hệ thống Home/Home Lab.
- Mở rộng cho những người vận hành được ủy quyền chỉ khi có cơ chế phân quyền phù hợp; không cam kết tính năng đa người dùng trong MVP.

## 4. Product goals

1. Tập trung tiếp nhận và theo dõi nhiệm vụ qua Main Chat.
2. Phân chia công việc theo phạm vi nghiệp vụ tại các Sub-chats.
3. Đồng bộ kết quả quan trọng bằng tài liệu/trạng thái chuẩn có phiên bản.
4. Đảm bảo các thao tác rủi ro phải được người dùng phê duyệt.
5. Đặt ToS, rate limit, bảo mật tài khoản và truy vết làm ràng buộc thiết kế.
6. Cho phép mở rộng sau khi xác minh khả năng và điều khoản của CLI.

## 5. Logical architecture (non-implementation commitment)

```text
Product Owner
     |
Main Chat — Orchestrator
     |
     +-- Sub-chat A (specialized domain)
     +-- Sub-chat B (specialized domain)
     +-- Sub-chat N (specialized domain)
     |
Shared Project Knowledge
(Markdown docs, task records, decisions, state snapshots)
     |
Controlled access to Home Infrastructure
```

**Main Chat**: tiếp nhận yêu cầu, phân rã tác vụ, theo dõi, kiểm tra và tổng hợp đầu ra.

**Sub-chats**: mỗi phiên chịu trách nhiệm một lĩnh vực hoặc tác vụ trong phạm vi đã giao. Chi tiết các nhóm chưa được quyết định tại bước 1.1.

**Shared Project Knowledge**: nguồn chuẩn cho trạng thái nhiệm vụ, quyết định và thông tin đã xác minh. Không giả định các session tự chia sẻ bộ nhớ hoặc Main Chat có thể gọi các session khác bằng cơ chế chưa được xác nhận.

## 6. Communication and data principles

- Mọi nhiệm vụ có mã định danh, mục tiêu, đầu vào, trạng thái, đầu ra, thời điểm cập nhật và chủ thể phê duyệt khi cần.
- Giao tiếp liên phiên được xem là **logic workflow**; phương thức trao đổi thực tế có thể là thủ công hoặc thông qua cơ chế chính thức được hỗ trợ.
- Thay đổi quan trọng được lưu vào Shared Project Knowledge, không chỉ nằm trong lịch sử chat.
- Main Chat phải kiểm tra nguồn, thời điểm cập nhật và mâu thuẫn dữ liệu trước khi tổng hợp.
- Khi đồng bộ thất bại hoặc dữ liệu cũ, không được giả định tác vụ hoàn tất.
- Không tự động hóa chéo session hoặc phát lệnh CLI hàng loạt khi chưa xác minh tính năng và quyền sử dụng.

## 7. Non-negotiable principles

| ID | Principle | Rule |
|---|---|---|
| P-01 | Compliance First | Chỉ sử dụng giao diện, luồng xác thực và các tính năng được nhà cung cấp cho phép theo điều khoản áp dụng. |
| P-02 | Human-in-Control | Hành động nhạy cảm cần phê duyệt rõ ràng trước khi thực thi. |
| P-03 | Single Source of Truth | Sự thật vận hành và quyết định quan trọng có nguồn chuẩn, có phiên bản. |
| P-04 | Least Privilege | Cấp quyền tối thiểu theo phiên, nhiệm vụ, tài nguyên. |
| P-05 | Observable & Recoverable | Có log, trạng thái, xử lý lỗi, điểm dừng và phương án phục hồi. |
| P-06 | No Quota Circumvention | Không né quota bằng xoay tài khoản, proxy, endpoint không chính thức hay thủ thuật khác. |

## 8. Security and approval boundaries

Các thao tác thay đổi cấu hình hệ thống, mạng, NAS, dữ liệu, dịch vụ đang chạy, thiết bị IoT hoặc thông tin xác thực phải có chính sách xác nhận và phạm vi quyền phù hợp. Chưa mặc định cấp quyền shell, quyền administrator hay quyền truy cập toàn mạng cho AI.

Tài liệu và lời nhắc gửi lên nền tảng AI phải được rà soát để tránh lộ mật khẩu, token, private key, thông tin định danh hoặc dữ liệu nhạy cảm của Home Lab. Log không được chứa bí mật chưa được che giấu.

## 9. MVP boundary — directional, not final feature selection

**Trong định hướng MVP:** workspace dự án, khung Main/Sub-chat, giao thức giao việc và nhận kết quả, hồ sơ nhiệm vụ, tài liệu dùng chung, quy trình phê duyệt, và chính sách bảo mật/tuân thủ.

**Cần xác minh trước khi đưa vào phạm vi:** session synchronization tự động, headless invocation, MCP integration, scheduling, điều khiển tài nguyên thật, và giao tiếp agent-to-agent.

**Không thuộc MVP:** AI toàn quyền tự trị, bypass quota, account rotation, reverse engineering API nội bộ, hoặc điều khiển hạ tầng không có giới hạn và phê duyệt.

Danh mục MVP chi tiết sẽ được quyết định ở bước sau; tài liệu này không phê duyệt sẵn từng tính năng.

## 10. ToS and capability validation

Thiết kế không tự khẳng định rằng mọi kịch bản đa phiên hoặc tự động hóa qua `agy` đều được phép. Trước triển khai cần kiểm tra tài liệu **chính thức, đang có hiệu lực** của nhà cung cấp đối với đúng loại tài khoản, gói sử dụng, tính năng CLI, cơ chế session, API, rate limits và third-party automation.

Quy tắc mặc định khi chưa có bằng chứng: **không triển khai cơ chế tự động hóa có nguy cơ vi phạm**; sử dụng bước chuyển giao thủ công hoặc chức năng được hỗ trợ rõ ràng.

Tham chiếu ban đầu (cần đối chiếu lại trước triển khai):
- https://antigravity.google/terms
- https://antigravity.google/docs/cli/reference/

## 11. Success criteria for Product Vision

- Mục tiêu, người dùng chính và giá trị sản phẩm được mô tả rõ.
- Phân biệt Main Chat, Sub-chats và kho dữ liệu chuẩn.
- Chốt mô hình AI-assisted với quyền phê duyệt của Product Owner.
- ToS, least privilege, bảo mật và khả năng truy vết là ràng buộc cấp sản phẩm.
- Phân biệt giữa kiến trúc mong muốn và khả năng CLI thực tế đã kiểm chứng.
- Không tự động chuyển sang bước 1.2 khi chưa có chỉ đạo.

## 12. Decision log

| Date | ID | Decision | Status |
|---|---|---|---|
| 2026-11-18 | DEC-001 | Phê duyệt Product Vision HomeAgentP ở Phase 1, Step 1.1 | Approved |
| 2026-11-18 | DEC-002 | Chọn mô hình AI-assisted; người dùng phê duyệt hành động nhạy cảm | Approved |
| 2026-11-18 | DEC-003 | Giữ nguyên Phase 1, Step 1.1 sau khi lưu tài liệu; chưa sang Step 1.2 | Approved |

## 13. Current gate

**Phase 1 — Step 1.1: APPROVED and documented.**

**Next step: NOT STARTED.** Không triển khai Phase 1 — Step 1.2 cho tới khi Product Owner yêu cầu.
