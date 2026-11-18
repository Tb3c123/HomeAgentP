# Điều phối Antigravity Home Orchestrator

Phase 1, bước 1.4a · Product Owner đã duyệt ngày 18/11/2026.

Product Owner đã chuyển trọng tâm MVP sang hỗ trợ vận hành NAS. Thiết kế nhóm Thiết bị và Lịch trình ở cuối tài liệu ghi lại phạm vi đã thảo luận trước đó. Các nhóm áp dụng cho [phạm vi hiện tại](01-overview.md) nằm ngay bên dưới.

## Các nhóm NAS đã duyệt

| Nhóm | Trách nhiệm |
| --- | --- |
| Hệ thống NAS | Theo dõi tài nguyên, trạng thái máy chủ và cảnh báo hệ thống. |
| Ứng dụng CasaOS | Kiểm tra trạng thái container, cấu hình dịch vụ và lỗi vận hành. |
| Lưu trữ & Sao lưu | Theo dõi dung lượng, bản sao lưu và khả năng khôi phục. |
| Media & Jellyfin | Theo dõi quá trình tải, nhập tệp, phụ đề, quét thư viện và phát trên Jellyfin. |
| Đội Dev | Thiết kế, xây dựng và duy trì phần mềm, tích hợp và công cụ phục vụ NAS. |

Chat Main giao cho Ứng dụng CasaOS khi container Jellyfin không khởi động. Nếu tệp đã tải xong nhưng phim chưa hiện trong thư viện, Chat Main giao cho Media & Jellyfin.

### Cơ cấu Đội Dev

Trưởng nhóm Dev nhận việc từ Chat Main. Các vai trò dưới đây bao phủ toàn bộ vòng đời phát triển. Cách giao việc bên trong Đội Dev và quyền của từng vai trò sẽ được thiết kế riêng.

| Mảng | Vai trò |
| --- | --- |
| Sản phẩm và tiến độ | Product Owner là người dùng dự án. Product Manager quản lý phạm vi và tiến độ. Business Analyst làm rõ yêu cầu và tiêu chí nghiệm thu. |
| Nghiên cứu và thiết kế | UX Researcher, UX Architect và UI/Visual Designer, bao gồm khả năng tiếp cận khi có giao diện. |
| Kiến trúc và phát triển | Tech Lead/Solution Architect, Frontend Engineer, Backend Engineer, Data/Database Engineer, Integration Engineer và AI/Agent Engineer. |
| Chất lượng và bảo mật | QA Engineer phụ trách kiểm thử thủ công và tự động. Security & Privacy Engineer rà soát quyền truy cập, bí mật và dữ liệu. |
| Phát hành và vận hành | DevOps/Platform Engineer, Release Manager và SRE phụ trách triển khai, giám sát, xử lý sự cố và rollback. |
| Tài liệu và hỗ trợ | Technical Writer duy trì tài liệu, runbook và changelog. Support/Maintainer tiếp nhận lỗi và theo dõi bảo trì sau phát hành. |

Product Owner chọn thiết kế chi tiết Media & Jellyfin trước.

## Quyết định của Chat Main

Chat Main chọn nhóm theo đầu ra người dùng yêu cầu và chịu trách nhiệm tổng hợp kết quả cuối cùng.

| Tình huống | Cách xử lý |
| --- | --- |
| Trả lời được từ thông tin có sẵn trong cuộc trò chuyện, ví dụ tóm tắt tiến độ vừa trao đổi | Trả lời trực tiếp. |
| Có một đầu ra rõ thuộc một nhóm | Gọi đúng một subagent rồi tổng hợp kết quả. |
| Có nhiều đầu ra và thứ tự xử lý rõ | Xử lý đầu ra đầu tiên. Nêu phần còn lại để Product Owner tiếp tục ở lượt sau. |
| Hai nhóm đều phù hợp và việc chọn nhóm làm thay đổi đầu ra | Hỏi một câu có hai lựa chọn trước khi giao việc. |
| Yêu cầu thay đổi dịch vụ hoặc dữ liệu NAS thật | Trả về phương án trên dữ liệu mẫu. Việc thực thi nằm ngoài MVP. |

Cùng một dịch vụ có thể liên quan đến nhiều nhóm. Chat Main chọn theo đầu ra người dùng yêu cầu và bằng chứng đang có.

## Nội dung giao việc và kết quả

