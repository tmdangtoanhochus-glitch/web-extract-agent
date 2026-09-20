# BRD — Nền tảng thu thập & quản lý dữ liệu web (Web Data Puller) + Automation

| | |
|---|---|
| **Dự án** | Web Data Extraction & Management Platform (Crawl · Automation · Admin) |
| **Đội** | MSB Team 56 — Cuộc thi AI Hackathon |
| **Phiên bản tài liệu** | 1.0 — 19/09/2026 |
| **Trạng thái sản phẩm** | Đã triển khai lên GreenNode AgentBase (UI + API), dùng Postgres GreenNode RDS |
| **Đối tượng đọc** | Đồng nghiệp, giám khảo, người vận hành, tester |

> **Ghi chú độ tin cậy.** Mỗi yêu cầu có cột *Trạng thái*: **Đạt** = đã có code, có test tự động (676 test) và/hoặc đã kiểm chứng trên bản deploy;
> **Đạt (offline)** = có code và test tự động nhưng chưa chạy với hạ tầng/AI thật; **Chưa UAT** = cần người dùng thật nghiệm thu; **Kế hoạch** = chưa làm.

---

## 1. Bối cảnh và mục tiêu

**Vấn đề.** Người dùng nghiệp vụ (không biết lập trình) thường phải sao chép dữ liệu từ website vào Excel thủ công: chậm, dễ sai, khó lặp lại.
Đội kiểm thử cũng tốn thời gian viết script tự động hóa thao tác trên trình duyệt.

**Giải pháp.** Một ứng dụng web giúp người dùng:
1. **Crawl:** nhập URL + mô tả field cần lấy bằng ngôn ngữ tự nhiên → hệ thống tự tải trang, làm sạch, dùng AI trích xuất có bằng chứng và độ tin cậy → lưu vào cơ sở dữ liệu hoặc file.
2. **Automation:** mô tả hoặc ghi lại thao tác trên một trang web → AI chuẩn hóa thành testcase → chạy tự động trên máy người dùng.
3. **Admin:** quản trị chung cho cả hai (lỗi, phản hồi, tài khoản).

**Mục tiêu kinh doanh**

| Mã | Mục tiêu | Chỉ số thành công |
|---|---|---|
| BG-01 | Giảm thời gian thu thập dữ liệu web thủ công | Người dùng nghiệp vụ lấy được dữ liệu trong ≤ 5 phút, không viết code |
| BG-02 | Dữ liệu đáng tin cậy, kiểm chứng được | Mỗi giá trị có bằng chứng (evidence) và độ tin cậy; giá trị nghi ngờ được gắn cờ "cần xem lại" |
| BG-03 | Tuân thủ và an toàn | Luôn kiểm tra robots.txt; không lưu cookie/mật khẩu người dùng; không giải CAPTCHA |
| BG-04 | Giảm công sức kiểm thử giao diện | Tạo testcase từ mô tả hoặc thao tác thật, chạy lặp lại được |
| BG-05 | Triển khai được trên hạ tầng GreenNode | Chạy ổn định trên AgentBase, dữ liệu bền vững trên Postgres |

## 2. Phạm vi

**Trong phạm vi**
- Crawl 1 trang, nhiều trang (phân trang), và bảng HTML theo khoảng ngày; trích xuất nhiều bản ghi mỗi trang.
- Lưu vào DB (schema động dạng JSON) hoặc file (CSV, XLSX, Parquet, JSON); tải ảnh theo URL.
- Lịch chạy tự động; xem, xuất dữ liệu đã lưu.
- Trang cần đăng nhập: người dùng dán cookie của chính mình cho từng lượt kéo.
- Automation: Describe, Record, Inspector/Discovery/Repair (AI), agent chạy trên máy người dùng, tóm tắt kết quả.
- Quản trị: đăng nhập chung, xử lý lỗi, phản hồi người dùng, quản lý tài khoản Runner.
- Triển khai UI + API trên GreenNode AgentBase, CI kiểm thử tự động.

**Ngoài phạm vi (giai đoạn này)**
- Vượt CAPTCHA, tường bảo vệ bot hoặc các cơ chế chống tự động hóa của website.
- Chọn phần tử trực quan trên bản xem trước (visual selector), biểu đồ Data Lineage, giao diện React.
- Chạy testcase không giao diện trên server (đang chạy trên máy người dùng theo thiết kế).
- Đóng gói agent thành `.exe`/Docker cho người dùng không cài Python.
- Hàng đợi phân tán (Celery/Redis).

