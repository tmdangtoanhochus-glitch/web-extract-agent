# Kết quả kiểm chứng triển khai và UAT

Cập nhật 2026-09-17. Chỉ ghi metadata đã che dữ liệu.

| Nhóm | Trạng thái | Bằng chứng |
| --- | --- | --- |
| Regression offline phase 27 | Đạt | 562 test pass, gồm sửa nút input và thứ tự fill giữa các frame; một warning Starlette/AnyIO có sẵn |
| Bản sửa nút input và gộp fill | Đạt offline | DOM tổng hợp, bộ nhận sự kiện chung, compiler và xuất JSON/workbook; chưa browser thật |
| Recorder mở rộng | Đạt offline | DOM JavaScript tổng hợp, scope lồng nhau, upload/check/uncheck; chưa browser UAT |
| AI biên dịch recording | Đạt offline | AI HTTP giả lập, contract Runner, UI review và giữ event mapping qua compose/prepare; chưa model thật |
| Docker UI build | Đạt local | Image fca03e1265bb, Python 3.12 Linux; context source riêng 58 file |
| Docker API build | Bị gián đoạn | Đã cài dependency Python; mất kết nối Docker daemon khi tải Chromium, chưa xác nhận image hoàn tất |
| UI /health, /ready và trang gốc | Đạt local | 200/200/200 trong container network none |
| UI thiếu Streamlit | Đạt local | Chỉ nginx: /health 200, /ready 502 |
| API /health và ranh giới đăng nhập | Chưa chạy | Chờ image API |
| Persistent storage sau restart | Chưa chạy | Cần volume thử, dữ liệu giả |
| Khởi động lại ứng dụng với SQLite tạm | Đạt offline | Hai ca test_mvp_restart: crawl/dedup, Runner result/summary/ownership, report TypeError, không claim lại run đang chạy |
| GreenNode/API–UI–agent | Chưa chạy | Người vận hành cấu hình môi trường và secret |
| UAT crawler | Chưa chạy | Ca trong RUNNER_ACCEPTANCE.md |
| UAT Runner/browser, phân quyền, mất mạng, retention | Chưa chạy | Ca trong RUNNER_ACCEPTANCE.md |

## Điểm tiếp tục phase 24

Image UI đã smoke ở phase 24 là phiên bản trước thay đổi Recorder/compiler phase
26–27; chưa build lại image mới. Các test compiler dùng AI HTTP giả lập và DOM
tổng hợp, không xác nhận chất lượng model thực hoặc browser trên website thật.

Người dùng chọn tạm để lại Docker và tiếp tục offline. Docker engine local không
còn truy cập được khi kiểm tra lại sau build. Không
đánh dấu API build thất bại do source, cũng không coi image đã hoàn tất.
Khi engine sẵn sàng, build lại Dockerfile.api từ context cuối cùng; Docker có
thể dùng lại cache dependency đã hoàn tất. Sau đó chạy API seed/verify và browser
theo RUNNER_CONTAINER_SMOKE.md. Hai container UI thử đã được dừng sau nghiệm thu.
Kiểm tra restart offline dùng lifecycle FastAPI đầy đủ và đóng/mở lại hai SQLite
tạm; fetch/AI giả lập, clock Runner cố định. Không có browser thực thi testcase,
không chứng minh container volume hoặc mạng GreenNode hoạt động.

## Mẫu bổ sung kết quả

Mỗi ca ghi: mã ca, phiên bản/commit hoặc image tag đang thử, ngày, đạt/không đạt,
HTTP status hoặc mã lỗi đã che dữ liệu, kết quả mong đợi/thực tế và lỗi cần sửa.
Không gửi raw traceback, URL nội bộ, token, cookie hoặc giá trị testcase.

## Kiểm tra UI sau triển khai

- `/health`: nginx sống; không chứng minh Streamlit hoặc API hoạt động.
- `/ready`: proxy tới `/_stcore/health` của Streamlit; phải trả 200 khi UI sẵn sàng.
  Khi Streamlit dừng, endpoint phải không còn trả 200.
- Mở trang và tương tác để kiểm tra WebSocket; readiness không thay thế bước này.
- API `/health`: process API sống, không chứng minh DB/AI/agent sẵn sàng.

Không chạy compose mặc định để nghiệm thu offline: cấu hình hiện tại tham chiếu
file môi trường thật. Người vận hành tự build/chạy trong môi trường được phép,
kiểm tra build context chỉ chứa source đã rà soát; không đưa local state/credential
vào context. Không đánh dấu phase 24 hoặc 25 hoàn tất khi các mục bắt buộc còn trống.
