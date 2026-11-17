# Hướng dẫn giao HomeAgentP cho Google Antigravity

> Mục đích: để chủ dự án dùng **Google AI Pro trong Antigravity chính thức** phát triển HomeAgentP theo GitHub, không để Dashboard tự gọi `agy` hay dùng OAuth consumer làm API. Không có quyền thay đổi NAS chỉ vì tài liệu này tồn tại.

## 1. Chọn đúng môi trường

**Khuyến nghị: Remote Agents trên Google** để viết code/test bằng repository GitHub mà không chạm trực tiếp NAS. Mở https://antigravity.google.com, đăng nhập Google AI Pro, tạo Remote Project và gắn GitHub repository `Tb3c123/HomeAgentP` (xem https://antigravity.google/docs/remote-agents/). Agent trong môi trường remote **không** tự có quyền truy cập file/thiết bị trên NAS.

**Phương án khác: Remote Control** để điều khiển một phiên Antigravity CLI/app chính thức trên máy bạn, theo https://antigravity.google/docs/remote-control/. Đây là tương tác chính thức do người dùng khởi động/chấp thuận, KHÔNG phải tích hợp API qua HomeAgentP. Trước khi dùng trên NAS, phải khóa quyền của container hiện hữu. Không dùng terminal root có Docker Socket RW và cổng ttyd 7681 đang lắng nghe rộng để chạy tác vụ AI chưa tin cậy.

## 2. Quy trình chuẩn Git

1. Đọc README này, `AGENTS.md`, `docs/00-project-scope.md` và toàn bộ tài liệu cho giai đoạn hiện tại.
2. Chỉ chọn **một** Phase/Task mỗi lần; nêu kế hoạch, file sẽ tác động và tiêu chí nghiệm thu trước khi sửa.
3. Làm việc trên branch `feature/phase-XX-short-name`; không push thẳng `main`.
4. Chỉ sửa các file thuộc scope; tạo code + unit tests + config examples + docs vận hành; không thêm secrets, host-specific mount paths hoặc OAuth credentials.
5. Chạy test trong môi trường cô lập khi được cấp phép; nếu không chạy được, ghi rõ `NOT_TESTED`; không dựng kết quả giả.
6. Commit và mở Pull Request với thay đổi, kết quả kiểm thử thật, rủi ro, giới hạn và rollback.
7. Chủ dự án review rồi mới merge; **merge không đồng nghĩa cho phép deploy**.
8. Chỉ triển khai NAS khi chủ dự án phê duyệt đúng target, files, lệnh, thời gian và rollback.

## 3. Kế hoạch thực hiện

- **P0 / Repo & spec**: README, AGENTS, từng phase, Git workflow, security baseline.
- **P1 / Foundation**: 2 service `homeagentp-web` + `homeagentp-core`, authentication, SQLite migrations, Dashboard shell, health, task/script metadata. Không gắn host filesystem tùy tiện.
- **P2 / NAS Guardian**: CPU/RAM/disk/mount/containers read-only; không dùng raw Docker socket trong Web/Core; nếu không có adapter an toàn, hiển thị `unavailable`.
- **P3 / Media & Downloads**: Jellyfin, Radarr, Sonarr, Bazarr, Prowlarr, Seerr, qBittorrent qua API read-only/scoped; alerts, không tự xóa hoặc tải phim.
- **P4 / Tasks, Scripts, Artifacts & Git**: Task Brief templates, code/script viewer, versioned artifacts, Git links; **không tự chạy Antigravity CLI**.
- **P5 / Home Assistant & Notifications**: read-only Home Assistant integration, Telegram alerts với token riêng; policy/approval cho actions.
- **P6 / Release & Recovery**: Compose được kiểm thử, backup SQLite nhất quán, isolated restore, resource caps, threat review và triển khai có rollback.

Mỗi Phase phải có acceptance checklist cụ thể tại `docs/plans/` trước khi được implement. Không coi P0-P6 đã đạt khi chưa có code và evidence.

## 4. Prompt chuẩn mở đầu cho Antigravity

Sao chép nguyên prompt này vào phiên **chính thức** khi repository đã được kết nối:

