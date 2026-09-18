# Roadmap chốt MVP Runner và crawler

Cập nhật 2026-09-17. Đây là bảng theo dõi phạm vi, không phải xác nhận production.
Phase triển khai 0–27 là các đợt công việc nhỏ; không tương đương số giai đoạn
MVP trong mục 21 của thiết kế V2.

## Đối chiếu MVP

| MVP trong V2 | Bằng chứng hiện tại | Điều kiện còn thiếu |
| --- | --- | --- |
| 1: UI, executor local, summary, temp, retention | Code và test offline; phase 1–5, 12, 20–22 | Executor/browser và kết nối agent thực tế |
| 2: Record, Inspector, gen step, validator | Phase 6–7, 13, 15, 17–19, 26–27; AI biên dịch recording theo Runner | Nghiệm thu recorder/browser và AI runtime trên website thử |
| 3: Discovery, repair | Discovery/repair có người duyệt, phase 13–14 | Người dùng đã chốt AI xử lý bản ghi thao tác; bỏ hướng tự điều hướng/tự thực thi nghiệp vụ |
| 4: Notification, cleanup, audit, GreenNode | Code quản lý vòng đời và hướng dẫn đóng gói | Build image, persistent storage, GreenNode, UAT thực tế |
| Crawler bổ sung theo yêu cầu | Phase 8–11: cookie, báo lỗi, bulk/bảng/lịch, pause, export | Nghiệm thu nguồn thử, restart và lịch append |

## Các phase còn lại và trạng thái

| Phase | Nội dung | Trạng thái | Điều kiện hoàn tất |
| --- | --- | --- | --- |
| 23 | Chốt phạm vi, đối chiếu MVP, checklist bàn giao | Hoàn tất tài liệu | Bảng này và RUNNER_ACCEPTANCE.md chỉ rõ phần có/chưa có |
| 24 | Kiểm chứng đóng gói và triển khai thử | UI local đạt smoke; phần Docker API tạm để lại theo yêu cầu người dùng | Build API/UI, kiểm tra health/readiness, persistent storage và kết nối agent trên môi trường thử |
| 25 | UAT, sửa lỗi, bàn giao | Đã diễn tập restart offline; chưa UAT thật | Các ca áp dụng trong RUNNER_ACCEPTANCE.md đạt và có kết quả đã che dữ liệu |
| 26 | Recorder iframe/shadow mở, check/uncheck/upload | Có code và test offline/DOM tổng hợp | Cần nghiệm thu browser thật |
| 27 | Recording → AI → cấu hình đúng Runner | Có code, API/UI và test offline | Cần nghiệm thu AI runtime; mọi step inactive, testcase chỉ header |

Phase 24–25 cần bằng chứng môi trường thật; test offline không thay thế được.
Lỗi tìm thấy khi nghiệm thu được sửa trong phase tương ứng, không tự thêm tính năng
hoặc kéo dài roadmap bằng các phase không có tiêu chí kết thúc.

## Phạm vi chốt

- Crawl công khai; chỉ Runner yêu cầu đăng nhập. Cookie do người dùng nhập theo lượt.
- Crawl nhiều lượt/thời gian/bảng, lưu record, lịch append, pause/resume/cancel.
- Gen đủ steps và header testcase; người dùng tự nhập testcase. Không tự sinh settings;
  chỉ đề xuất setting cần cho executor, giải thích và hỏi riêng từng thay đổi.
- Executor local, summary cloud, journal chống replay; artifact chi tiết giữ local.
- AI đề xuất, người dùng review; không tự điều hướng hoặc chạy lại thao tác nghiệp vụ.
- MVP dùng SQLite và một API process. PostgreSQL/multi-worker, queue bền vững,
  lịch có cookie theo user, shadow DOM đóng/drag-drop và mọi widget tùy biến là backlog.

## Bằng chứng và nhật ký

- CHANGELOG.md: thay đổi từng phase và kết quả test.
- runner_local_greennode_integration_design_v2.md: quyết định kiến trúc cập nhật.
- docs/RUNNER_ACCEPTANCE.md: ma trận chức năng, giới hạn và ca nghiệm thu.
- docs/RUNNER_SETUP.md: lệnh vận hành, chẩn đoán và xử lý sự cố.
- docs/RUNNER_UAT_RESULTS.md: trạng thái bằng chứng triển khai/UAT; không ghi secret.

Không tự thay CLAUDE.md. Không lưu raw log, cookie, token, workbook hoặc dữ liệu
nghiệp vụ vào tài liệu tiến trình. Nhật ký tài liệu không có nghĩa đã tạo Git commit.
