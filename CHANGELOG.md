# Changelog

## Nguồn API (JSON) + bỏ lịch lưu file + sửa hướng dẫn kiểm thử — 2026-09-21
- **Nguồn là API (JSON)**: ô tick ở Bước 1 (`api_source`). Dán link API vào ô URL; tải bằng httpx (không leo thang Playwright), tự tìm mảng bản ghi, ghép field theo tên hoặc mô tả với khóa JSON (bỏ dấu/hoa thường, khóa lồng `a.b`), **không gọi AI**, confidence 1.0, evidence `api:<khóa>`. Lỗi ghép field liệt kê các khóa có sẵn. Chặn `localhost`/IP nội bộ/`.internal`; tối đa 10 triệu ký tự. Module mới `src/api_source.py`; tham số `api_source` chạy xuyên `/crawl`, job nền, kéo nhiều lượt. Đã chạy thật trên jsonplaceholder (100 bản ghi) và dummyjson (10 bản ghi). Nguồn API luôn đi qua engine httpx (`static_fetcher`), vì engine Playwright bọc JSON trong thẻ HTML; lỗi này lộ ra khi kiểm tra trên bản triển khai (`FETCH_ENGINE=playwright`) và được sửa ngay. Chưa hỗ trợ POST và lịch cho nguồn API.
- **Bỏ lịch lưu file** (đề xuất của Kiên): `POST /schedules` với `storage_mode=file` trả 400; UI Bước 5 chỉ còn lưu DB. Phần thực thi lịch file được giữ để lịch đã tạo trước đây vẫn chạy. Lưu file khi crawl thủ công giữ nguyên (file nằm trên server, tải về qua trình duyệt).
- `docs/samples/Sample_Inputs.xlsx`: workbook mẫu chạy được với trang công khai the-internet.herokuapp.com/inputs (TC01 PASS, TC02 FAIL có chủ đích); đã chạy thật bằng `docs/runner.py` và qua preflight.
- TEST_GUIDE: thêm trang mẫu API/bảng/Automation, ca TC-CR-13, TC-CR-23, TC-CR-50..55, viết lại phần Automation (TC-AU-01..13) giải thích từng chức năng.


## Gộp kien-v2 của Kiên, sửa timeout bảng dày, export Excel runner — 2026-09-21
- Gộp `origin/kien-v2` (commit fallback 3 `document.body.innerText` của Kiên) vào bản hiện tại; xung đột `playwright_fetcher.py` xử lý giữ bản mới + thêm fallback 3.
- **Timeout AI theo số dòng bản ghi**: trang bảng ngắn nhưng dày (data.vietnambiz.vn/macro-economic: 2.643 ký tự, 25 bản ghi, model ~57s, có lần >90s) từng timeout vì công thức chỉ theo độ dài. Thêm `max(công thức cũ, 15 + 4s × số dòng)` tối đa 240s (`_count_record_rows`).
- Gợi ý `{page}` đặt được trong đường dẫn (`https://bonbanh.com/oto/page,{page}`), thông báo lỗi thiếu `{page}` có ví dụ.
- Khung "Automation là gì?" viết lại theo hướng kỹ thuật (workbook steps/testcases, agent claim/heartbeat/journal, executor Playwright, ranh giới bảo mật).
- `docs/runner.py` `export_results_excel`: row `read_result_single` không còn thành block b1/b2 thừa; `overall` vẫn tính cả row single (giữ UNVERIFIED); `expected_*` được strip khoảng trắng. Không dùng nguyên `runner_debug_fixed.py` vì nó dựa trên bản runner cũ (có `eval`, không có redaction/scoped locator).

## Đổi model AI mặc định sang GLM-5.3-flash — 2026-09-21
BTC đề nghị hạn chế qwen3.6-flash. Đổi `AI_MODEL=z-ai/glm-5.3-flash-thirdparty` trong `deploy/runtime-api.env` (chỉ đổi cấu hình, không build lại image); hạn mức 5 request/phút đã có sẵn trong `AI_MODEL_LIMITS`. Cần kiểm tra chất lượng trích xuất trên trang thật.

## Hạn mức AI theo model + tiến độ Crawl tách ①CODE / ②AI — 2026-09-20
**Bối cảnh (đo thật trên key của dự án):** GreenNode đặt hạn mức request/phút RIÊNG cho từng model — qwen3.6-flash **2**,
glm-5.3-flash / glm-5.2-hackathon / deepseek-v4-pro **5**; token 1 triệu/phút, 100 triệu/ngày (không phải nút thắt). Vượt hạn
mức trả **429 "API rate limit exceeded"** kèm `Retry-After`. Trước đây code KHÔNG có giới hạn nào cho lời gọi AI và thử lại tức
thì khi 429 (chắc chắn dính 429 lần nữa) → chế độ "Nhanh" với trang > 2 đoạn sẽ mất đoạn.
- **Bộ giới hạn theo model** (`src/ai/rate_limiter.py`): cửa sổ trượt 60s, mỗi model một bộ đếm riêng, an toàn giữa các luồng.
  Vượt hạn mức thì TỰ CHỜ (delay) thay vì bắn rồi nhận 429. Cấu hình bằng `AI_MODEL_LIMITS=model=số,model=số`
  (mục sai định dạng bị bỏ qua kèm cảnh báo). Header `x-ratelimit-limit-minute` của API (nếu có) **ghi đè** số cấu hình.
- **Xử lý 429 đúng cách:** chờ đúng `Retry-After` (chặn mọi luồng gọi model đó), thử lại tối đa 4 lần, KHÔNG tính là "đoạn lỗi"
  và không tiêu hao lần thử lại thường. Chế độ Nhanh giờ mỗi phút chỉ GỬI tối đa bằng hạn mức của model (các đoạn còn lại tự chờ), không bắn cả loạt.
- **Tiến độ Crawl tách hai thanh** (`ui/crawl_progress.py`): ① CODE — tải trang → làm sạch (kèm số ký tự gửi AI); ② AI — số
  đoạn xong/tổng, đang xử lý đoạn nào, đang chờ hạn mức còn ~Ns ("không phải lỗi"), thử lại, đoạn lỗi, trang bị cắt. Dòng trạng
  thái nói rõ ai đang làm: CODE / MODEL AI / chờ hạn mức / đang lưu / hoàn tất. Áp dụng cho crawl 1 URL (luồng nền + hỏi
  `GET /crawl-progress/{progress_id}` mỗi ~0,8s) và cho job nền (kéo nhiều lượt, chế độ trường).
