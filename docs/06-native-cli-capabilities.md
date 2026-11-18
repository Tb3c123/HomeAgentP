# HomeAgentP — Native CLI Capability Validation

> Document ID: HAP-NATIVE-006  
> Version: v0.6.0  
> Status: **APPROVED**  
> Approved by: Product Owner  
> Date: 2026-11-18  
> Direction: Native Agents & Swarm First  
> Scope: Documentation-based capability review, **not** proof of local compatibility

## 1. Objective

Ưu tiên tận dụng Antigravity CLI (`agy`) chính thức, Native Agents, Subagents, Swarm, Rules và Skills trước khi viết công cụ hoặc cơ chế điều phối riêng. Tài liệu này chốt **định hướng đánh giá năng lực**; không chứng nhận tính năng đã chạy thành công trên Home NAS hay tài khoản hiện có.

## 2. Preferred Architecture

- **Runtime và giao diện chính:** Native Antigravity CLI; không xây Director CLI hoặc wrapper riêng.
- **Director:** Main Agent điều phối logic và tổng hợp kết quả.
- **Workers:** Ưu tiên custom Native Subagents cho công việc chuyên trách.
- **Swarm:** Chỉ dùng khi tác vụ có khả năng chia nhỏ và điều kiện tài khoản/quota cho phép; không mặc định chạy cho mọi yêu cầu.
- **Rules / Skills:** Tận dụng các cơ chế dự án được Antigravity hỗ trợ chính thức.
- **Knowledge:** Giữ tri thức và quyết định quan trọng có kiểm soát.
- **Hermes Agent:** Chỉ tham khảo cơ chế memory/learning; chưa tích hợp hoặc điều khiển Antigravity qua Hermes.

## 3. Capability Matrix

Các trạng thái bên dưới phản ánh **mô tả trong tài liệu được tham chiếu khi xây dựng proposal**. Cần kiểm tra lại tài liệu theo phiên bản thực tế, gói tài khoản và môi trường NAS trước khi sử dụng.

| Capability | Documentation Assessment | Home NAS / Account Test |
|---|---|---|
| Interactive `agy` | Documented | Pending |
| Custom Subagents | Documented | Pending |
| Agent management | Documented | Pending |
| `/swarm` | Documented; availability/preview restrictions may apply | Pending |
| Swarm coordination board | Documented | Pending |
| Workspace Rules | Documented | Pending |
| Skills | Documented | Pending |
| Learning commands/workflows | Documented; behavior/version to recheck | Pending |
| Task management | Documented; scope to recheck | Pending |
| Usage / context indicators | Documented; accuracy/availability to verify | Pending |
| Headless CLI | Documented; automation/ToS boundaries to verify | Pending |
| Hermes Agent integration | Not validated | Pending |
| Home NAS OS/CPU compatibility | Not validated | Pending |

**Interpretation:** “Documented” không có nghĩa hỗ trợ trên mọi tài khoản, mọi phiên bản hoặc quyền tự động điều khiển từ bên thứ ba.

## 4. Proposed Routing Policy

1. Director xử lý trực tiếp tác vụ đơn giản, nằm trong quyền được cấp.
2. Director sử dụng Native Subagent khi tác vụ có miền chuyên môn rõ ràng và cơ chế đó được hỗ trợ.
3. Cân nhắc Native Swarm chỉ khi thực sự cần phối hợp, được phép sử dụng, có đủ quota và đảm bảo quyền hạn.
4. Nếu tính năng unavailable hoặc không được phép, ưu tiên chuyển giao thủ công hoặc cách làm native hợp lệ, không dùng workaround né hạn chế.

Đây là định hướng logic; chưa phải routing implementation.

## 5. Quota and Token Policy

- Hạn chế số agent/worker được kích hoạt.
- Không dùng Swarm mặc định.
- Tránh chuyển toàn bộ lịch sử hoặc context không liên quan.
- Chỉ dùng usage/quota metrics từ nguồn chính thức và ghi rõ khi số liệu không có.
- Không xoay tài khoản, bypass quota hay truy cập endpoint nội bộ.
- Khi thiếu quota, dừng an toàn và ghi lại trạng thái công việc.

## 6. Security and Compliance

- Single Administrator, Controlled Automation Level B.
- Least privilege và yêu cầu người quản trị phê duyệt hành động nhạy cảm.
- Không tự nâng quyền, không sửa chính sách phê duyệt bằng self-learning.
- Chỉ sử dụng cơ chế tích hợp và tự động hóa được phép theo ToS hiện hành.
- Không cho rằng hỗ trợ `agy -p` đồng nghĩa việc dùng CLI làm backend cho client bên thứ ba luôn hợp lệ.
- Không lưu hoặc phát tán secrets chưa che giấu qua prompt, memory hoặc log.

## 7. Outstanding Local Validation

- Home NAS: hệ điều hành, phiên bản, kiến trúc CPU, RAM và phương thức truy cập shell.
- Runtime requirements và khả năng cài `agy` chính thức trên OS/CPU đó.
- Phiên bản `agy`, loại tài khoản và quyền tính năng thực tế.
- Subagents / Swarm có khả dụng và thực sự phù hợp không.
- Rules, Skills, memory và việc lưu trạng thái giữa các phiên.
- Dữ liệu quota/usage chính thức có thể đọc đến mức nào.
- Giới hạn quyền với thư mục, network và tài nguyên NAS.
- Ranh giới headless, automation và ToS áp dụng cho loại tài khoản.

**Chưa tiến hành cài đặt hoặc local validation.**

## 8. Preserved Decisions

- Single Administrator.
- Centralized Director.
- Orchestration-first MVP.
- Human-in-the-Loop Level B.
- Token efficiency và governed memory.
- **Custom UI/UX deferred:** chỉ xem xét sau khi HomeAgentP được thiết kế, cài đặt, cấu hình và xác nhận chạy thành công trên Home NAS.

## 9. Reference Sources (must revalidate before implementation)

- https://antigravity.google/docs/cli/reference/
- https://antigravity.google/docs/subagents
- https://antigravity.google/docs/swarm/
- https://antigravity.google/docs/skills
- https://antigravity.google/docs/slash-commands
- https://antigravity.google/terms

## 10. Approval and Next Gate

**Native CLI Capability Matrix v0.6.0: APPROVED** as a documentation-based planning baseline.

**Next step: Home NAS Environment Survey — NOT APPROVED.**

Không suy diễn kết quả tài liệu thành chứng nhận khả thi, không bắt đầu cài đặt hoặc UI/UX trước khi có quyết định mới.
