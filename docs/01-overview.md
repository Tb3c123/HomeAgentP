# Antigravity Home Orchestrator

Phase 1, bước 1.1 · Phạm vi MVP đã duyệt ngày 18/11/2026.

## Tầm nhìn và người dùng

Antigravity Home Orchestrator là hệ thống điều phối AI hỗ trợ quản lý việc nhà từ NAS thông qua Antigravity CLI. Người dùng đầu tiên là Product Owner, trực tiếp giao việc, kiểm tra kết quả và theo dõi quota. Về lâu dài, hệ thống sẽ tái sử dụng các bài học đã được duyệt để giảm công sức xử lý các tác vụ lặp lại.

## MVP Milestone 1

Thiết lập Antigravity CLI chính thức, xác thực bằng phương thức được Google hỗ trợ và vận hành trong một workspace dành riêng cho dự án. Workspace có một phiên Chat Main và bốn vai trò subagent được gọi khi cần. Đây là mô hình Project cho MVP. Khả năng duy trì lịch sử riêng cho từng nhóm qua nhiều phiên sẽ được kiểm chứng sau.

| Luồng | Trách nhiệm ban đầu |
| --- | --- |
| Chat Main — Director | Tiếp nhận yêu cầu, chọn nhóm, giới hạn việc ủy quyền và tổng hợp kết quả. |
| Thiết bị | Lập danh mục và đề xuất cách kiểm tra trạng thái thiết bị. |
| Lịch trình | Sắp xếp việc nhà, nhận diện xung đột và đề xuất lịch nhắc. |
| Tài chính & Vật tư | Tổng hợp chi phí, tồn kho và nhu cầu mua sắm. |
| Bảo trì | Lập lịch bảo dưỡng và soạn checklist xử lý sự cố. |

Bài thử dùng dữ liệu mẫu. UX/UI, kết nối thiết bị thật, thiết kế chi tiết từng nhóm và tích hợp cơ chế tự học nằm ngoài phạm vi Milestone 1.

## Lộ trình Phase 1

| Bước | Công việc | Kết quả cần đạt |
| --- | --- | --- |
| 1.1 — Chốt phạm vi | Duyệt cấu trúc workspace, vai trò và tiêu chí nghiệm thu. | Product Owner đã duyệt. |
| 1.2 — Kiểm tra NAS và điều kiện sử dụng | Kiểm tra chỉ đọc host và container CasaOS. Xác định gói tài khoản và điều khoản áp dụng. | Đã xác minh `agy` 1.5.11 trong container hiện có. Product Owner xác nhận dùng Google AI Pro và duyệt tái sử dụng bản cài. |
| 1.3 — Xác minh và cấu hình bản cài CasaOS hiện có | Dùng `agy` có sẵn qua SSH, thiết lập workspace riêng và cấu hình theo phiên. Xác nhận đăng nhập Google và kiểm tra `/usage`. | Đã mở CLI trong workspace dự án, xác minh Google AI Pro và xem được quota. Product Owner đã duyệt kết quả. |
| 1.4 — Thiết kế điều phối, đăng ký subagent và nghiệm thu | Trao đổi và duyệt thiết kế điều phối trước khi đăng ký bốn vai trò trong `.agents/agents/`. Sau đó chạy một yêu cầu mẫu qua Chat Main. | Main chọn đúng một subagent, tổng hợp kết quả, Product Owner theo dõi được qua `/agents` và mở lại Main qua `/resume`. Ghi nhận `/usage` trước và sau bài thử. |

## Bản cài CasaOS

Antigravity CLI 1.5.11 đã có trong container `antigravity-cli`. Workspace `/mnt/disk1/Workspace/HomeAgentP` và file `.homeagentp-cli-settings.json` đã được tạo. File cấu hình theo phiên đặt `agentMode` thành chuỗi rỗng để chọn chế độ mặc định có duyệt sửa file, bật `toolPermission: strict`, tắt truy cập ngoài workspace ở cấp CLI và đặt `useG1Credits: false` để tắt tự động dùng AI credits vượt quota. Tạo Linux user namespace bị từ chối trong container. Giới hạn của CLI không thay thế sandbox hệ điều hành.

Mở trực tiếp `agy` từ terminal SSH trên NAS:

```bash
docker exec -it -e SSH_CONNECTION -e SSH_TTY \
  -w /mnt/disk1/Workspace/HomeAgentP antigravity-cli \
  /usr/local/bin/agy --settings .homeagentp-cli-settings.json
```

Phiên SSH đã xác minh tài khoản đăng nhập có gói Google AI Pro và `/usage` hiển thị quota theo nhóm model. Nếu CLI yêu cầu đăng nhập lại, dùng luồng OAuth qua SSH chính thức của Google. Bài kiểm tra chỉ mở CLI và xem quota.

## Điều khoản và quota

- Chạy trực tiếp trong `agy` chính thức theo điều khoản áp dụng cho tài khoản. Giữ thông tin xác thực trong luồng đăng nhập chính thức. Tránh bọc `agy` trong ứng dụng bên thứ ba và tự động xoay tài khoản.
- Chat Main gọi tối đa một subagent mỗi lượt theo mặc định. Product Owner theo dõi chỉ số CLI hiển thị qua `/usage`, dừng khi chạm giới hạn và giữ tùy chọn dùng AI credits vượt quota ở trạng thái tắt nếu có. Khả năng đo token chính xác theo từng subagent chưa được xác minh.
- Theo [Điều khoản Antigravity](https://antigravity.google/terms), cần giám sát hành động và quyền truy cập của agent. Theo [Plans](https://antigravity.google/docs/plans), quota Google AI Pro làm mới theo chu kỳ năm giờ cho đến khi chạm giới hạn tuần. Xem thêm [FAQ](https://antigravity.google/docs/faq) và [CLI Settings](https://antigravity.google/docs/settings?tab=cli).

## Hướng tự học sau MVP

Tham khảo bộ nhớ ngắn qua nhiều phiên và cách tải skills khi cần của Hermes Agent. Quy trình đề xuất là agent ghi lại bài học, Product Owner duyệt, rồi cập nhật memory hoặc skill của dự án. Dùng cơ chế Antigravity được hỗ trợ để triển khai quy trình này. [Hermes Persistent Memory](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory) · [Hermes Skills](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills)

## Tài liệu triển khai

- [Quickstart Antigravity CLI](https://antigravity.google/docs/getting-started?tab=cli)
- [Xác thực qua SSH](https://antigravity.google/docs/install?tab=cli#remote-ssh-oauth-flow)
- [Custom subagents](https://antigravity.google/docs/subagents?tab=cli)
- [CLI Features](https://antigravity.google/docs/cli-features)
- [Terminal sandbox](https://antigravity.google/docs/sandbox?tab=cli)