- Kỹ thuật: `progress_id` 32 hex do UI sinh (loại khỏi `config_fingerprint`, không lưu vào cấu hình chạy lại/lịch); kho tiến độ
  trong bộ nhớ tự hết hạn (15 phút, tối đa 500), chỉ chứa nhãn + số đếm, không có nội dung trang/cookie. Lỗi callback tiến độ
  không bao giờ làm hỏng crawl.
- Chưa áp dụng bộ giới hạn cho ô phản hồi AI (`AI_DEBUG_*`) và Runner AI (dùng chung key nên vẫn chia sẻ hạn mức thật của model);
  ô phản hồi đã có giới hạn riêng 20 lượt/phút.
- Sửa `Dockerfile` gốc cho khớp `Dockerfile.api` (thêm `--timeout/--retries` cho pip) — trước đó test đồng bộ Dockerfile bị đỏ.
- Test: 676 pass (thêm 51 test: bộ giới hạn với đồng hồ giả + đa luồng, 429/Retry-After/delay/học header, sự kiện tiến độ,
  kho tiến độ, endpoint, tích hợp UI). Đã xem thực tế bằng trình duyệt với API cục bộ chạy chậm.

## Chế độ trích xuất "Nhanh (tốn)" / "Chậm" cho trang dài — 2026-09-20
Người dùng tự tick chọn ở Bước 3 (mặc định **tắt** = Chậm, giữ nguyên `_MAX_CHUNKS=6`):
- **Chậm (mặc định):** gọi các đoạn tuần tự như hiện tại — an toàn, không tăng tải đồng thời lên AI/server.
- **Nhanh (tốn):** gọi TẤT CẢ đoạn ĐỒNG THỜI (`ThreadPoolExecutor`, không cần dependency mới) — giảm hẳn thời gian
  chờ với trang nhiều bản ghi. **Không đổi số lượt gọi/chi phí AI** so với Chậm — "tốn" ở đây là tải đồng thời lên
  endpoint AI và lên chính container API (nhiều luồng threadpool cùng lúc), không phải tốn thêm tiền cho cùng dữ
  liệu. Hành vi gộp kết quả (thứ tự đoạn, thử lại, bỏ qua đoạn lỗi, cảnh báo cắt bớt) giống hệt chế độ Chậm.
- Xuyên suốt: `AIClient.extract(..., parallel=bool)` → `ai_extract(..., parallel_extract=)` → `run_crawl_job`/
  `run_file_crawl_job`/`run_bulk` → `CrawlRequest.parallel_extract` (API) → ô tick ở `ui/crawl_controls.py`.
- **Đã kiểm chứng với model thật** (không chỉ test giả lập): cùng 1 markdown 10.479 ký tự/2 đoạn/60 bản ghi — Chậm
  115,4s, **Nhanh 47,1s** (~2,4×), cả hai đều 60/60 bản ghi, không lỗi.
- Test: 625 pass (thêm 9 test: chạy thật song song không phải tuần tự trá hình, giữ đúng thứ tự đoạn dù hoàn thành
  không theo thứ tự, hành vi bỏ qua đoạn lỗi giống hệt chế độ tuần tự, cờ xuyên đúng từ UI → API → pipeline → AI
  client, mặc định tắt).

## AI extract chịu tải trang dài tốt hơn (chia đoạn) — 2026-09-20
Trang danh sách dài (vd. batdongsan.com.vn) hay bị `extract_failed` vì đoạn ĐẦU TIÊN timeout làm hỏng cả lượt, dù
các đoạn sau vẫn ổn. Sửa ở `src/ai/greennode_client.py` (không đổi endpoint/model — vẫn đúng format GreenNode MaaS):
- **Thử lại 1 lần mỗi đoạn** khi lỗi (timeout thường là tải đột biến tạm thời), với timeout dài hơn ở lần thử lại.
- **Timeout theo kích thước đoạn**, không cố định cho mọi đoạn — đoạn gần 8000 ký tự được timeout dài hơn đoạn ngắn;
  `AI_TIMEOUT_SECONDS` luôn là mức sàn, không bị rút ngắn.
- **Một đoạn lỗi (kể cả đoạn đầu) không còn làm hỏng cả trang** — bỏ qua đoạn đó, giữ bản ghi các đoạn còn lại; chỉ
  báo lỗi khi TẤT CẢ đoạn đều lỗi.
- **Không còn cắt bớt trang âm thầm.** Khi có đoạn bị bỏ qua hoặc trang vượt quá 6 đoạn (48.000 ký tự), kết quả vẫn
  `status: "saved"` kèm `detail` giải thích rõ (đã lộ ra `CrawlResponse.detail`, hiển thị trong Console log của UI) —
  trước đây chỉ ghi log server, người dùng không biết dữ liệu bị thiếu.
- `ExtractionResult`/`AiExtractResult` thêm trường `warning` (khác `error`: `success=True` nhưng chưa trọn vẹn).
- Test: 616 pass (thêm 9 test cho chia đoạn/thử lại/warning, giữ nguyên hành vi các đoạn thành công 100%).

**Hiệu chỉnh timeout theo số liệu đo thật (cùng ngày, sau khi stress-test với model thật qua GreenNode MaaS).**
Công thức ban đầu (`base*(0.5+ratio)`, tối đa 1.5×) SAI — đo thật với `qwen/qwen3.6-flash` cho thấy thời gian model trả
lời tỉ lệ gần tuyến tính theo SỐ BẢN GHI cần sinh JSON, không chỉ độ dài input: 10 bản ghi (~1300 ký tự) ~31s, 25 bản
ghi (~3300 ký tự) ~57s, 60 bản ghi (đầy 1 đoạn 8000 ký tự) ~101,5s — với `AI_TIMEOUT_SECONDS=30` mặc định, công thức
cũ chỉ cho tối đa 45s ở đoạn đầy nên **luôn timeout** với trang nhiều bản ghi, y hệt lỗi ban đầu. Đổi thành
`base*(1.0+3.0*ratio)` (tối đa 4× ở đoạn đầy, có biên an toàn ~20%). Đã kiểm chứng lại bằng 2 bài thật với AI/model
production qua GreenNode:
- Client trực tiếp, markdown giả lập 60 bản ghi (10.479 ký tự, 2 đoạn): trước khi sửa công thức — **cả 2 đoạn timeout
  hoàn toàn kể cả sau khi thử lại** (187,5s, 0 bản ghi); sau khi sửa — **60/60 bản ghi**, 115,4s, không lỗi.
