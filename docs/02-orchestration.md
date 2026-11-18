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

## Media & Jellyfin — Yêu cầu và khảo sát trước thiết kế

Khảo sát ngày 18/11/2026 qua SSH chỉ đọc. Product Owner đã duyệt kiến trúc Sub-First, Fire-and-Forget và Periodic Health Check. Bố trí lưu trữ hiện có cần cải thiện trước khi triển khai. Quyền thao tác và cấu hình chi tiết chờ duyệt riêng. Bài nghiệm thu MVP tiếp tục dùng dữ liệu mẫu.

### Hạ tầng quan sát được

| Thành phần | Kết quả khảo sát |
| --- | --- |
| HDD 1 | `/mnt/disk1`, ext4, 9,1 TiB. Thư mục phim được Radarr gắn tại `/movies` và Jellyfin nhìn thấy tại `/media/disk1/Movies`. |
| HDD 2 | `/mnt/disk2`, ext4, 9,1 TiB. Thư mục `Downloads` dùng chung cho qBittorrent, Sonarr và Radarr tại `/downloads`. Thư mục `Media/TVShows` được Sonarr gắn tại `/tv` và Jellyfin nhìn thấy tại `/media/disk2/TVShows`. |
| qBittorrent | Nhãn image ghi phiên bản 5.3.0. Đường dẫn tải mặc định là `/downloads/`. Cấu hình có khai báo `/downloads/incomplete/` cho tệp tạm, trạng thái bật chưa xác minh. Trong `categories.json`, `radarr` có đường dẫn lưu riêng để trống và chưa thấy category `sonarr` theo đúng tên này. |
| Bazarr | Nhìn thấy cùng thư mục phim và tập với Radarr và Sonarr, lần lượt tại `/movies` và `/tv`. |
| Compose | qBittorrent, Prowlarr, Sonarr, Radarr, Bazarr và Seerr thuộc `media-stack`. Jellyfin thuộc project `jellyfin` và có cả hai cây `Media` được gắn. |
| Lịch nền | Dịch vụ `cron` đang hoạt động. Chưa xác minh job theo dõi torrent sẵn có hoặc kết nối WebUI API. |

