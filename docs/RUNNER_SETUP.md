# Runner local: chạy thử bản tích hợp

## Phạm vi hiện tại

Đã có executor workbook, tài khoản user/admin, agent polling, UI tạo/xem run,
phân quyền theo chủ sở hữu, summary và retention. Runner mặc định tắt để giữ
luồng crawler hiện tại. Có Record local và Describe AI xuất workbook nháp.
Inspector, AI repair và chuyển artifact chi tiết lên cloud là phần chưa triển khai.

Cloud chỉ nhận số đếm PASS/FAIL/ERROR/UNVERIFIED và thời gian chạy. Excel, log,
screenshot nằm trong thư mục state trên máy agent. Masking không bảo đảm loại
bỏ mọi dữ liệu nghiệp vụ trên trang; không gửi các artifact này cho AI/cloud.

## Cài và bật

Chạy từ thư mục gốc project trong môi trường Python đang dùng cho ứng dụng:

```powershell
python -m pip install -r requirements.txt -r requirements-auth.txt -r requirements-runner.txt
python -m playwright install chromium
python scripts/create_runner_admin.py --username runneradmin
$env:RUNNER_ENABLED = 'true'
python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

Bootstrap hỏi mật khẩu bằng đầu vào ẩn, chỉ dùng cho database Runner SQLite
mặc định `data/runner.db`. Không chạy lại bootstrap trên database đã có user.
API và bootstrap phải trỏ cùng database nếu đổi đường dẫn. Backend PostgreSQL
có adapter nhưng chưa được kiểm chứng integration; chưa dùng làm cấu hình triển khai.

Ở terminal khác, chạy UI như trước:

```powershell
python -m streamlit run ui/app.py
```

Mở trang **Runner**, đăng nhập, tạo agent và giữ token được cấp một lần.
Trên máy truy cập được hệ thống cần test, chuẩn bị thư mục `config` chứa workbook
và file môi trường local theo `runner.env.example`. Chỉ người vận hành quản lý
file thật, không upload hoặc gửi nội dung cho trợ lý.

```powershell
python local_runner_agent.py --api http://localhost:8000 --configs config --state data/local-runner --env-path runner.env
```

Agent hỏi token bằng đầu vào ẩn. Dùng HTTPS nếu API ở máy khác. Trên UI chọn agent
và tên workbook trong thư mục config để tạo run. Chế độ local là mặc định;
Hybrid cho phép upload workbook đã bỏ dữ liệu nhạy cảm, server xóa bản tạm sau
khi kết thúc hoặc job hết hạn. Validator không thể nhận diện mọi secret tùy ý
trong Excel; người vận hành phải kiểm tra trước khi upload. Dùng `${TEN_BIEN}`
cho giá trị cần resolve từ môi trường local.

## Vận hành và giới hạn

- Mỗi agent chạy một job, mỗi run dùng process riêng; không tự chạy lại testcase
  khi mất kết nối. Chỉ kết quả được gửi lại. Nếu agent chết, kiểm tra trình duyệt/
  worker còn sống và trạng thái nghiệp vụ trước khi chủ động tạo run mới.
- Mất heartbeat quá 5 phút chuyển run sang LOST; kết quả đến muộn không đổi
  trạng thái terminal. Job chờ quá 24 giờ hết hạn.
- Artifact giữ 7 ngày, có thông báo trước khi xóa ít nhất 24 giờ. Agent offline
  thực hiện retention khi chạy lại; thời gian giữ có thể kéo dài. Metadata/audit
  giữ lại. UI hiển thị thông báo server, console agent hiển thị thông báo local.
- API cloud cần HTTPS, persistent storage, giới hạn request/login ở reverse proxy
  và quy trình backup trước khi đưa vào vận hành nhiều người dùng.
- Chưa kiểm chứng Docker/GreenNode deployment, PostgreSQL hoặc browser trên UAT thật.

## Record local (bản đầu)

Tạo sẵn thư mục config và chạy trên máy người dùng:

```powershell
python record_runner.py --output config/Recorded_Draft.xlsx
```

Browser mới không dùng profile đăng nhập có sẵn. Người dùng tự mở website và
thao tác; đóng các tab để xuất workbook. Recorder không đọc file môi trường,
giá trị input, text/attribute của phần tử hoặc URL điều hướng. Chỉ ghi click,
fill và select HTML chuẩn ở trang chính, bằng CSS theo vị trí phần tử.
Không gửi recording lên server. File output phải chưa tồn tại.

Workbook nháp có step và testcase `active=N`. Đặt URL local, kiểm tra locator,
ánh xạ placeholder `${REC_FIELD_0001}` sang biến môi trường local thích hợp,
đặt role/account nếu luồng cần, thêm assertion rồi chủ động bật các dòng đã
rà soát. Không coi một flow chỉ click/fill là testcase đã xác minh kết quả.

Giới hạn: chưa ghi iframe/shadow DOM, upload, checkbox/radio, dropdown tùy biến,
navigation hoặc assertion; tối đa 1000 event. CSS theo vị trí cần sửa khi layout
thay đổi. Số event bị từ chối nằm trong sheet review. Bản này chưa có AI hay
inspector tìm locator ổn định. Đóng browser bình thường để xuất; kill process
hoặc Ctrl+C có thể mất recording chưa xuất. Browser UAT thật cần người dùng kiểm chứng.

## Describe AI (workbook đầy đủ)

Backend dùng các biến runtime `AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL` và
`AI_TIMEOUT_SECONDS` đã có. Người vận hành tự cấu hình; không gửi giá trị thật
cho trợ lý. Để bật Describe, đặt thêm `RUNNER_AI_ENABLED=true` cùng
`RUNNER_ENABLED=true` rồi khởi động lại API. Endpoint AI phải dùng HTTPS
(HTTP chỉ cho loopback). Không cần thay client AI của crawler.

Trong tab **Describe**, nhập flow ngắn chỉ dùng role/placeholder, kiểm tra nội dung
không có dữ liệu nhạy cảm và xác nhận gửi cho AI. Bấm **Tạo workbook nháp**, sau đó
tải workbook về máy. API không lưu mô tả, phản hồi model hoặc workbook xuống disk/DB;
audit chỉ ghi event `DRAFT_GENERATED` và người thực hiện. UI giữ workbook trong phiên
cho đến khi xóa nháp hoặc đăng xuất. Nội dung mô tả được gửi tới nhà cung cấp AI;
chính sách lưu dữ liệu của nhà cung cấp nằm ngoài cơ chế lưu trữ của ứng dụng.

AI tạo JSON gồm **settings, steps và testcases**; Python kiểm tra liên kết giữa
các sheet rồi xuất workbook. Không chỉ sinh action/target. Workbook gồm:

- `settings`: đầy đủ key executor đang đọc, screen_flow/login_screen/result_screen,
  browser, timeout, session và các mục selector dành cho website.
- `steps`: `screen`, `step`, `action`, `locator_type`, `locator`, `value_source`,
  `active`, `wait_selector`, `dropdown_selector`, `match_type`, `prefill_check`,
  `group`, `read_method`.
- `testcases`: các cột metadata, nhiều scenario, cột input liên kết tên step và
  `expected_*` cho các kiểm tra kết quả được yêu cầu. Input/expected chỉ dùng
  placeholder `${TEN_BIEN_LOCAL}`; username/password resolve qua role/account.
- `review`: những phần phải kiểm tra trước khi bật chạy.

Ví dụ mô tả: “Role RM đăng nhập, tìm theo CIF, đọc số tiền. Tạo hai testcase
cho hai khách hàng giả lập, kiểm tra số tiền; mọi dữ liệu dùng biến local.”
Workbook sẽ có cột dữ liệu tìm kiếm, step đọc kết quả và cột expected tương ứng.
Tên cụ thể do AI đề xuất; validator bắt buộc các tên khớp giữa sheet.

Hỗ trợ các action executor hiện có, gồm dropdown, wait và read_result. Assertion
được tạo khi người dùng yêu cầu; không tự suy diễn giá trị nghiệp vụ. Hiện gen
so sánh exact, group lặp vẫn trống; group result chỉ có expected cho block đầu,
cần mở rộng thủ công nếu có nhiều block. Các trường tùy chọn vẫn xuất đầy đủ.

Backend từ chối code, giá trị input literal, locator tự đoán và field ngoài schema.
Bản nháp chưa inspect website: locator `:not(*)` không khớp phần tử nào,
step/testcase `active=N`; các selector/class/label trong settings cũng cần rà soát.
Người dùng phải đặt URL, thay locator, map placeholder và kiểm tra assertion trước
khi chạy. Runner resolve expected placeholder local, báo lỗi nếu thiếu biến.
Không tạo run hoặc tự mở browser khi bấm tạo nháp.

Mô tả giới hạn 6000 ký tự, tối đa 100 step và 25 testcase, hai yêu cầu AI đồng thời mỗi API process;
không tự retry. Có chặn mẫu credential/URL thường gặp, nhưng không thể nhận diện
mọi secret trong văn bản tự do: việc rà soát trước khi gửi là bắt buộc. Reverse proxy
cần đặt quota/rate limit theo chính sách triển khai. Chưa gọi model GreenNode thật
trong kiểm chứng; test dùng MockTransport, không cần API key thật.

## Kiểm tra không dùng secret

```powershell
python -B scripts/test_offline.py -x
```

Bộ kiểm tra dùng dữ liệu giả, chặn mạng và việc mở file secret, không chạy
PostgreSQL integration mặc định. Người vận hành tự chạy UAT và chỉ gửi số liệu/
output đã che dữ liệu nhạy cảm để đối chiếu.
