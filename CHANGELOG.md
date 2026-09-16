# Changelog

## Runner integration — cập nhật 2026-09-15

### Phase 6c: Generate toàn bộ workbook
- Thay schema action/target bằng workbook plan gồm settings, steps, testcases;
  xuất đủ 13 cột step, các setting executor dùng và nhiều scenario kèm data/expected.
- Validate screen_flow, tên step/testcase duy nhất và tham chiếu input/expected
  giữa các sheet. Dữ liệu chỉ là placeholder; mọi step/testcase vẫn inactive.
- Record export cũng có đủ cột step và setting. Locator/site setting chưa biết
  được đánh dấu cần rà soát, không tự đoán. Có sheet review và freeze/filter header.
- Runner resolve expected placeholder local trước so sánh; thiếu biến báo lỗi.
  Gen assertion exact khi được yêu cầu; repeat group/nhiều result block còn cần bổ sung tay.
- Cập nhật UI và V2 theo yêu cầu generate đầy đủ workbook; không sửa CLAUDE.md.
- Kiểm chứng offline: **324 test pass**. Có round-trip Excel qua loader/validator
  Runner thật, đối chiếu coverage cột/settings với source executor, nhiều testcase,
  expected local và kiểm tra tham chiếu sai. Chưa gọi AI/website UAT thật.

### Phase 6b: Describe AI tạo workbook nháp
- Thêm tab Describe và API có xác thực; dùng GreenNode chat khi bật
  `RUNNER_AI_ENABLED`, mặc định tắt. Client tạo nháp tách khỏi client crawler.
- Validate action/target bằng schema đóng; không nhận code, giá trị input hay
  locator tự đoán. Workbook inactive, locator chưa xác định không khớp phần tử nào.
- Không lưu mô tả/phản hồi AI/workbook trên server; chỉ audit event theo user.
  UI yêu cầu rà soát nội dung trước gửi, cho xóa nháp và xóa nháp khi đăng xuất.
- Chưa inspect website, tự tạo assertion hoặc sửa locator; chưa gọi GreenNode thật.
- Kiểm chứng offline: **310 test pass**, gồm hợp đồng chat qua MockTransport,
  phản hồi AI sai schema, chặn mô tả nhạy cảm trước gọi AI, phân quyền/opt-in,
  audit không lưu nội dung, workbook inactive và UI tải/xóa nháp khi đăng xuất.
  Một deprecation warning Starlette/AnyIO còn tồn tại.

### Phase 6a: Record local và workbook nháp
- Thêm recorder do người dùng chạy local, ghi click/fill/select theo vị trí
  phần tử; không lấy giá trị input, text, attribute hoặc URL điều hướng.
- Xuất workbook tương thích schema Runner với placeholder local, step/testcase
  mặc định inactive để rà soát; không ghi đè file có sẵn, không gửi recording lên cloud.
- Thêm tab hướng dẫn Record local; cập nhật V2 và hướng dẫn về phạm vi hỗ trợ.
  Inspector/Describe/AI generate/repair chưa triển khai, browser UAT chưa kiểm chứng.
- Kiểm tra offline: **291 test pass**, gồm từ chối payload chứa value/locator tùy ý,
  workbook inactive, không ghi đè output và lifecycle recorder giả lập. Có một
  deprecation warning từ Starlette/AnyIO; không gọi browser hoặc UAT thật.

### Phase 2: tài khoản và metadata
- Thêm đăng nhập user/admin, hash Argon2, session có hạn, token riêng cho agent;
  phân quyền run/artifact theo chủ sở hữu. Metadata Runner tách khỏi crawler.
- Runner mặc định tắt; bật tùy chọn qua cấu hình, không thay đổi luồng crawl.

### Phase 3: agent local
- Claim job tuần tự, heartbeat và journal khôi phục; không tự chạy lại testcase
  khi mất kết nối, chỉ gửi lại kết quả. Mỗi run dùng process và thư mục riêng.
- Hỗ trợ workbook local hoặc bản upload tạm; xóa bản copy sau khi kết thúc.

### Phase 4: UI Runner
- Thêm trang đăng nhập, tạo run, lịch sử/summary, quản lý agent, user và audit.
- Chỉ số liệu tổng hợp đi lên server; Excel/log/screenshot được giữ local.

### Phase 5: retention và hướng dẫn
- Thêm retention 7 ngày với cảnh báo tối thiểu 24 giờ trước xóa, audit metadata
  và xử lý agent offline. Thêm Docker exclusions cho dữ liệu local/secret.
- Cập nhật thiết kế V2 và hướng dẫn `docs/RUNNER_SETUP.md`; Record/Describe,
  AI generate/repair và artifact chi tiết trên cloud còn ở phạm vi tiếp theo.