## 3. Người dùng và vai trò

| Vai trò | Mô tả | Nhu cầu chính |
|---|---|---|
| Người dùng nghiệp vụ | Không kỹ thuật, dùng Crawl | Lấy dữ liệu web vào DB/Excel nhanh, tin cậy |
| Kiểm thử viên (tester) | Dùng Automation | Tạo và chạy testcase giao diện lặp lại |
| Quản trị viên (admin) | Vận hành hệ thống | Xem lỗi, xử lý phản hồi, cấp tài khoản, đặt lại mật khẩu |
| Người vận hành hạ tầng | Triển khai | Deploy, cấu hình, giám sát, chi phí |

## 4. Yêu cầu nghiệp vụ (Business Requirements)

| Mã | Yêu cầu nghiệp vụ | Truy vết tới |
|---|---|---|
| BR-01 | Người dùng tự cấu hình thu thập dữ liệu bằng ngôn ngữ tự nhiên, không cần code | FR-CR-01..05 |
| BR-02 | Mọi dữ liệu trích xuất phải kiểm chứng được (bằng chứng, độ tin cậy) | FR-CR-08, FR-CR-09 |
| BR-03 | Hệ thống tôn trọng quy định của website (robots.txt, tốc độ) | FR-CR-10, NFR-SEC-02 |
| BR-04 | Cho phép lấy dữ liệu sau đăng nhập mà không lưu thông tin đăng nhập của người dùng | FR-CR-14, NFR-SEC-03 |
| BR-05 | Dữ liệu lưu bền vững, không trùng lặp, có lịch sử thay đổi | FR-CR-11..13 |
| BR-06 | Thu thập định kỳ không cần thao tác thủ công | FR-CR-18 |
| BR-07 | Tạo và chạy testcase giao diện tự động, dữ liệu nhạy cảm ở lại máy người dùng | FR-AU-01..10 |
| BR-08 | Quản trị tập trung, người dùng báo lỗi dễ và được phản hồi | FR-AD-01..06 |
| BR-09 | Triển khai và vận hành trên GreenNode | NFR-DEP-01..05 |

## 5. Yêu cầu chức năng

### 5.1 Crawl