- Qua endpoint `/crawl` thật, trang Wikipedia "Hà Nội" (214.947 ký tự, chia 29 đoạn, xử lý 6 đoạn đầu theo giới hạn):
  1 đoạn timeout ở lần thử đầu, **thử lại thành công** (nếu không có cơ chế thử lại, code cũ sẽ dừng luôn ở đây, bỏ
  mất 4 đoạn còn lại) — kết quả `status: "saved"`, 45 bản ghi, `detail` báo đúng phần trang bị cắt bớt.

## Giao diện dùng chung + hướng dẫn cài Python sau đăng nhập — 2026-09-19
- **Giao diện:** `ui/theme.py` dùng chung cho Crawl, Automation và Admin (banner, thẻ/tab/nút/khung mở rộng nổi khối, bóng đổ). Tab active có gradient.
  Trái tim 🧡 thay bằng huy hiệu **MSB**; đặt file `ui/assets/msb_logo.png` (.svg/.jpg/.webp) để dùng logo thật ở banner và biểu tượng tab.
- **Automation:** hướng dẫn cài Python (8 bước, lỗi thường gặp, lệnh agent điền sẵn địa chỉ API) hiện **sau khi đăng nhập**, mở sẵn ở lần đầu của phiên,
  thu gọn các lần sau (`ui/runner_setup_guide.py`).
- **Thanh bên:** mục điều hướng (Crawl/Automation/Admin) dạng thẻ nổi khối, mục đang chọn có gradient, hiệu ứng khi rê chuột; nút đóng/mở thanh bên là nút bo góc nổi khối.
  Logo tự nhận dạng nền trong suốt hoặc nền liền và tự thu nhỏ (`ui/theme.py`).
- **Cookie:** giữ nguyên thiết kế của Kiên (dán ở Bước 3, không lưu, xóa sau mỗi lần gửi), thêm **cảnh báo rủi ro** và ô xác nhận bắt buộc
  ("Tôi hiểu các rủi ro ... và chấp nhận") — chưa tích thì không chạy và không gửi cookie. Áp dụng cả cho "Chạy lại lượt lỗi".
- **Lưu ý website chặn tự động** (`ui/notices.py`) ở Crawl Bước 1 và Automation: CAPTCHA, WAF/bot protection, giới hạn tốc độ/IP, nhận diện headless, OTP/2FA,
  dữ liệu khó lấy, robots.txt/điều khoản, giới hạn địa lý; nêu rõ hệ thống **không giải CAPTCHA/không né bảo vệ** và cách xử lý hợp lệ.
- **Automation:** khung "Automation là gì? Dùng như thế nào?" (ví dụ nhà hàng, bảng tab, luồng 4 bước) hiện sau đăng nhập cùng hướng dẫn cài Python.
- **Sửa lỗi deploy:** trang Automation trên bản deploy báo `No module named 'ui'` vì `streamlit run ui/Crawl.py` chỉ thêm `ui/` vào `sys.path`;
  thêm `ENV PYTHONPATH=/app` trong `Dockerfile.ui`, các trang tự thêm thư mục gốc, và test chặn tái diễn.

## Giữ URL ảnh khi làm sạch + RUNNER_AI_MODEL — 2026-09-19
- `clean_html(html, base_url)` chuyển mỗi `<img>` thành `![alt](url tuyệt đối)` đúng vị trí trong trang (ưu tiên `data-src`/lazy-load,
  rồi `srcset`, rồi `src`; bỏ ảnh `data:`/`blob:` và pixel 1-2px). Trước đây `<img>` bị bỏ hết nên field ảnh (`image_fields`) luôn rỗng.
  Vẫn là xử lý HTML thuần, không OCR. Lưu ý: URL ảnh nay nằm trong markdown nên `content_hash` đổi khi URL ảnh đổi (vd. CDN token).
- `RUNNER_AI_MODEL` (tùy chọn): model riêng cho Runner Describe; trống = dùng chung `AI_MODEL`.

## Tuân thủ skill GreenNode AgentBase + phản hồi người dùng — 2026-09-19

- **robots.txt luôn được kiểm tra** với mọi engine: `PlaywrightFetcher` mặc định `HttpRobotsChecker`
  (trước đây `AllowAllRobotsChecker` nên `FETCH_RESPECT_ROBOTS_TXT=true` vô tác dụng); bản sao theo
  cookie giữ nguyên checker + rate limit.
- **Bật/tắt bỏ qua robots.txt theo từng lượt kéo**: checkbox + lý do bắt buộc ở màn Chạy crawl
  (`ignore_robots`, `ignore_robots_reason` trong `POST /crawl`); chỉ áp dụng cho đúng domain của URL,
  ghi log WARNING mỗi lần (`OverrideRobotsChecker`). `FETCH_RESPECT_ROBOTS_TXT=false` toàn cục vẫn còn, kèm cảnh báo khi khởi động.
- **Phản hồi/báo lỗi tự do ở mọi màn hình** (crawl, Runner, admin): `POST /feedback` -> AI_DEBUG phân loại
  (`src/ai/feedback_triage.py`). AI kết luận *không phải lỗi* với confidence >= 0.75 thì trả lời thẳng người dùng;
  là lỗi / confidence thấp / AI hỏng thì chuyển admin kèm trace (audit theo `request_id`, các lần crawl lỗi gần nhất,
  chẩn đoán AI) — xem tab "Phản hồi AI đã chuyển admin" ở trang Admin. Cookie/token bị che trước khi gửi AI/lưu.
- Fetcher: bỏ dò API đoán mò (`/data/corporateaz`...) và `sleep(8)` cố định (đổi sang chờ `networkidle`), escape HTML khi
  chèn bảng API; `FETCH_ENGINE=playwright|hybrid|httpx` (mặc định playwright).
- AI extract: trang dài chia đoạn ≤ 8000 ký tự thay vì cắt bỏ phần đuôi.
- Bật lại cache selector cho trang 1-record (chỉ ghi khi AI trả đúng 1 bản ghi, chỉ áp khi mọi field còn lại đều khớp).
- Bulk: nhả khóa tuần tự khi tạm dừng (sửa test treo). UI: bỏ ghi file lên đĩa server theo đường dẫn người dùng nhập (chỉ tải về).
- Skill AgentBase: `Dockerfile` gốc dùng cổng 8080; CI chạy test trước khi build/push image; xóa `scripts/create_admin_direct.py`
  (hardcode mật khẩu); chuẩn hóa LF + `.gitattributes`; gộp reset/quên mật khẩu Runner.
- Đăng nhập admin chung: tài khoản admin Runner dùng cho cả `/admin/*` (Crawl) và `/runner/*` (Automation); `.env` Basic là dự phòng
  (chỉ Crawl). Trang đổi tên: `ui/Crawl.py` (Crawl), `pages/2_Automation.py`, `pages/3_Admin.py` (tab riêng "Crawl · …" và "Automation · …").
  Entry Streamlit mới: `streamlit run ui/Crawl.py`.