- Kiểm tra offline: **280 test pass**, bao phủ crawler, auth/ownership, agent, retention và UI;
  chưa chạy UAT thật, PostgreSQL integration hay deployment GreenNode.

Format dựa trên [Keep a Changelog](https://keepachangelog.com/) — mỗi mục ghi ngắn gọn,
hướng người đọc (họ được lợi gì / cái gì mới), không liệt kê tên file đã sửa (xem diff).

## [Chưa phát hành]

### Runner integration — Phase 0: baseline test
- Cô lập dotenv, DB và thư mục làm việc khi test; thêm lệnh test offline chặn
  đọc secret và kết nối mạng. PostgreSQL integration chỉ chạy khi bật tường minh
  trên database test riêng. Bộ crawler hiện tại gồm 250 test chạy thành công.

### Runner integration — Phase 1: executor local
- Tái sử dụng runner workbook hiện có qua callable `execute_config`, giữ CLI;
  thêm output theo run và summary PASS/FAIL/ERROR/UNVERIFIED.
- Loại bỏ eval từ ngưỡng so sánh, từ chối action expect chưa triển khai,
  bổ sung validate cột executor cần dùng, che giá trị nhập và artifact.
- Kiểm tra offline: 260 test pass (250 crawler + 10 Runner); chưa chạy UAT thật.

### Đã thêm
- Lựa chọn lưu DB bằng PostgreSQL thay cho SQLite (`DB_BACKEND=postgres` +
  `DATABASE_URL` trong `.env`) — cùng interface `StorageEngine`, chọn qua cấu
  hình chứ không cần sửa code. Có service `postgres` optional trong
  docker-compose (`--profile postgres`) cho dev/test.
- Tải ảnh tài sản về (`data/images/`) khi người dùng đánh dấu tường minh field
  nào là ảnh (checkbox ở Bước 2/Bước 5) — record lưu đường dẫn local thay vì
  chỉ lưu URL; endpoint `GET /images/{file_path}` để tải file. Ảnh lỗi tải
  không chặn record (giữ nguyên URL gốc, chỉ ghi log cảnh báo).
- Crawl trang cần đăng nhập: dán cookie/session đã đăng nhập sẵn (thủ công,
  KHÔNG tự động điền form login) cho từng domain qua panel admin, lưu lại
  dùng chung cho mọi job cùng domain (`site_credentials`).
- Bảo vệ panel admin (`/admin/*`) bằng HTTP Basic Auth (`ADMIN_USERNAME`/
  `ADMIN_PASSWORD` trong `.env`) — mặc định TỪ CHỐI mọi request nếu chưa cấu
  hình, không mở cửa ngầm định.
- Log tiến trình crawl rõ ràng theo từng bước (fetch → làm sạch → structured
  data/cache/AI → lưu) để biết đang ở đâu và có đưa nội dung cho AI hay không.
- Lỗi "Chạy crawl" thủ công (502) giờ được ghi vào `audit_log` và hiển thị lại
  ở panel admin — trước đây chỉ hiện thoáng qua trên UI rồi mất, không tra
  cứu lại được.

### Đã sửa
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
- Cố định theme sáng cho Streamlit (`.streamlit/config.toml`) — trước đây UI tự theo
  dark mode của trình duyệt/hệ điều hành người dùng, khiến chữ trắng hiển thị trên nền
  trắng do CSS trong `ui/app.py` giả định nền sáng.
- AI extract so khớp tên field trả về từ model không phân biệt hoa/thường — trước đây
  model trả key khác cách viết hoa so với tên field yêu cầu (vd. "quote" thay vì "Quote")
  khiến field bị rơi về `None`/confidence 0 dù model đã trích đúng giá trị.
- Sửa lỗi nghiêm trọng ở bước làm sạch HTML (`clean_html`) làm mất toàn bộ nội dung
  chính trên các trang dùng `<div>`/`<span>` để layout thay vì `<p>` (rất phổ biến, vd.
  quotes.toscrape.com) — nếu trang có sẵn bất kỳ heading/`<p>` không liên quan nào khác
  (vd. link "Login"), code cũ coi như "đã tìm được nội dung" và bỏ qua hoàn toàn phần
  div/span chứa dữ liệu thật, khiến AI nhận markdown gần như rỗng.
- `LOG_LEVEL` trong `.env` trước đây được đọc nhưng KHÔNG bao giờ áp dụng (thiếu
  `logging.basicConfig`) — mọi log `INFO` (kể cả log có sẵn từ trước) bị nuốt mất,
  không hiện ra console/`docker compose logs`.

## Cách dùng file này

Mỗi khi hoàn thành 1 phần việc (feature/fix), cập nhật mục "Chưa phát hành" ngay trong
cùng commit — không dồn lại cuối phiên làm việc.
