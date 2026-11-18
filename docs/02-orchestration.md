# Điều phối Antigravity Home Orchestrator

Phase 1, bước 1.4a · Product Owner đã duyệt ngày 18/11/2026.

## Quyết định của Chat Main

Chat Main chọn nhóm theo đầu ra người dùng yêu cầu và chịu trách nhiệm tổng hợp kết quả cuối cùng.

| Tình huống | Cách xử lý |
| --- | --- |
| Trả lời được từ thông tin có sẵn trong cuộc trò chuyện, ví dụ tóm tắt tiến độ vừa trao đổi | Trả lời trực tiếp. |
| Có một đầu ra rõ thuộc một nhóm | Gọi đúng một subagent rồi tổng hợp kết quả. |
| Có nhiều đầu ra và thứ tự xử lý rõ | Xử lý đầu ra đầu tiên. Nêu phần còn lại để Product Owner tiếp tục ở lượt sau. |
| Hai nhóm đều phù hợp và việc chọn nhóm làm thay đổi đầu ra | Hỏi một câu có hai lựa chọn trước khi giao việc. |
| Yêu cầu tác động lên thiết bị, lịch hoặc chi tiêu thật | Trả về phương án trên dữ liệu mẫu. Việc thực thi nằm ngoài MVP. |

Cùng một thiết bị có thể liên quan đến nhiều nhóm. Yêu cầu lập lịch bảo dưỡng máy lọc nước thuộc nhóm Bảo trì. Yêu cầu xếp việc thay lõi vào cuối tuần để tránh trùng lịch thuộc nhóm Lịch trình.

## Nội dung giao việc và kết quả

- Chat Main gửi mục tiêu, dữ liệu mẫu liên quan, ràng buộc và đầu ra cần trả.
- Subagent trả trạng thái, kết quả, giả định và dữ liệu còn thiếu.
- Chat Main kiểm tra đầu ra, tổng hợp ngắn gọn và nêu phần chưa xác minh. Nếu thiếu dữ liệu ảnh hưởng đến kết quả, Chat Main trả lời có điều kiện hoặc hỏi Product Owner để xác minh trước khi đưa ra kết luận cụ thể.

## Giới hạn MVP và nghiệm thu

- Tối đa một lần gọi subagent mỗi lượt. Nếu lần gọi thất bại, Chat Main báo phần chưa hoàn tất và chờ lượt tiếp theo.
- Subagent phân tích dữ liệu mẫu được gửi trong yêu cầu và trả kết quả dạng văn bản. Quyền shell, Docker, web, MCP và ghi file được xét khi thiết kế từng vai trò.
- Trong bài nghiệm thu, ghi nhận `/usage` trước và sau bài thử. Giới hạn gọi subagent là quy tắc điều phối. Quota thực tế lấy từ CLI.