- Kiểm chứng thật: Runner trên Postgres 16 (ghi -> kết nối lại -> dữ liệu, đăng nhập, reset mật khẩu còn nguyên) và 35 test
  PostgresStorage đạt. So sánh engine trên finance.vietstock.vn/doanh-nghiep-a-z: httpx/hybrid chỉ lấy 3 dòng bảng, playwright lấy 310 —
  giữ `FETCH_ENGINE=playwright` mặc định; hybrid không phù hợp site JS nặng có HTML lớn.
- Test: 588 pass (sửa fake Playwright page, timeout/mocks UI, test nhiều bảng).

## Runner integration — cập nhật 2026-09-17

### Bổ sung kiểm chứng phase 26–27: giữ thao tác nhập xen giữa các frame
- Sửa bộ lọc fill trong từng document có thể bỏ lần nhập tiếp theo vào cùng ô,
  khi giữa hai lần nhập có thao tác ở frame khác. JS gửi sự kiện cấu trúc về bộ
  nhận chung; chỉ gộp fill liên tiếp cùng locator/screen tại đó, không đọc giá trị.
- Pause/resume, chuyển screen và thao tác xen giữa kết thúc chuỗi gõ. Gõ tiếp
  trong chuỗi hiện tại không làm tăng số event hoặc báo dropped khi đạt giới hạn.
- Bổ sung regression về thứ tự qua scope, pause/screen, giới hạn; đối chiếu JSON
  và workbook xuất cùng sự kiện sau khi gộp. Cập nhật quyết định trong thiết kế V2.
- **562 test toàn bộ suite offline pass**, một warning Starlette/AnyIO có sẵn;
  bao gồm bản sửa nút input trước đó. Chưa browser/AI runtime thật; không đổi crawler.

### Bổ sung kiểm chứng phase 26–27: không bỏ sót nút input
- Sửa Recorder bỏ qua click trên input type button/submit/reset/image. Ghi action
  click bằng locator cấu trúc, không đọc label/value/src; vẫn bỏ click của ô nhập,
  checkbox/radio/file để không tạo thao tác trùng với input/change.
- DOM test kiểm tra trang chính và shadow mở, dedupe giữa các root, bỏ event giả.
  Test compiler kiểm tra giữ hai lần bấm thành hai steps inactive riêng, không
  tạo cột dữ liệu cho nút bấm hoặc sinh testcase/settings.
- Kiểm chứng: **41 test liên quan pass, 518 deselected**; một warning Starlette/AnyIO
  có sẵn. Baseline toàn bộ suite trước bản sửa: 558 pass; chưa chạy lại toàn bộ
  suite hoặc browser thật cho bản sửa này. Không thay kiến trúc hay code crawler.

### Phase 27: AI biên dịch recording theo contract Runner
- Chốt lại phạm vi theo người dùng: người dùng thao tác Inspector/Recorder; AI
  chuẩn hóa flow thành steps, không tự điều hướng/thực thi nghiệp vụ.
- Thêm JSON recording được kiểm tra theo schema đóng; UI yêu cầu rà metadata trước
  khi gửi endpoint /runner/authoring/recording có đăng nhập. Không persist trace;
  audit chỉ event/user/time, response no-store; đổi đầu vào hoặc logout xóa draft.
- AI đặt tên step và đề xuất gộp; compiler đối chiếu mọi event đúng một lần/đúng
  thứ tự/screen, ràng buộc action/value_source/locator/wait/read_method theo Runner.
  Gộp fill liên tiếp hoặc Ant Design có bằng chứng thành select_antd thay vì chép click.
- Selector lấy từ recording, không từ AI. Thiếu bằng chứng thì review/placeholder;
  không tự đoán group, account, prefill hoặc expected. Sheet review ghi event nguồn.
  Steps inactive, testcase chỉ header, settings vẫn qua prepare và duyệt từng mục.
- Compose giữ review/mapping nguồn từng draft; prepare sao chép review vào sheet
  draft_review mới, không ghi đè ghi chú có sẵn hoặc testcase của người dùng.
- Bằng chứng widget chỉ enum và locator liên quan, không class string/text/value/file.
  Ant Design trong iframe/shadow chưa gộp tự động; nhóm lặp cần rà soát thủ công.
- Kiểm chứng cuối phase 26–27: **558 test offline pass**, một warning deprecation
  Starlette/AnyIO có sẵn. AI HTTP/browser giả lập và DOM tổng hợp; chưa nghiệm thu
  model/website thật. Docker tiếp tục tạm để lại theo yêu cầu người dùng.

### Phase 26: recorder có scope và điều khiển bổ sung
- Ghi iframe/shadow DOM mở bằng scope cấu trúc; frame ancestry lấy local, không URL.
  Dedupe event qua shadow root, bỏ event giả/detached frame, không thu giá trị/file.
- Thêm check/uncheck/upload; upload chỉ sinh header để người dùng tự nhập đường dẫn.
  Executor bổ sung uncheck/upload và resolve scope cho thao tác/wait/đọc input.
  Không đổi đường thực thi crawler, không sửa CLAUDE.md.
- Test offline có DOM JavaScript tổng hợp, scope lồng nhau, chặn upload credential,
  và workbook inactive/header-only. Browser/website thật chưa nghiệm thu.

### Phase 23: chốt roadmap MVP và bằng chứng nghiệm thu
- Thêm docs/RUNNER_ROADMAP.md đối chiếu bốn giai đoạn MVP trong V2 với các
  phase triển khai, phạm vi chốt và tiêu chí hoàn tất phase 23–25.
- Thêm docs/RUNNER_UAT_RESULTS.md ghi rõ các kiểm tra chưa chạy; không coi test
  offline là bằng chứng Docker/GreenNode/browser thật đã đạt.
- Phase 23 hoàn tất tài liệu. Baseline gần nhất: 510 test offline pass;
  không chạy lại suite chỉ cho thay đổi tài liệu.

### Phase 24: kiểm chứng triển khai — đang thực hiện
- Rà soát Dockerfile API/UI, compose và nginx. UI /health chỉ là liveness nginx;
  thêm /ready proxy tới health của Streamlit với connect/read timeout 2/5 giây.
  Đã kiểm chứng UI container: health/ready/trang gốc 200; chỉ nginx thì ready 502.
- Thêm prepare_container_context.py: source được chọn rõ, không copy workspace,
  không dotenv/state/workbook; từ chối symlink/junction, chuẩn hóa LF, manifest SHA-256.
  Context 58 file có các module workbook dùng chung mà API import khi có yêu cầu.