| Mã | Yêu cầu | Ưu tiên | Trạng thái |
|---|---|---|---|
| FR-CR-01 | Nhập một hoặc nhiều URL; tạo pattern phân trang bằng `{page}` | Cao | Đạt |
| FR-CR-02 | Khai báo field cần lấy kèm mô tả tự nhiên (tên → mô tả) | Cao | Đạt |
| FR-CR-03 | Tự tải trang: `httpx` cho site tĩnh, Playwright cho site nặng JavaScript; chọn engine bằng `FETCH_ENGINE` (mặc định Playwright) | Cao | Đạt |
| FR-CR-04 | Làm sạch HTML thành Markdown TRƯỚC khi gọi AI (bỏ script, nav, footer; giữ bảng, danh sách, URL ảnh) | Cao | Đạt |
| FR-CR-05 | Ưu tiên structured data (JSON-LD, Open Graph) và cache selector theo domain trước khi gọi AI | Trung bình | Đạt |
| FR-CR-06 | AI trích xuất theo endpoint OpenAI-compatible của GreenNode MaaS; trang dài chia đoạn, không cắt bỏ phần đuôi | Cao | Đạt (offline); chất lượng model thật **Chưa UAT** |
| FR-CR-07 | Một trang có thể trả nhiều bản ghi (multi-record) | Cao | Đạt |
| FR-CR-08 | Mỗi giá trị kèm confidence và evidence (đoạn gốc) | Cao | Đạt |
| FR-CR-09 | Gắn cờ "cần xem lại" khi confidence dưới ngưỡng (`AI_CONFIDENCE_THRESHOLD`); vẫn lưu, không tự loại bỏ | Trung bình | Đạt |
| FR-CR-10 | Luôn kiểm tra robots.txt; giới hạn tốc độ theo domain; bỏ qua robots chỉ theo từng lượt kéo, bắt buộc có lý do, ghi log | Cao | Đạt |
| FR-CR-11 | Lưu DB theo schema động JSON (bảng `datasets`, `dataset_sources`, `records`), không tạo bảng riêng cho từng job | Cao | Đạt |
| FR-CR-12 | Phát hiện thay đổi bằng `content_hash`; nội dung không đổi thì không lưu lại | Cao | Đạt |
| FR-CR-13 | Không tự gộp dataset chỉ vì trùng field; người dùng xác nhận tường minh | Cao | Đạt |
| FR-CR-14 | Trang cần đăng nhập: dán cookie cho lượt kéo, kèm hướng dẫn lấy cookie, cảnh báo rủi ro và ô xác nhận bắt buộc; cookie không lưu, xóa sau mỗi lần gửi | Cao | Đạt |
| FR-CR-15 | Lưu ra file CSV/XLSX/Parquet/JSON với các chế độ ghi (thêm, tạo file mới, ghi đè theo khóa) | Trung bình | Đạt |
| FR-CR-16 | Chế độ kéo nhiều lượt / kéo bảng: khoảng ngày, phân trang, chọn bảng bằng CSS selector, ánh xạ cột, xem trước, tạm dừng, tiếp tục, hủy, chạy lại lượt lỗi | Trung bình | Đạt (offline) |
| FR-CR-17 | Tải ảnh về `data/images/` cho field được người dùng đánh dấu là ảnh (URL lấy từ HTML, không OCR) | Thấp | Đạt |
| FR-CR-18 | Lên lịch chạy định kỳ (APScheduler); xem, sửa, xóa lịch | Trung bình | Đạt |
| FR-CR-19 | Xem dữ liệu đã lưu, xuất và tải file kết quả | Trung bình | Đạt |
| FR-CR-20 | Console log tiến trình từng URL; báo lỗi rõ ràng cho người dùng (không lỗi 502 trống) | Trung bình | Đạt |
| FR-CR-21 | Lưu ý website có thể chặn tự động (CAPTCHA, WAF, giới hạn IP...); hệ thống không cố vượt qua | Trung bình | Đạt |
| FR-CR-22 | Hai chế độ trích xuất cho trang dài chia nhiều đoạn, người dùng tự tick ở Bước 3: **Chậm** (mặc định, gọi AI tuần tự) và **Nhanh (tốn)** (gọi các đoạn đồng thời; không đổi số lượt gọi/chi phí AI, chỉ tăng tải đồng thời) | Trung bình | Đạt (đã đo thật: cùng 2 đoạn/60 bản ghi, Chậm 115 giây, Nhanh 47 giây) |
| FR-CR-23 | Giới hạn tốc độ gọi AI theo từng model (`AI_MODEL_LIMITS`): tự chờ (delay) để không vượt request/phút, header của API ghi đè cấu hình, gặp 429 thì chờ đúng `Retry-After` rồi thử lại | Cao | Đạt (đã đo hạn mức thật: qwen 2, GLM 5 request/phút; kiểm tra 429 thật) |
| FR-CR-24 | Tiến độ Crawl tách hai thanh: ① CODE (tải, làm sạch) và ② AI (từng đoạn, đang chờ hạn mức, thử lại, đoạn lỗi), cho biết đang chạy code hay model AI | Trung bình | Đạt |
| FR-CR-25 | Mỗi đoạn AI thử lại 1 lần khi lỗi, timeout tăng theo kích thước đoạn (đo thật: 60 bản ghi/đoạn đầy ~101 giây); một đoạn lỗi không làm hỏng cả trang; trang bị cắt bớt được báo rõ | Cao | Đạt |

### 5.2 Automation (Local Runner)

