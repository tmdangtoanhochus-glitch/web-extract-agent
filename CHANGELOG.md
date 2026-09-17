# Changelog

## Crawler — cập nhật 2026-09-16

### Phase 9: xem trước và chạy lại lượt lỗi
- Bước 3 có Xem trước đợt kéo: hiển thị số lượt, cửa sổ ngày và số trang; chế độ
  bảng tải đúng trang đầu và hiển thị tối đa 10 dòng mẫu. Không tạo dataset/record,
  không ghi file/cache trích xuất, không gọi AI. Audit chỉ metadata, không lưu mẫu.
- Thêm chạy lại riêng lượt lỗi cho bảng DB, giữ nguyên dataset và số thứ tự trong
  kế hoạch gốc. Backend so fingerprint cấu hình, dataset và kết quả audit trước khi
  chọn lượt; đổi cấu hình bị từ chối. Giữ dedup khi một lượt đã lưu được một phần.
- Retry do người dùng chủ động, không tự động; không áp dụng file append, chế độ
  fields, lịch có khoảng ngày di động hoặc đợt chưa có kết quả xác định. Cookie cần
  nhập lại, không lưu trong snapshot cấu hình. UI giữ lịch sử retry trong phiên hiện tại.
- Lỗi bảng có mã và hướng dẫn riêng cho selector, ô gộp, số cột, ngày và giới hạn
  dòng; lỗi tải/lưu không phản chiếu nội dung trang hay exception message thô.
- Admin thấy lịch lỗi một phần và kết quả từng lượt; chẩn đoán AI của lịch bulk
  dùng metadata, không đọc source/DOM. Sửa báo lỗi UI khi trạng thái exception là None.
- Kiểm chứng: **381 test pass** offline, gồm 10 test mới cho preview/retry/API/UI và
  lỗi lịch một phần. Còn một deprecation warning Starlette/AnyIO. Chưa gọi website,
  AI hay PostgreSQL thật; không sửa CLAUDE.md, settings Runner hoặc dữ liệu testcase.

### Phase 8a: cookie theo lượt và báo lỗi từ người dùng
- Chuyển nhập cookie sang Bước 3, kèm hướng dẫn Chrome Network. Form xóa sau submit;
  cookie chỉ dùng trong bộ nhớ cho đúng origin, không lưu vào DB/lịch/audit và chặn
  redirect khác origin. Fetcher mặc định ngừng dùng kho cookie chung của admin;
  admin vẫn xem metadata/xóa mục cũ. Lịch nguồn cần cookie chưa hỗ trợ cơ chế phiên mới.
- Mỗi lần crawl có request ID và audit metadata. Người dùng gửi báo lỗi không cần
  đăng nhập Runner; hộp báo lỗi nằm ngoài renderer để vẫn dùng khi gặp TypeError.
- Admin có hộp báo cáo, có thể yêu cầu AI chẩn đoán metadata và lưu kết quả. Không
  gửi raw HTML/cookie/giá trị record/exception message; không tự sửa code hay gửi email.
- Lỗi validation không phản chiếu input. Đọc code cho debug chỉ cho phép file Python
  trong repo, loại đường dẫn secrets/credential.

### Phase 8b: kéo nhiều lượt, lịch sử, bảng và lịch append
- Thêm `CrawlOptions` và pipeline bulk riêng, giữ pipeline một trang hiện tại.
  Hỗ trợ URL `{start}/{end}/{page}`, khoảng ngày bao gồm hai đầu, chia cửa sổ và
  phân trang số; giới hạn 100 lượt/đợt. Kết quả ghi số lưu/bỏ qua/lỗi từng lượt.
- Bảng HTML: selector đúng một bảng, field ánh xạ cột từ 1, tùy chọn cột ngày/format;
  mỗi dòng là một record. Bỏ qua dòng trùng toàn bộ dữ liệu trong cùng dataset,
  kiểm tra hết lịch sử theo trang; thay đổi dữ liệu append bản mới. Ghi source và as_of.
- File bulk dùng append, giữ hành vi không dedup của luồng file. Bảng có ô gộp,
  bảng JS-only và tải ảnh trong ô chưa hỗ trợ; không âm thầm coi như thành công.
- Bước 5 dùng lại cấu hình đợt vừa kéo để đặt lịch, thay khoảng cố định bằng N ngày
  gần nhất (UTC). Cấu hình được lưu/nạp lại qua SQLite/Postgres; SQLite migration
  giữ lịch cũ. Bulk tuần tự trong một backend process để tránh chồng lấn append.
- Giới hạn: request đồng bộ, UI timeout 600 giây, không background queue/checkpoint
  hoặc khóa nhiều worker; đợt dài cần chia nhỏ. Chưa test PostgreSQL/UAT/GreenNode thật.