- Thêm container_probe.py và hướng dẫn RUNNER_CONTAINER_SMOKE.md. Probe chỉ chạy
  khi đánh dấu container thử, không dùng secret hoặc mạng ngoài; có ca workbook
  chỉ header, phân quyền Runner, SQLite persistence và Chromium HTML tổng hợp.
- Docker local 29.8.0, cấu hình client rỗng riêng. Image UI build thành công;
  API build gián đoạn khi Docker daemon không còn truy cập được lúc tải Chromium;
  chưa xác nhận image hoàn tất. Không dùng compose mặc định hoặc mount dữ liệu thật.
- Regression: **513 test offline pass**, một warning Starlette/AnyIO có sẵn;
  3 test context chạy lại đạt sau cập nhật danh sách source.
- Checklist triển khai/UAT và nơi ghi bằng chứng đã có. Phase 24–25 chưa hoàn tất.

### Phase 25: diễn tập nghiệm thu offline — chưa UAT thật
- Theo yêu cầu người dùng, tạm để lại Docker khi engine không còn hoạt động;
  tiếp tục phần offline, không đánh dấu phase 24 hoàn tất.
- Thêm hai ca test_mvp_restart dùng lifecycle FastAPI đầy đủ, SQLite tạm đóng/mở
  lại, fetch/AI giả lập và clock Runner cố định. Xác minh dữ liệu crawl/dedup,
  kết quả và summary Runner còn sau restart, ownership và login vẫn có hiệu lực.
- Xác minh báo lỗi TypeError giữ metadata qua restart mà không chứa exception/query
  riêng tư; lỗi crawl không làm mất trạng thái run, run đang chạy không bị claim lại.
- Hai ca mới pass; đây là diễn tập offline, không thay thế container volume,
  browser/executor thật hoặc UAT GreenNode. Không đổi code crawler/CLAUDE.md.
- Regression cuối lượt: **515 test offline pass**, một warning Starlette/AnyIO
  có sẵn. Phase 25 chỉ hoàn tất phần diễn tập offline, còn nghiệm thu thực tế.

### Phase 22: chẩn đoán journal local chỉ đọc
- Thêm `--journal-status`, tùy chọn `--run-id`: chạy trước luồng token/agent/API,
  không tạo state/lock, không recover, resend, cleanup hoặc thực thi testcase.
- Dùng chung validator với agent; phân loại JSON/schema/identity/timestamp/result
  sai, quá lớn, ghi dở hoặc không đọc được. Không đọc nội dung pending, file có
  tên credential hoặc symlink; không in payload, đường dẫn hay tên file thô.
- Báo cáo JSON giới hạn 1.000 mục, có cờ truncated và reference từ hash tên file.
  Đây là snapshot không nguyên tử; agent đang ghi có thể làm kết quả thay đổi.
  Mã thoát 0 là OK, 2 là cần kiểm tra. UI và hướng dẫn local có lệnh sử dụng.
- Kiểm chứng: **510 test pass** offline; một warning Starlette/AnyIO có sẵn.
  Bao phủ giới hạn quét, phân loại lỗi, không sửa file, không đọc pending/file
  bị loại và CLI không khởi tạo agent/token/HTTP. Chưa chạy UAT thật.

### Phase 21: cô lập journal hỏng và ghi bền vững
- Agent kiểm tra từng journal: giới hạn 128 KB, JSON/schema/state, run_id phải
  khớp tên file, timestamp hữu hạn và payload metrics/preflight theo contract đóng.
  Journal sai/unreadable được giữ nguyên, không forward dữ liệu tùy ý hoặc cleanup
  artifact của run khác. Các mục hợp lệ vẫn recover/resend/retention bình thường.
- Lỗi ghi ACK, recovery hoặc retention được cô lập theo mục; cảnh báo chỉ mã giai
  đoạn, không in raw JSON/exception. Mỗi giai đoạn cảnh báo một lần trong process.
- Ghi journal dùng file .pending tạo exclusive, flush/fsync trước atomic replace.
  Không ghi đè pending có sẵn. Pending dở chặn replay/cleanup/resend của đúng run
  để giữ bằng chứng, không chặn các run khác. Không tự suy luận trạng thái từ file dở.
- Cleanup không ghi lại journal chưa đổi. --resend-run dùng cùng validator; không
  sửa journal thủ công hoặc xóa dấu vết để ép chạy lại. CLAUDE.md/crawler không đổi.
- Kiểm chứng: **505 test pass** offline, một deprecation warning Starlette/AnyIO
  có sẵn. Bao phủ journal JSON/schema/size/timestamp sai, pending dở, chặn replay,
  giữ artifact, identity chống xóa nhầm và tiếp tục gửi mục tốt sau lỗi ghi ACK.

### Phase 20: kết quả nhận muộn sau mất kết nối
- Sửa trường hợp backend đã đánh dấu LOST nhưng agent hoàn tất và gửi kết quả sau đó:
  lưu late_result metadata đầu tiên, gồm metrics/status tính từ metrics/preflight và
  thời điểm nhận. Không đổi LOST, mốc mất theo dõi, hạn lưu, thông báo hoặc deleted_at.
- UI phân biệt kết quả agent báo muộn với trạng thái backend; summary JSON có cùng
  metadata. Agent khác/user khác không được gửi/đọc; gửi trùng không đổi kết quả
  đầu tiên hoặc tạo audit trùng. Run chưa từng được claim không nhận late_result.
- Artifact đã xóa không được tạo lại. Không claim/replay testcase; audit riêng
  RUN_LATE_RESULT_RECEIVED_NO_REPLAY, chỉ lưu event/user/run/time.
- Thêm --resend-run cho agent: người dùng chủ động gửi lại metrics/preflight từ
  journal PENDING_RESULT/REPORTED bằng đúng agent. Không recover/cleanup/claim/run;
  khóa single-instance vẫn áp dụng. Journal sai schema/giá trị bị chặn trước HTTP.
  Dùng sau nâng API để khôi phục metadata mà phiên bản cũ từng ACK nhưng bỏ qua.
- Không đọc/sửa credential, settings hoặc testcase, không thay CLAUDE.md hay crawler.
- Kiểm chứng cuối phase 20: **492 test pass** offline, một deprecation warning
  Starlette/AnyIO có sẵn; gồm quyền sở hữu, idempotence, retention, không phục hồi
  artifact đã xóa, gửi lại journal và UI phân biệt LOST/kết quả nhận muộn.