| Mã | Yêu cầu | Ưu tiên | Trạng thái |
|---|---|---|---|
| FR-AU-01 | Đăng nhập bằng tài khoản do admin cấp (mật khẩu băm argon2, phiên có hạn) | Cao | Đạt |
| FR-AU-02 | Quên mật khẩu: người dùng gửi yêu cầu, admin đặt lại; không tiết lộ tài khoản có tồn tại | Trung bình | Đạt |
| FR-AU-03 | **Describe:** mô tả flow bằng lời, AI tạo workbook nháp (sheet `steps`, khung `testcases`) | Cao | Đạt (offline); AI thật **Chưa UAT** |
| FR-AU-04 | **Record:** ghi thao tác thật trên máy người dùng, AI chuẩn hóa thành workbook | Cao | Đạt (offline); **Chưa UAT** |
| FR-AU-05 | **Inspector / Discovery / Repair:** kiểm tra locator, đề xuất step, sửa locator hỏng | Trung bình | Đạt (offline); **Chưa UAT** |
| FR-AU-06 | Đăng ký agent (token hiện một lần, có thu hồi) | Cao | Đạt |
| FR-AU-07 | Giao run cho agent; agent kiểm tra preflight trước khi mở trình duyệt | Cao | Đạt (offline); **Chưa UAT** |
| FR-AU-08 | Thực thi testcase trên máy người dùng; log, ảnh chụp và Excel chi tiết lưu tại máy | Cao | Đạt (offline); **Chưa UAT** |
| FR-AU-09 | Tóm tắt kết quả (PASS/FAIL/ERROR/UNVERIFIED, thời gian) trên web; run chỉ của chủ sở hữu | Trung bình | Đạt |
| FR-AU-10 | Xóa artifact trên server sau 7 ngày và thông báo trước | Thấp | Đạt |
| FR-AU-11 | Hướng dẫn cài môi trường Python ngay trên trang; giải thích chức năng cho người mới | Trung bình | Đạt |

### 5.3 Admin

| Mã | Yêu cầu | Ưu tiên | Trạng thái |
|---|---|---|---|
| FR-AD-01 | Đăng nhập admin chung cho Crawl và Automation (tài khoản admin Runner); có đường dự phòng bằng biến môi trường (chỉ Crawl) | Cao | Đạt |
| FR-AD-02 | Xem job lịch và lượt crawl bị lỗi; nhờ AI gợi ý sửa (chỉ đọc, không tự sửa mã) | Trung bình | Đạt (offline) |
| FR-AD-03 | Xem báo lỗi có cấu trúc từ người dùng và nhờ AI chẩn đoán | Trung bình | Đạt |
| FR-AD-04 | **Phản hồi tự do** ở mọi màn hình: AI_DEBUG phân loại; nếu không phải lỗi (độ tin cậy ≥ 0,75) thì trả lời trực tiếp; nếu là lỗi hoặc không chắc thì chuyển admin kèm trace | Cao | Đạt (offline); AI thật **Chưa UAT** |
| FR-AD-05 | Quản lý tài khoản Runner: tạo, khóa, mở khóa, đặt lại mật khẩu, xem yêu cầu quên mật khẩu, xem audit | Cao | Đạt |
| FR-AD-06 | Quản lý cookie theo domain do admin cấu hình (tính năng kế thừa) | Thấp | Đạt |

## 6. Yêu cầu phi chức năng

| Mã | Yêu cầu | Trạng thái |
|---|---|---|
| NFR-SEC-01 | Không đặt khóa API/mật khẩu thật trong mã hoặc `.env` trong repo; `*.env`, `.greennode.json` bị git và Docker bỏ qua | Đạt |
| NFR-SEC-02 | Kiểm tra robots.txt mặc định cho mọi engine (httpx và Playwright); bỏ qua chỉ theo lượt kéo và có log | Đạt |
| NFR-SEC-03 | Cookie chỉ nằm trong bộ nhớ, dùng một lần, không ghi DB, file hay log; cảnh báo rủi ro và xác nhận bắt buộc | Đạt |
| NFR-SEC-04 | Mật khẩu Runner băm argon2, tối thiểu 12 ký tự; route quản trị yêu cầu xác thực | Đạt |
| NFR-SEC-05 | Phản hồi người dùng được che cookie/token trước khi lưu và trước khi gửi AI; giới hạn 20 phản hồi mỗi phút | Đạt |
| NFR-SEC-06 | AI chỉ trích xuất và chẩn đoán; không tự quyết lưu bảng nào, trùng hay không, có retry hay không (rule-based trong code) | Đạt |
| NFR-DEP-01 | Container nghe cổng 8080 và có `GET /health` trả 200 (yêu cầu AgentBase) | Đạt (đã kiểm chứng bản deploy) |
| NFR-DEP-02 | Hai runtime tách biệt: `web-extract-api`, `web-extract-ui`; image linux/amd64 trên Container Registry của AgentBase | Đạt |
| NFR-DEP-03 | Dữ liệu bền vững trên Postgres (GreenNode RDS), không dùng SQLite trong container | Đạt |
| NFR-DEP-04 | CI chạy toàn bộ test trước mỗi lần build/push image (GitHub Actions) | Đạt |
| NFR-DEP-05 | Cấu hình bằng biến môi trường; có file mẫu `deploy/runtime-*.env.example` | Đạt |
| NFR-PERF-01 | Kiểm soát tốc độ theo domain (`FETCH_DEFAULT_DELAY_SECONDS`, mặc định 2 giây) | Đạt |
| NFR-PERF-02 | Trang lớn được chia đoạn ≤ 8000 ký tự khi gọi AI | Đạt |
| NFR-PERF-03 | Hạn mức AI: mỗi model có bộ đếm request/phút riêng (đo 2026-09-20: qwen3.6-flash 2, glm-5.3-flash 5, glm-5.2-hackathon 5, deepseek-v4-pro 5; Gemma chưa báo header, BTC cho biết 10); hệ thống xếp hàng thay vì nhận 429 | Đạt |
| NFR-USA-01 | Giao diện tiếng Việt, ba trang thống nhất (Crawl, Automation, Admin), logo MSB | Đạt |
| NFR-QUA-01 | Bộ test tự động: 676 test đạt (unit, API, UI) | Đạt |

