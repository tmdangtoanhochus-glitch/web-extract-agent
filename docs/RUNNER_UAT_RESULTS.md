# Kết quả kiểm chứng triển khai và UAT

Cập nhật 2026-09-17. Chỉ ghi metadata đã che dữ liệu.

| Nhóm | Trạng thái | Bằng chứng |
| --- | --- | --- |
| Regression offline phase 24 | Đạt | 513 test pass; một warning Starlette/AnyIO; 3 test context chạy lại đạt sau bổ sung danh sách source |
| Docker UI build | Đạt local | Image fca03e1265bb, Python 3.12 Linux; context source riêng 58 file |
| Docker API build | Đang chạy | Đang cài Chromium; chưa nghiệm thu image |
| UI /health, /ready và trang gốc | Đạt local | 200/200/200 trong container network none |
| UI thiếu Streamlit | Đạt local | Chỉ nginx: /health 200, /ready 502 |
| API /health và ranh giới đăng nhập | Chưa chạy | Chờ image API |
| Persistent storage sau restart | Chưa chạy | Cần volume thử, dữ liệu giả |
| GreenNode/API–UI–agent | Chưa chạy | Người vận hành cấu hình môi trường và secret |
| UAT crawler | Chưa chạy | Ca trong RUNNER_ACCEPTANCE.md |
| UAT Runner/browser, phân quyền, mất mạng, retention | Chưa chạy | Ca trong RUNNER_ACCEPTANCE.md |

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