Theo sơ đồ mount, luồng dự kiến của Radarr đi từ thư mục tải trên HDD 2 sang thư mục phim trên HDD 1, nên không thể dùng hardlink qua hai filesystem. Sonarr có đường dẫn nguồn và đích trên HDD 2, nhưng đây là hai bind mount riêng trong container. Linux cũng không hỗ trợ hardlink qua hai mount khác nhau. Khảo sát xác minh cấu hình và đường dẫn, còn hành vi nhập thực tế cần được kiểm chứng bằng tệp mẫu. [Linux link(2)](https://man7.org/linux/man-pages/man2/link.2.html)

### Kiến trúc nghiệp vụ đã duyệt

1. **Sub-First.** Tìm phụ đề tiếng Việt trước. Ghi lại định danh phim hoặc tập, edition và thông tin release có sẵn như nguồn video, nhóm encode hoặc tên bản phát hành. Chỉ gửi lệnh tải khi có bản phim khớp với phụ đề đã chọn. Nếu chỉ trùng các thuộc tính chung như `WEB-DL` hoặc cùng nhóm encode, đánh dấu chưa đủ bằng chứng và chờ xác minh. Đề xuất kiểm tra lại đồng bộ phụ đề sau khi có tệp. Bazarr hiện có vai trò quản lý phụ đề cho thư viện Sonarr/Radarr, còn nguồn tìm phụ đề trước khi có video cần xác minh riêng. [Bazarr và thư viện Sonarr/Radarr](https://wiki.bazarr.media/Getting-Started/How-Bazarr-Connects-to-Sonarr-and-Radarr/)
2. **Fire-and-Forget.** Sau khi qBittorrent hoặc ứng dụng *arr xác nhận nhận lệnh, ghi mã theo dõi và trạng thái bàn giao, trả kết quả cho Chat Main rồi kết thúc phiên. Sự cố mất phản hồi sau khi gửi cần đối chiếu mã theo dõi với hàng đợi trước khi gửi lại để tránh tải trùng. Phiên Antigravity không chờ tải hoàn tất.
3. **Periodic Health Check.** Một job cục bộ chạy ngắn theo lịch hoặc trigger nhẹ, kiểm tra tiến độ qua nhiều mẫu, tốc độ, trạng thái tracker và seed/peer. Job chỉ cần qBittorrent WebUI API cho việc giám sát thường kỳ. Kết quả ghi vào báo cáo cục bộ để Chat Main đọc khi cần. Đề xuất bắt đầu ở chế độ chỉ báo cáo, sau đó duyệt riêng ngưỡng, thời gian chờ, số lần thử và quyền thực hiện re-announce hoặc đổi sang bản dự phòng đã qua Sub-First. [qBittorrent WebUI API](https://github.com/qbittorrent/qBittorrent/wiki/WebUI-API-(qBittorrent-5.0))

### Thử nghiệm bố trí cùng HDD cho phim

Product Owner đã duyệt giữ vị trí thư viện và thử vùng tải mới theo từng HDD. Phương án đích là vùng tải phim dưới `/mnt/disk1/Media/.downloads/radarr` và vùng tải tập dưới `/mnt/disk2/Media/.downloads/sonarr`. Mỗi ứng dụng nhập nhìn thấy vùng tải và thư viện qua cùng một mount cha trên HDD tương ứng. qBittorrent và ứng dụng nhập dùng cùng đường dẫn bên trong container cho vùng tải.

Bài thử dùng thư mục tạm trên HDD 1, mạng Docker riêng và đúng image của ba dịch vụ hiện có. qBittorrent 5.3.0 nhận video tự tạo từ một peer nội bộ, báo tải hoàn tất và lưu đúng vùng thử trên HDD 1. Một lượt thử riêng xác nhận category `radarr-pilot` tự chọn đúng vùng tải khi bật Automatic Torrent Management và không truyền đường dẫn lưu riêng.

Radarr 6.4.4.10685 nhập chính tệp đã tải bằng lệnh quét nhập ở chế độ `Copy`, với tùy chọn dùng hardlink. Tệp tải và tệp thư viện có cùng device `2049`, inode `3918317` và số link `2`. Jellyfin 12.4.0 quét thấy phim trong thư viện thử. Dữ liệu trả từ luồng phát HTTP trùng tệp đã tải và FFmpeg giải mã được cả hình lẫn tiếng. Đã dọn container, mạng và thư mục thử. Các dịch vụ đang dùng tiếp tục chạy với thời điểm khởi động trước bài thử.

Kết quả xác nhận bố trí cùng mount hỗ trợ hardlink và Jellyfin đọc được tệp nhập. Bài thử chủ động gọi Radarr để nhập. Tự nhập từ hàng đợi qBittorrent, chính sách thư mục tải dở của cấu hình đang dùng và luồng Sonarr chờ kiểm chứng riêng. Bài thử không bao gồm tìm Vietsub hoặc Health Check.

Phương án ưu tiên là áp dụng trước cho các lượt tải phim mới, giữ đường dẫn cũ cho torrent đang tải hoặc seed. Cần xác nhận tệp đang tải dở cũng nằm đúng HDD. Bố trí hiện tại đơn giản hơn nhưng nhập qua ổ cần sao chép và có thể giữ hai bản trong lúc seed. Dồn toàn bộ tải và thư viện vào một HDD đơn giản hóa mount nhưng cần chuyển thư viện và tập trung dung lượng, I/O vào một ổ. Hai HDD hiện đều còn nhiều chỗ trống, nên bố trí tách theo loại nội dung cân bằng tốt hơn giữa khả năng hardlink và công sức chuyển đổi.

### Tải phim mới trên NAS đang dùng

Đã áp dụng bố trí HDD 1 cho Radarr. Category `radarr` trỏ đến `/data/disk1/.downloads/radarr`, tương ứng `/mnt/disk1/Media/.downloads/radarr` trên NAS. qBittorrent đọc đường dẫn category cả khi Automatic Torrent Management tắt. Tùy chọn thư mục tải dở riêng đang tắt, nên luồng này dùng vùng tải HDD 1 từ đầu. Các category TV và mount `/downloads` trên HDD 2 vẫn giữ cấu hình hiện có.

Radarr dùng một mount cha `/data/disk1` để truy cập vùng tải và `/data/disk1/Movies`. Đã cập nhật đường dẫn logic của 52 mục phim, xác minh vẫn có 50 mục có tệp và giữ nguyên vị trí tệp trên NAS. Seerr dùng root mới. Bazarr có thêm alias cho đường dẫn mới của Radarr. Jellyfin tiếp tục đọc thư viện phim ở đường dẫn hiện có. Bản sao lưu Compose, cơ sở dữ liệu Radarr và các giá trị cấu hình trước khi đổi nằm trong thư mục sao lưu được bảo vệ trên NAS.

Bài kiểm tra trên dịch vụ đang dùng đưa một video tự tạo từ peer nội bộ vào Radarr. Radarr giao đúng category cho qBittorrent, qBittorrent lưu đúng HDD 1, rồi Radarr tự nhập từ hàng đợi. Tệp nguồn và tệp thư viện của bài thử có cùng device `2049`, inode `3918269` và số link `2`. Đã xóa riêng mục, torrent và dữ liệu mẫu sau khi kiểm tra.

#### Tải lại và giữ đúng đường dẫn

- Định danh bản tải theo infohash, category và `content_path` mà qBittorrent báo. Khi còn bản ghi, đối chiếu infohash trước khi gửi lại. Bài thử gửi trùng giữ đúng một bản ghi và cùng `content_path`.
- Khi đã gỡ bản ghi nhưng giữ tệp nguồn, thêm lại cùng torrent vào category `radarr` với bố trí tệp như cũ để qBittorrent kiểm tra lại dữ liệu. Bài thử xác nhận qBittorrent dùng lại đúng đường dẫn và inode, với dữ liệu nguồn còn nguyên.
- Nếu nguồn bị mất hoặc hỏng, hoặc bản thay thế có infohash khác, cần đối chiếu tệp thư viện trước khi xử lý. Hai tên file hardlink dùng chung inode, nên ghi đè dữ liệu tại nguồn có thể đổi dữ liệu Jellyfin đang đọc. Trường hợp này chờ quy tắc phục hồi riêng của Media & Jellyfin.

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