## 7. Kiến trúc và dữ liệu

```
Người dùng ──> UI (Streamlit + nginx, runtime web-extract-ui, cổng 8080)
                    │  HTTP
                    ▼
              API (FastAPI, runtime web-extract-api, cổng 8080)
   ┌───────────────┼───────────────────────────────┐
   ▼               ▼                               ▼
Fetch (httpx /   AI runtime (GreenNode MaaS,    Postgres (GreenNode RDS)
Playwright)      OpenAI-compatible)             datasets · records · runner_*
   │
   ▼
Website nguồn (kiểm tra robots.txt, giới hạn tốc độ)

Máy người dùng: Agent + Recorder + Inspector (Python + Chromium) ──HTTPS──> API
                runner.env (user/pass của trang được test) không rời máy
```

**Mô hình dữ liệu (rút gọn)**

| Bảng | Vai trò |
|---|---|
| `datasets` | Định danh dataset, `schema_signature` (danh sách field) |
| `dataset_sources` | Nguồn URL của dataset; đổi nguồn là thêm dòng mới, dòng cũ `active=false` (giữ audit) |
| `records` | `data` (JSON linh hoạt), `content_hash`, `evidence`, `confidence`, `crawled_at`, `as_of` |
| `extraction_strategies` | Cache chiến lược trích xuất theo domain |
| `scheduled_jobs`, `audit_log` | Lịch chạy; nhật ký sự kiện (báo lỗi, phản hồi, chẩn đoán) |
| `runner_*` | Tài khoản, phiên, agent, run, thông báo, yêu cầu quên mật khẩu, audit của Automation |

## 8. Quy trình chính

**Crawl (5 bước):** 1) Nguồn dữ liệu → 2) Trường dữ liệu → 3) Chạy và kết quả → 4) Dữ liệu đã lưu → 5) Lịch tự động.
Luồng xử lý mỗi URL: kiểm tra robots.txt → tải trang → làm sạch → structured data / cache → AI (nếu còn field) → gắn confidence → lưu (DB/file) → ghi nhật ký.

**Automation:** Soạn (Describe hoặc Record) → Kiểm tra (Inspector) → Đăng ký agent → Giao run → Agent chạy trên máy → Xem tóm tắt trên web.

**Phản hồi:** Người dùng gửi phản hồi → AI_DEBUG phân loại → (không phải lỗi) trả lời trực tiếp / (là lỗi hoặc không chắc) chuyển admin kèm trace → admin xử lý và đánh dấu xong.

## 9. Ràng buộc, giả định, rủi ro