```text
Bạn là kỹ sư triển khai dự án HomeAgentP B+.
Repository: https://github.com/Tb3c123/HomeAgentP

Nhiệm vụ đầu tiên: CHỈ đọc README.md, AGENTS.md và các tài liệu docs/ hiện có; nếu file nào chưa tồn tại, ghi nhận thiếu, không tự bịa ra quyết định kiến trúc.

HomeAgentP không phải dự án developer-only: phải bảo toàn NAS Guardian, media/downloads, Home Assistant, monitoring, Telegram, scripts/tasks, knowledge, security/recovery và developer workspace.

Kiến trúc B+: Antigravity chính thức là công cụ AI do người dùng trực tiếp sử dụng, còn HomeAgentP là Web + Core điều hành NAS. HomeAgentP không gọi, bọc, proxy hoặc xoay vòng đăng nhập của Antigravity CLI consumer.

Trước khi viết code, hãy:
1. Tóm tắt scope và current repo state.
2. Chọn Phase đầu tiên còn thiếu và chia thành những task nhỏ có thể review.
3. Đề xuất tech stack tối giản, sơ đồ folder, API surface và database schema cơ bản.
4. Liệt kê rủi ro bảo mật, tiêu chí acceptance và test strategy.
5. Nêu rõ mọi giả định chưa được xác minh.

Không thực hiện bất kỳ thao tác nào lên NAS, không deploy Docker, không đọc credentials, không mở port, không dùng sudo/root/docker.sock, không tự cài package vào host. Chỉ làm kế hoạch trong repository; chờ tôi chấp thuận trước khi code.
```

## 5. Prompt cho mỗi task sau khi duyệt kế hoạch

```text
Thực hiện HomeAgentP [PHASE/TASK ID] theo README.md, AGENTS.md và docs/plans tương ứng.
Scope được phép: [files/features].
Scope không được phép: [excluded].
Chỉ sửa code trong workspace/repository, không can thiệp NAS.
Yêu cầu: code tối giản, type-check/lint/test phù hợp, sample config không chứa secrets, tài liệu vận hành, security review.
Không tự tạo fake test results. Nếu cần quyền hoặc cấu hình ngoài scope, dừng và ghi BLOCKED.
Tạo branch riêng và Pull Request với summary, evidence, risks và rollback. Không merge hay deploy thay tôi.
```

## 6. Prompt cho deployment (chỉ sau khi có quyền riêng)

```text
Chỉ lập Deployment Plan cho HomeAgentP phiên bản [tag/commit] đến NAS Debian/CasaOS.
Trước tiên kiểm tra read-only thông số được cấp; không có quyền chạy lệnh ghi.
Trình bày chính xác từng command dự định chạy, ports, volumes, image digests, secrets handling, resource caps, healthchecks, backup, rollback, expected downtime.
Chờ chủ dự án phê duyệt DEPLOYMENT ACTIONS. Không thực thi lệnh hay tạo container khi chưa được cấp quyền.
```

## 7. Bảo mật và điều khoản bắt buộc

- Không dùng Antigravity consumer token làm API backend của HomeAgentP.
- Không cấp quyền root hoặc Docker Socket cho Web/Core.
- Không mount toàn bộ `/mnt/disk1`, `/mnt/disk2`, `/`, `/root/.gemini`.
- Không khai báo secrets thật trong repo, commit log, screenshots hoặc PR.
- Không mở port 8310 công khai trước khi có auth và network access rules.
- Dữ liệu SMART và container stats cần adapter kỹ thuật có đặc quyền tối thiểu, tránh trực tiếp Docker admin socket.
- Tất cả kết quả kiểm thử/benchmark/backup/restore chưa chạy phải ghi `NOT_TESTED`.
- Một tác vụ được tạo trong Dashboard KHÔNG được tự chạy `agy` từ backend.

## 8. Điều kiện nghiệm thu chung

Mỗi PR phải có: phạm vi; file thay đổi; cách chạy local; lint/test evidence; security consideration; config sample; rollback; limitations. Nếu không đáp ứng, yêu cầu sửa trước khi merge.

**Chú ý:** Đây là quy trình chuyển giao, không phải giấy phép triển khai trên NAS.