### Phase 19: chạy thử một step có xác nhận local
- Thêm try_step_runner.py: chọn dòng workbook, người dùng tự điều hướng, chọn tab,
  review phần tử highlight và gõ EXECUTE <row>. Chỉ thực hiện một thao tác thật;
  không tự chạy thử từ AI/UI, không bật active, không sửa source/settings/testcase.
- Hỗ trợ fill/click/check/select trực tiếp và wait CSS cấu trúc. Các bước group,
  force/prefill, post-action wait, đọc kết quả hoặc action phức tạp dùng Runner đầy đủ.
  Fill/select lấy giá trị thử qua đầu vào ẩn, từ chối fallback echo; không lấy giá trị
  testcase hoặc đọc file credential. Giá trị không ghi vào report/log của công cụ.
- Dùng builder locator của runner; sau xác nhận kiểm tra hash workbook và identity,
  uniqueness/visibility, thực thi trên chính ElementHandle đã review. Không resolve
  lại selector để thao tác trên phần tử thay thế.
- Persist EXECUTION_STARTED trước side effect; lỗi sau khi bắt đầu là OUTCOME_UNKNOWN,
  không retry. ACTION_COMPLETED không phải PASS testcase. Report JSON chỉ metadata,
  không ghi đè report có sẵn, cập nhật bằng atomic replace; restart không replay.
- UI/hướng dẫn/V2 có luồng sử dụng và phân biệt với Inspector chỉ đọc. Không tác động
  queue/scheduler crawler, không thay CLAUDE.md. Browser/UAT thật chưa được kiểm chứng.
- Kiểm chứng: **481 test pass** offline (20 test mới), một deprecation warning
  Starlette/AnyIO có sẵn. Bao phủ từng action, đúng một attempt, hủy, source/target đổi,
  locator thiếu/ẩn/trùng, lỗi ghi intent, kết quả không xác định và từ chối action phức tạp.

### Phase 18: Record nhiều màn hình, pause và đánh dấu wait/read
- Ctrl+Alt+N tạo screen kế tiếp, Ctrl+Alt+P pause/resume ghi trong phiên local;
  không lấy URL hoặc tự suy luận chuyển màn hình. Hiển thị trạng thái cố định
  ở góc browser, tối đa 100 screen/1000 event, từ chối control payload ngoài enum.
- Ctrl+Alt+W ghi wait theo CSS cấu trúc; Ctrl+Alt+A đánh dấu read_result_single
  cho input/textarea/select với expected header trống. Không đọc input value,
  text hoặc expected; không chạy thao tác mới trên website. Chặn read ở screen
  thứ hai và loại password/file/checkbox/radio/hidden khỏi hotkey read.
- Export giữ step inactive, không testcase/settings. Lỗi dựng workbook không
  để lại output rỗng. Inspector chỉ kiểm tra count/visibility của wait cấu trúc;
  các wait command phức tạp vẫn cần kiểm tra thủ công, không được execute bởi Inspector.
- Cập nhật UI, hướng dẫn và thiết kế V2; CLAUDE.md giữ nguyên. Browser/hotkey thật
  cần người vận hành kiểm chứng, test hiện dùng browser giả lập.
- Kiểm chứng: **461 test pass** offline, một deprecation warning Starlette/AnyIO
  có sẵn; bao phủ control/screen/pause, read header-only, từ chối read khác screen,
  không để lại output rỗng và kiểm tra structural wait không thực thi lệnh.

### Phase 17: gen nhóm lặp và header nhiều khối kết quả
- Describe hỗ trợ group được người dùng yêu cầu, liền mạch trên một màn hình và
  dùng đúng action của run_repeat_group. Không sinh giá trị danh sách; người dùng
  tự nhập các giá trị phân cách bằng dấu chấm phẩy trong testcase.
- Người dùng chọn 1–100 khối kết quả ở UI; Python sinh đủ expected_<field>_<index>
  cho read_result/read_result_group. Đây chỉ là header trống, không thay số lần
  thực thi hoặc setting. Chuỗi header sai/thiếu block, xung đột input/expected,
  quá giới hạn cột Excel bị từ chối; compose/prepare giữ đủ các header đã chọn.
- Preflight chặn INVALID_REPEAT_GROUP khi action/value_source không được dispatcher
  nhóm lặp hỗ trợ hoặc nhóm không có testcase-valued step, tránh bỏ qua âm thầm.
- Runner resolve từng placeholder local sau tách danh sách nhóm lặp, register vào
  redactor như luồng step thường; thiếu biến báo lỗi, không truyền literal placeholder
  xuống browser. Kiểm thử chỉ dùng giá trị giả, không đọc credential thật.
- Suite đầy đủ sau thay đổi gen/resolve: **456 test pass**, một deprecation warning
  Starlette/AnyIO. Sau bổ sung preflight group, chạy lại nhóm repeat/preflight/
  compose/workbook generation: **44 pass, 413 deselected**.

### Phase 13: discovery cấu trúc local và AI gắn locator
- Thêm discover_runner.py: người dùng tự điều hướng/đăng nhập, chọn tab, highlight
  candidate theo ID và xác nhận EXPORT. Chỉ xuất tag chuẩn và CSS theo vị trí;
  không thu text, URL, input value, attribute hoặc DOM thô. Tối đa 100 candidate/màn hình.
- API/UI discovery yêu cầu đăng nhập và xác nhận rà soát; dùng AI runtime opt-in
  hiện có. AI chỉ được chọn ID người dùng nêu trong mô tả, kiểm tra action/tag,
  tham chiếu cột và một màn hình/snapshot. Locator chỉ lấy từ snapshot hợp lệ.
- Nháp có đủ cột steps inactive và header testcases; không sinh settings, testcase,
  dữ liệu input/expected. Không chạy browser ở server, không tạo run hay lưu snapshot
  trong DB/audit. Giới hạn hai yêu cầu AI đồng thời dùng chung Describe.

### Phase 14: AI đề xuất repair, xác nhận lại tại browser local
- AI chỉ trả candidate ID và reason enum; Python gắn hash snapshot, action/read_method.
  UI cho tải proposal JSON, không upload workbook hoặc artifact lỗi.
- repair_runner.py nhận --snapshot/--proposal, đối chiếu hash và action, highlight
  phần tử trên màn hình người dùng tự mở. Phải xác nhận EXPORT, kiểm tra lại
  identity/visibility/uniqueness và hash workbook mới xuất bản sao inactive.
- Giữ nguyên source, testcase và settings; không ghi đè output hoặc chạy lại UAT.
  Snapshot/proposal không đúng schema, candidate chưa chỉ định hoặc sai tag bị từ chối.