| Loại | Nội dung |
|---|---|
| Ràng buộc | Stack cố định: FastAPI, Streamlit, APScheduler, SQLite/Postgres, httpx/Playwright; AI chạy qua endpoint GreenNode MaaS |
| Giả định | Người dùng có quyền hợp pháp với dữ liệu họ thu thập; máy chạy agent truy cập được trang cần test |
| Rủi ro | **Website chặn tự động** (CAPTCHA, WAF, chặn IP đám mây, OTP/2FA) → lượt kéo lỗi hoặc rỗng; hệ thống không né |
| Rủi ro | **Chất lượng model AI** (JSON không sạch, chế độ thinking làm chậm) → cần đo trước khi dùng thật |
| Rủi ro | **Hạn mức request/phút thấp** (qwen 2/phút, dùng chung cho crawl, phản hồi AI và Runner AI cùng một key) → nhiều người crawl cùng lúc sẽ phải xếp hàng (thanh tiến độ báo "chờ hạn mức"); giảm nhẹ bằng chọn model có hạn mức cao hơn (GLM 5/phút, nhanh hơn ~2,2 lần trong bài đo) sau khi kiểm tra chất lượng trên trang thật, hoặc xin BTC nâng hạn mức |
| Rủi ro | **DB mở Public, chưa có SSL** trong giai đoạn thi → dùng mật khẩu mạnh; tắt Public hoặc chuyển VPC sau khi xong |
| Rủi ro | **Chi phí runtime** tính vào ví thật, chạy liên tục → dừng runtime cũ/thừa khi không dùng |
| Rủi ro | Người dùng Automation phải cài Python trên máy → có hướng dẫn trên trang; kế hoạch đóng gói |
| Rủi ro | Cookie dán vào có rủi ro bảo mật → cảnh báo, xác nhận bắt buộc, không lưu |

## 10. Tiêu chí nghiệm thu

| Mã | Tiêu chí |
|---|---|
| AC-01 | Nhập URL công khai + field → dữ liệu xuất hiện ở Bước 4 với confidence và evidence |
| AC-02 | Chạy lại cùng URL khi nội dung không đổi → không tạo bản ghi mới (trạng thái "không đổi") |
| AC-03 | Trang bị robots.txt chặn → báo `blocked_by_robots_txt`; bật bỏ qua chỉ khi có lý do, log ghi lại |
| AC-04 | Dán cookie mà chưa tích xác nhận rủi ro → không chạy; sau khi chạy, cookie không còn trong phiên |
| AC-05 | Kéo bảng nhiều trang/khoảng ngày → không trùng dòng khi chạy lại |
| AC-06 | Lưu file XLSX/CSV mở được, đúng cột |
| AC-07 | Lịch chạy tự động tạo bản ghi theo chu kỳ |
| AC-08 | Admin đăng nhập một lần thấy đủ các tab Crawl và Automation |
| AC-09 | Phản hồi "không phải lỗi" được AI trả lời trực tiếp; phản hồi lỗi xuất hiện ở danh sách admin kèm trace |
| AC-10 | Người dùng Automation cài môi trường theo hướng dẫn, chạy được Record và agent (UAT) |
| AC-11 | `/health` của API và UI trả 200 sau deploy; dữ liệu còn sau khi restart runtime |

## 11. Trạng thái hiện tại và lộ trình

**Đã hoàn thành:** toàn bộ chức năng ở mục 5 ở mức "Đạt/Đạt (offline)"; triển khai UI + API lên GreenNode; Runner đã kiểm chứng trên Postgres thật; CI có cổng kiểm thử.

**Việc còn lại:** đo chất lượng trích xuất với model AI thật (Qwen3.6-Flash, GLM-5.2); UAT Automation với trang và trình duyệt thật; đóng gói agent cho người không cài Python;
tắt DB Public/bật SSL; dọn runtime thừa.

**Hướng phát triển:** chọn phần tử trực quan (visual selector), Data Lineage, chạy testcase không giao diện trên server (chỉ với trang công khai), tự động deploy có kiểm soát.

## 12. Thuật ngữ

| Thuật ngữ | Nghĩa |
|---|---|
| Dataset | Tập bản ghi cùng schema (danh sách field) |
| Evidence | Đoạn văn gốc chứa giá trị AI trích xuất |
| Confidence | Độ tin cậy 0–1 của từng giá trị |
| robots.txt | Tệp website dùng để chỉ dẫn robot được phép truy cập gì |
| WAF | Tường bảo vệ ứng dụng web (chặn bot) |
| Workbook | File Excel gồm sheet `steps` và `testcases` cho Automation |
| Agent | Chương trình chạy trên máy người dùng, nhận run và điều khiển trình duyệt |
| AgentBase | Nền tảng chạy runtime container của GreenNode |
| MaaS | Model-as-a-Service: dịch vụ gọi model AI của GreenNode |
