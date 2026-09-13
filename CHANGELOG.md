# Changelog

Format dựa trên [Keep a Changelog](https://keepachangelog.com/) — mỗi mục ghi ngắn gọn,
hướng người đọc (họ được lợi gì / cái gì mới), không liệt kê tên file đã sửa (xem diff).

## [Chưa phát hành]

### Đã thêm
- Tách Docker image riêng cho Runtime API và Runtime UI (`Dockerfile.api`, `Dockerfile.ui`)
  để deploy lên GreenNode AgentBase (mỗi Agent Runtime = 1 image riêng), có route
  `GET /health` cho cả 2 service phục vụ liveness/readiness check của nền tảng.
- Gắn cờ `needs_review` cho record khi confidence thấp hơn `AI_CONFIDENCE_THRESHOLD` —
  record vẫn luôn được lưu, chỉ cảnh báo thêm cho người dùng qua UI/API.
- Panel admin nội bộ "AI gợi ý sửa lỗi" cho job lịch bị lỗi — chỉ hiển thị gợi ý dạng
  text, không tự động sửa code.
- Lựa chọn lưu kết quả ra file JSON (`data/exports/`) thay cho lưu DB, áp dụng cho cả
  crawl 1 lần và job lịch.
- Cache "chiến lược" trích xuất theo domain (selector rule-based) để giảm gọi AI lặp lại.
- Chạy job crawl định kỳ bằng APScheduler, quản lý qua UI (tạo/xem/xoá lịch).
- Ưu tiên đọc structured data có sẵn (JSON-LD/Open Graph) trước khi gọi AI.
- Kiểm tra `robots.txt` thật + rate-limit theo domain trước khi fetch.
- Hỗ trợ fetch site JS-heavy bằng Playwright (adapter riêng, chưa bật mặc định).
- Giao diện Streamlit 5 bước (nguồn dữ liệu → trường dữ liệu → chạy & kết quả → dữ liệu
  đã lưu → lịch tự động), hỗ trợ cả 2 lựa chọn lưu (DB/file) và trang admin riêng.

### Đã sửa
- Xác nhận lại format API GreenNode MaaS thật (endpoint, auth, model ID) thay vì giả định.

## Cách dùng file này

Mỗi khi hoàn thành 1 phần việc (feature/fix), cập nhật mục "Chưa phát hành" ngay trong
cùng commit — không dồn lại cuối phiên làm việc.