- Quyết định kiến trúc: dùng adapter Playwright local với snapshot cấu trúc thay
  MCP raw DOM; khám phá/repair có người duyệt, không tự điều hướng hoặc thao tác UAT.
  Không suy đoán ngữ nghĩa từ cấu trúc; iframe/shadow DOM và action phức tạp cần
  cấu hình thủ công. Tài liệu V2 và hướng dẫn phản ánh phạm vi này.
- Kiểm chứng phase 13–14 ban đầu: 43 test discovery/planner/UI pass offline.

### Phase 15: ghép nhiều màn hình và kiểm chứng luồng chuẩn bị
- Thêm compose_runner.py ghép 1–20 nháp theo thứ tự tường minh, tối đa 2000 steps;
  đủ cột steps/header testcases, không sinh testcase hoặc settings. Source giữ nguyên,
  không ghi đè output, từ chối file đã có testcase/settings để tránh bỏ mất dữ liệu.
- Từ chối tên step trùng, screen bị xen kẽ, nhiều result screen, xung đột cột input/
  expected và step active. Dùng prepare_runner.py sau ghép để giữ dữ liệu/config hiện có;
  setting chỉ thay đổi khi người dùng duyệt từng đề xuất.
- Luồng kiểm thử discovery → ghép nhiều màn hình → giữ dữ liệu user/settings →
  preflight chặn đến khi user tự activate. Bổ sung test UI xác nhận gửi AI và logout.
- Toàn bộ **448 test pass** offline, 1 cảnh báo deprecation Starlette/AnyIO có sẵn.
  Bao gồm crawler và Runner; không gọi mạng/AI/credential hoặc browser UAT thật.

### Phase 16: hướng dẫn nghiệm thu và đóng gói
- Thêm docs/RUNNER_ACCEPTANCE.md: trạng thái từng phần, thứ tự nâng API/UI/agent,
  điều kiện lưu trữ/single process, kiểm thử UAT người vận hành tự chạy và cách báo
  kết quả chỉ bằng mã/số đếm đã che dữ liệu. Chưa thực hiện deployment thật.
- Dockerfile API tổng hợp cài requirements-auth để bật Runner có Argon2/openpyxl
  như Dockerfile.api. Docker context loại workbook/config local, state công cụ dev
  và các tên snapshot/proposal mặc định. Không đổi config runtime hoặc credential.
- Docker build, PostgreSQL, GreenNode và UAT thật chưa được xác nhận. Không coi
  test offline là nghiệm thu vận hành; CLAUDE.md giữ nguyên.

### Phase 12: preflight bắt buộc trước executor và chẩn đoán trên UI
- Executor local chạy preflight trước khi import runner/browser hoặc resolve
  môi trường. Workbook lỗi tạo summary ERROR và preflight.json, không chạy UAT.
  Kiểm tra thêm action/locator_type/value_source hợp lệ và URL HTTP(S).
- Report chỉ có status, số lượng active, mã lỗi cố định, sheet và số dòng; giới hạn
  100 lỗi/100 cảnh báo và cờ truncated. Schema đóng từ chối message/code tùy ý.
- Agent gửi metadata cùng metrics, giữ trong journal khi cần gửi lại kết quả;
  không replay testcase. Workbook lỗi ngay ở validator agent có mã INVALID_WORKBOOK.
- API lưu metadata theo quyền owner/admin, bổ sung vào summary JSON; report bị chặn
  không thể dẫn đến PASSED kể cả agent gửi nhầm số passed. Run cũ/agent cũ vẫn nhận
  metrics như trước. Cần nâng API trước agent để nhận contract bổ sung.
- UI lịch sử chỉ ra run bị chặn trước browser và nơi cần sửa workbook local.
  Không tự sửa settings/locator, sinh testcase hoặc bật active; qua preflight tĩnh
  không có nghĩa locator/đăng nhập/assertion đã được kiểm chứng trên browser thật.

- Kiểm thử offline: toàn bộ 417 test pass; chạy lại nhóm preflight sau khi bổ sung
  tình huống gửi lại kết quả: 12 pass. Có 1 cảnh báo deprecation Starlette/AnyIO
  đã tồn tại; chưa chạy browser/UAT, AI hoặc PostgreSQL thật.

## Runner — thêm reset mật khẩu + hướng dẫn tạo admin qua Postgres — 2026-09-18

### Đã thêm
- Admin Runner đặt lại mật khẩu cho user quên mật khẩu (`POST
  /runner/users/{id}/reset-password`, nút trong tab "Quản trị" của UI Runner)
  — không có luồng tự phục vụ qua email (chưa có hệ thống mail), admin đặt
  trực tiếp rồi tự báo lại cho user qua kênh khác.
- `scripts/create_runner_admin.py` nhận thêm `--postgres-dsn` — chạy được từ
  xa để bootstrap admin khi deploy Runner với `RUNNER_DATABASE_URL` trỏ
  Postgres, không cần shell vào container đang chạy trên GreenNode.
- Hướng dẫn cụ thể trong `docs/RUNNER_SETUP.md` mục "Tạo admin khi deploy
  (Postgres)".

### Đã sửa
- Sửa lỗi Docker `deploy/start-ui.sh: 4: set: Illegal option -` — file bị
  Windows git tự đổi LF thành CRLF lúc checkout do chưa có `.gitattributes`,
  khiến container UI crash loop ngay lúc start. Thêm `.gitattributes` ép LF
  cho `*.sh`/`Dockerfile*`/`*.conf`.

## Crawler — merge origin/main (audit Kiên) vào develop — 2026-09-17

### Hợp nhất 2 nhánh làm việc song song
- Merge `origin/main` (audit độc lập của Kiên, 2026-09-16) vào `develop` — 28 file
  conflict, chủ yếu do 2 nhánh cùng sửa `src/pipeline.py`/`src/ai/greennode_client.py`
  theo 2 hướng khác nhau cùng lúc (multi-record extraction bên main, Postgres/admin-auth/
  ảnh/cookie bên develop). Giữ đủ tính năng cả 2 bên, không tính năng nào bị bỏ sót.
- Port từ audit Kiên vào kiến trúc multi-record hiện có: field-name so khớp không phân
  biệt hoa/thường trong `_to_records()` (bug tái xuất hiện khi Kiên viết lại hàm parse
  AI response, đã có ở bản cũ nhưng bị rơi mất khi chuyển sang array-based).
- Sửa bug `FETCH_RESPECT_ROBOTS_TXT` được đọc vào `Settings` nhưng chưa từng được dùng ở
  `_build_default_app()` — set `false` trong `.env` trước đây không có tác dụng gì,
  fetcher luôn fail-closed theo `HttpRobotsChecker()` mặc định.