- Chat Main gửi mục tiêu, dữ liệu mẫu liên quan, ràng buộc và đầu ra cần trả.
- Subagent trả trạng thái, kết quả, giả định và dữ liệu còn thiếu.
- Chat Main kiểm tra đầu ra, tổng hợp ngắn gọn và nêu phần chưa xác minh. Nếu thiếu dữ liệu ảnh hưởng đến kết quả, Chat Main trả lời có điều kiện hoặc hỏi Product Owner để xác minh trước khi đưa ra kết luận cụ thể.

## Giới hạn MVP và nghiệm thu

- Tối đa một lần gọi subagent mỗi lượt. Nếu lần gọi thất bại, Chat Main báo phần chưa hoàn tất và chờ lượt tiếp theo.
- Subagent phân tích dữ liệu mẫu được gửi trong yêu cầu và trả kết quả dạng văn bản. Quyền shell, Docker, web, MCP và ghi file được xét khi thiết kế từng vai trò.
- Trong bài nghiệm thu, ghi nhận `/usage` trước và sau bài thử. Giới hạn gọi subagent là quy tắc điều phối. Quota thực tế lấy từ CLI.

## Nhóm Thiết bị

Product Owner đã duyệt ở bước 1.4b.

Nhóm Thiết bị quản lý thông tin danh mục, phân tích trạng thái đã ghi nhận và đề xuất kiểm tra thủ công khi cần. Chat Main giao cho nhóm này khi yêu cầu cần thông tin về thiết bị. Nếu đầu ra là lịch bảo dưỡng, Chat Main giao cho nhóm Bảo trì.

- **Đầu vào:** dữ liệu mẫu Chat Main gửi trong nội dung giao việc. Mỗi bản ghi có thể gồm mã, tên, vị trí, trạng thái, thời điểm và nguồn ghi nhận.
- **Đầu ra:** trạng thái xử lý, kết quả dạng văn bản, giả định và dữ liệu còn thiếu. Với mỗi trạng thái thiết bị, giữ nguyên nguồn và thời điểm nếu có. Nếu hỏi về hiện tại, nêu rõ mức độ xác minh của bản ghi gần nhất.
- **Dữ liệu thiếu:** đánh dấu trường chưa rõ và đề xuất cách kiểm tra thủ công.
- **Thiết bị trùng tên:** phân biệt bằng mã hoặc vị trí. Nếu vẫn chưa xác định được, gửi các lựa chọn để Chat Main hỏi lại.
- **Bản ghi mâu thuẫn:** trình bày các bản ghi liên quan kèm thời điểm và nguồn, rồi nêu điều cần xác minh.
- **Quyền MVP:** chỉ phân tích dữ liệu được giao và trả văn bản. Không dùng shell, Docker, web, MCP hay quyền ghi file.

Bài thử dùng bản ghi camera cửa trước có trạng thái `offline` lúc `09:15`. Khi được hỏi camera hiện còn online không, kết quả cần giữ nguyên trạng thái và thời điểm ghi nhận, đồng thời nêu trạng thái hiện tại chưa được xác minh.

## Nhóm Lịch trình

Product Owner đã duyệt ở bước 1.4b.

Nhóm Lịch trình chọn thời điểm cho việc nhà, phát hiện trùng lịch và soạn nội dung nhắc. Chat Main giao cho nhóm này khi đầu ra là một khung giờ khả thi. Nhóm Bảo trì xác định hạng mục công việc và hạn bảo dưỡng.

- **Đầu vào:** tên việc, ngày hoặc khung giờ cho phép, thời lượng, múi giờ và các khoảng bận trong dữ liệu mẫu. Mặc định dùng giờ Việt Nam khi người dùng không chỉ định múi giờ khác.
- **Đầu ra:** trạng thái xử lý, khung giờ đề xuất, xung đột liên quan, giả định và dữ liệu còn thiếu. Ưu tiên khung giờ sớm nhất đáp ứng mọi ràng buộc và đưa thêm một lựa chọn nếu có.
- **Thiếu ngày hoặc thời lượng:** báo thông tin cần thiết để Chat Main hỏi lại.
- **Không đủ thời gian:** nêu khoảng bận gây xung đột và đề nghị Product Owner chọn ràng buộc có thể nới.
- **Quyền MVP:** phân tích dữ liệu mẫu và trả kết quả dạng văn bản. Việc tạo sự kiện hoặc gửi nhắc thực tế nằm ngoài quyền của nhóm.

Bài thử yêu cầu xếp một việc kéo dài 60 phút trong khung `09:30–12:00`, với lịch bận `10:00–11:00`. Kết quả cần chọn `11:00–12:00` và giải thích rằng khoảng `09:30–10:00` chỉ có 30 phút.