- Bước 4 có phân trang 100/500/1000 record; CSV ghi rõ chỉ xuất trang đang xem.
- Hướng dẫn đầy đủ: `docs/CRAWL_SUPPORT.md`.
- Kiểm chứng phase 8a–8b: **371 test pass** offline (356 test trước đó và 15 test mới),
  một deprecation warning Starlette/AnyIO. Bao gồm cookie isolation, redirect,
  báo lỗi TypeError sau fetch, AI metadata, backfill/phân trang/lọc ngày, dedup khi
  chạy chồng nhau và lịch sử hơn 1000 record, SQLite migration/reload và UI chuyển cấu hình sang lịch.
  Chưa gọi mạng, AI hay credential thật; chưa kiểm chứng PostgreSQL và deploy thực tế.

## Runner integration — cập nhật 2026-09-16

### Điều chỉnh phạm vi gen và đăng nhập theo yêu cầu người dùng
- Thay quyết định phase 6c: Describe/Record chỉ sinh steps và header testcases,
  không sinh dòng testcase, dữ liệu input/expected hoặc settings (kể cả mẫu).
  Schema AI từ chối cả trường settings/testcases nếu model cố trả về.
- Thêm prepare_runner.py ghép local với config có sẵn: giữ dữ liệu người dùng,
  bổ sung cột trống; settings giữ nguyên mặc định. Mỗi đề xuất settings có lý do
  gắn với hàm executor và hỏi riêng từng mục trước áp vào bản sao.
- Đăng nhập chỉ dành cho Runner; crawl công khai vẫn dùng không cần đăng nhập.
  Thêm test chạy crawl với Runner đã bật nhưng không có session; Runner trả 401.

### Phase 7c: kiểm tra config trước chạy
- Tiếp tục phát triển preflight local: báo thiếu settings/testcase active, locator
  nháp, màn hình không khớp flow/result. Chỉ báo số dòng/mã lỗi, không in nội dung
  dữ liệu, mở browser hay đọc secret. Không tự thay đổi config hoặc kích hoạt step.
- Kiểm chứng chung cho điều chỉnh phạm vi và phase 7c: **356 test pass**, gồm
  từ chối settings/testcases từ AI, xuất header-only, giữ dữ liệu template,
  duyệt riêng từng setting, preflight và crawl công khai khi Runner bật.
  Còn một deprecation warning Starlette/AnyIO; chưa gọi GreenNode/UAT thật.

### Phase 7b: repair local có xác nhận
- Thêm picker Ctrl+Alt+L theo phần tử người dùng trỏ tới; chỉ lấy CSS cấu trúc,
  không lấy input value/text/attribute hay gửi DOM lên cloud.
- Kiểm tra lại identity/visibility/uniqueness sau xác nhận; hash workbook phải
  khớp lúc bắt đầu. Xuất bản sao, không sửa nguồn hoặc ghi đè output.
- Giữ các sheet/dữ liệu, chỉ đổi locator dòng chọn; mọi step/testcase trong bản
  sao inactive. Thêm repair_review ghi nguồn và thay đổi để rà soát.
- Có hướng dẫn trong UI và cập nhật V2. Đây là repair người dùng chọn target;
  AI discovery/repair vẫn chưa triển khai, browser UAT/hotkey thật chưa kiểm chứng.
- Kiểm chứng: suite đầy đủ **354 test pass**; bổ sung test selection bị thay đổi
  sau xác nhận rồi chạy riêng repair: **15 pass, 340 deselected**. Kiểm tra giữ
  dữ liệu/sheet, hủy không ghi file, nguồn đổi bị từ chối và không ghi đè output.
  Còn một deprecation warning Starlette/AnyIO.

### Phase 7a: Inspector local
- Thêm CLI kiểm tra locator workbook trong browser local do người dùng tự điều
  hướng, dùng cùng builder với Runner. Không thực hiện step hoặc đọc input value.
- Kiểm tra cả step inactive, ghi số phần tử khớp/visibility theo dòng; phân biệt
  missing, ambiguous, hidden, unresolved, error và mục cần kiểm tra thủ công.
- Report chỉ gồm hash workbook, thời điểm, số màn hình/tab/dòng và số đếm/trạng thái;
  không chứa DOM, URL, selector hay dữ liệu nhập. Không sửa workbook/ghi đè report.
- Thêm tab Inspector local, cập nhật V2 và hướng dẫn. AI repair chưa triển khai;
  report xuất chủ động do người dùng quản lý, không phải artifact của run.
- Kiểm chứng: suite đầy đủ **339 test pass**; sau bổ sung metadata snapshot và
  group review, chạy lại riêng Inspector **16 pass, 324 deselected**. Browser
  dùng giả lập, chưa chạy UAT thật; còn một deprecation warning Starlette/AnyIO.

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