- Thêm export XLSX (nút "⬇ Tải XLSX trang hiện tại") và BOM UTF-8 cho CSV export (Excel
  mở tiếng Việt không lỗi font) ở Bước 4 — theo audit Kiên, giữ nguyên phần chống CSV
  injection (`text_cell`) đã có trên `develop`.
- Thêm test multi-record cho `run_crawl_job()`/`run_file_crawl_job()` (chưa có test nào
  xác nhận trực tiếp việc lưu/ghi NHIỀU record từ 1 lần gọi AI, dù kiến trúc đã hỗ trợ).
- Phát hiện (chưa sửa — cần xác nhận thêm): `run_file_crawl_job()` ghi record ra file ở
  dạng flatten (field thành cột riêng, phục vụ export CSV/XLSX/Parquet dễ hơn) nhưng
  KHÔNG còn lưu `evidence` — khác với luồng DB (`run_crawl_job()`) vẫn lưu đủ evidence.
  Có thể là đánh đổi có chủ đích cho export dạng bảng; cần người quyết định xác nhận.
- Cập nhật `CLAUDE.md` ghi nhận module Runner (`src/runner/`) là module độc lập trong
  cùng repo, không dùng chung code/schema với luồng crawl chính.
- **229 test pass** (thêm test mới sau merge, xem `tests/test_pipeline.py`,
  `tests/ai/test_greennode_client.py`, `tests/clean/test_html_cleaner.py`); chưa build
  Docker/chạy Postgres thật để xác nhận lại (giới hạn mạng của môi trường làm việc).

## Crawler — cập nhật 2026-09-17

### Phase 11a: quản lý lịch
- Bước 5 có tạm dừng/bật lại và sửa chu kỳ hoặc giờ chạy theo múi giờ; giữ nguyên
  source/dataset/file/cấu hình bảng và lịch sử chạy. Trạng thái/timing lưu vào DB,
  được nạp lại sau restart. UI hiển thị trạng thái bật, timezone và lần chạy kế tiếp.
- Validate trigger trước khi lưu, từ chối interval không dương/cron không hợp lệ;
  tránh để lại lịch lỗi sau đăng ký thất bại. Update API chỉ cho đổi enabled/timing.
- Job đã vào hàng chờ kiểm tra enabled trước khi crawl. Tạm dừng không ngắt lượt
  đã bắt đầu. Mỗi lịch tối đa một instance; coalesce các lượt đến hạn cùng lúc.

### Phase 11b: tạm dừng đợt crawl kéo lâu
- UI kéo nhiều lượt/bảng chuyển sang task nền, theo dõi tiến độ mỗi 2 giây và có
  Tạm dừng / Tiếp tục / Dừng hẳn. Tác dụng ở ranh giới giữa các lượt, sau request
  đang xử lý; không ngắt cưỡng bức HTTP/AI hay rollback record đã lưu.
- Tạm dừng nhả khóa bulk cho crawler khác/lịch chạy tiếp. Khi tiếp tục, refresh
  dedup trước khi kéo trang kế tiếp, tránh ghi lặp dữ liệu được thêm trong lúc chờ.
- Batch tối đa 20 nguồn cùng schema/đích; các nguồn dùng chung dataset mới đúng thứ tự.
  Hai worker thread, tối đa 8 task chưa kết thúc. Điều khiển bằng mã riêng cho phiên,
  backend chỉ giữ hash mã; task/cookie chỉ ở RAM, không ghi secret xuống DB/audit.
- Sau 15 phút pause tự dừng để giải phóng phiên; kết quả task giữ tối đa 1 giờ hoặc
  bị loại sớm khi đủ bộ đệm. Restart backend không replay task; record/audit đã lưu
  còn nguyên. Vẫn yêu cầu một backend process, không có queue/checkpoint bền vững.
- Luồng một trang, preview và retry chọn lọc hiện vẫn gọi đồng bộ; nút tạm dừng áp
  dụng đợt nhiều lượt/bảng khởi chạy từ Chạy crawl. Không áp dụng cho Runner/UAT.
- Kiểm chứng chung phase 11a–11b: **407 test pass** offline (17 test mới), một
  deprecation warning Starlette/AnyIO. Kiểm tra pause/resume/cancel, quyền điều
  khiển, queue đầy, pause timeout, restart, dedup sau pause, batch cùng dataset,
  lịch giữ trạng thái/timing qua restart, validate/rollback và thao tác UI.
  Chưa kiểm chứng PostgreSQL, HTTP/AI thật hoặc deployment; không đọc secret thật.

## Crawler — cập nhật 2026-09-16

### Phase 10: xuất toàn bộ dataset
- Bước 4 thêm chuẩn bị/tải CSV toàn bộ, tách khỏi CSV trang hiện tại. Có lọc theo
  ngày crawl hoặc ngày dữ liệu `as_of`, hai đầu bao gồm, tính theo UTC. Record
  thiếu as_of bị loại khi lọc theo ngày dữ liệu; không áp bộ lọc vào bảng đang xem.
- API stream CSV UTF-8 BOM theo từng nhóm 500 record, không tạo file tạm. SQLite
  và Postgres có truy vấn keyset (crawled_at, record_id) và index tương ứng; giới
  hạn timestamp tại lúc bắt đầu xuất, tính cả record bằng mốc đó. Không phải
  transaction snapshot; thao tác backdate hoặc clock lùi trong lúc xuất chưa được đảm bảo.
- Metadata và cột dữ liệu có prefix riêng, tránh ghi đè khi trùng tên; CSV toàn
  bộ theo schema dataset. Chuỗi giống công thức được xuất dạng text trong cả
  CSV toàn bộ và CSV trang hiện tại, không sửa dữ liệu DB.
- Audit lưu dataset, mốc xuất, bộ lọc, số record đã phát và trạng thái stream;
  không lưu nội dung record. File chuẩn bị nằm trong phiên UI, có nút xóa;
  đổi dataset/bộ lọc không hiển thị nhầm file cũ.
- Backend dùng bộ nhớ theo trang; UI vẫn tải trọn file vào RAM. Dataset rất lớn
  nên tải trực tiếp endpoint export.csv bằng HTTP client có hỗ trợ streaming.
- Kiểm chứng: **390 test pass** offline (9 test mới), một deprecation warning
  Starlette/AnyIO. Bao phủ trên 1000 record, timestamp trùng mốc xuất, keyset khi
  append, lọc UTC/as_of thiếu, Unicode/CSV/formula, stream bị ngắt và UI đổi bộ lọc.
  PostgreSQL và deploy thực tế chưa kiểm chứng; không truy cập secret thật.

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
