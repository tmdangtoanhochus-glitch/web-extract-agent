# Web Data Extraction & Management Platform — CLAUDE.md

## Bối cảnh
Ứng dụng web cho phép người dùng nghiệp vụ (non-technical) tự cấu hình thu thập dữ liệu
từ website được phép, không cần viết code. Người dùng nhập URL + mô tả field cần lấy
bằng ngôn ngữ tự nhiên → hệ thống tự crawl, AI trích xuất, lưu vào database.

Đây là bài dự thi (competition project) — bắt buộc push code lên GitHub.

## QUAN TRỌNG: phân biệt 2 vai trò AI, đừng nhầm lẫn

**(A) AI dùng để CODE (dev tool)** — Claude Code, OpenCode, Codex... Đây là công cụ hỗ
trợ người phát triển viết code, KHÔNG nằm trong sản phẩm cuối, không deploy, không chạy
khi người dùng thật dùng web app. OpenCode bản thân nó là 1 coding agent mã nguồn mở
(tương tự Claude Code) có thể kết nối nhiều provider model khác nhau — BTC cấp công cụ
này như phương án thay thế cho ai không có subscription Claude Code/Codex. Dùng tool
nào để code là lựa chọn cá nhân, không ảnh hưởng đến sản phẩm.

**(B) AI chạy BÊN TRONG sản phẩm lúc vận hành** — model cụ thể (Qwen/GLM...) được BTC
cấp qua GreenNode, gọi ở bước classify/extract (`src/ai/client.py`). Đây là AI runtime
thật sự của ứng dụng, cấu hình qua `.env` (`AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL`),
độc lập hoàn toàn với việc đang dùng dev tool nào để code ra dòng code đó.

→ Khi sửa `src/ai/client.py`, LUÔN trỏ về endpoint model mà BTC cấp (Qwen/GLM qua
GreenNode) — xác nhận lại format thật (OpenAI-compatible hay khác) trước khi build
client chính thức, đừng giả định.

## Nguyên tắc thiết kế bắt buộc (đọc kỹ trước khi code)

### 1. AI chỉ trích xuất — không tự quyết định nghiệp vụ
AI chỉ dùng cho: đọc HTML đã làm sạch, suy luận field theo mô tả tự nhiên của người
dùng, trả JSON có cấu trúc + confidence + evidence quote (câu/đoạn gốc chứa giá trị đó).
KHÔNG để AI tự quyết định: lưu vào bảng nào, có trùng dữ liệu không, retry hay không.
Những việc đó là rule-based, code tường minh, test được.

### 2. Fetch + clean TRƯỚC khi gọi AI, không đưa URL thẳng cho AI tự fetch
- Code tự fetch (httpx cho site tĩnh, Playwright cho site JS-heavy) rồi làm sạch HTML
  (bỏ script/style/nav/footer, giữ bảng/list dạng Markdown) TRƯỚC khi gửi cho AI.
- Ưu tiên tìm structured data có sẵn trước (JSON-LD `<script type="application/ld+json">`,
  Open Graph meta tags) — dùng trực tiếp nếu có, chỉ fallback sang AI extract khi không có.
- Lý do: rẻ hơn (giảm token), kiểm soát compliance được (robots.txt/rate-limit nằm ở bước
  fetch do code viết, không phó mặc cho AI agent tool tự quyết định cách fetch).

### 3. robots.txt: mặc định LUÔN kiểm tra, không phải toggle im lặng
Nếu người dùng muốn bỏ qua robots.txt cho 1 domain cụ thể, phải là hành động tường minh
có cảnh báo rõ ràng, ghi log lại — không làm thành checkbox tắt/bật vô hiệu hóa dễ dàng.
Kèm rate-limit/delay giữa các request theo domain.

### 4. Lưu trữ: dynamic schema qua JSON, KHÔNG auto-migrate bảng SQL riêng từng job
```sql
CREATE TABLE datasets (
    dataset_id TEXT PRIMARY KEY,
    dataset_name TEXT,
    schema_signature TEXT,      -- JSON list các field, dùng để so khớp job mới
    created_at TIMESTAMP
);

CREATE TABLE dataset_sources (
    dataset_id TEXT REFERENCES datasets(dataset_id),
    source_url TEXT,
    active BOOLEAN,              -- nguồn đang dùng; đổi nguồn = thêm dòng mới active=true,
                                  -- đánh dấu dòng cũ active=false, KHÔNG xóa (giữ audit)
    added_at TIMESTAMP
);

CREATE TABLE records (
    record_id TEXT PRIMARY KEY,
    dataset_id TEXT REFERENCES datasets(dataset_id),
    source_url TEXT,
    data JSON,                   -- field thật sự, linh hoạt theo từng dataset
    content_hash TEXT,           -- change detection: so hash để biết nội dung có đổi
    evidence JSON,                -- câu/đoạn gốc AI trích xuất được, để verify
    confidence FLOAT,
    crawled_at TIMESTAMP,
    as_of TIMESTAMP              -- thời điểm dữ liệu có hiệu lực THEO NỘI DUNG TRANG,
                                  -- có thể khác crawled_at
);
```
- Khi cào 1 URL: so `schema_signature` mới với dataset đã có → khớp thì lưu vào
  `dataset_id` đó, không khớp thì tạo dataset mới.
- Đổi nguồn dữ liệu cho 1 dataset đã có: KHÔNG tự động gộp chỉ vì field giống nhau —
  luôn để người dùng xác nhận tường minh (tránh gộp nhầm 2 dataset không liên quan).
- Không tạo bảng SQL riêng/migration tự động cho từng job — mọi field nằm trong cột `data` JSON.

### 5. Cache chiến lược extract theo domain — giảm gọi AI lặp lại
Lần đầu cào 1 domain, lưu lại "chiến lược" (structured-data path tìm được, hoặc pattern
AI đã dùng) — lần sau ưu tiên áp lại, chỉ gọi AI lại khi cache fail (site đổi cấu trúc)
hoặc `content_hash` cho thấy nội dung thay đổi đáng kể.

### 6. Adapter pattern cho mọi thành phần external
Tách interface trừu tượng cho: fetch engine (static/Playwright), AI client, storage.
Có mock/test double cho từng interface để test được mà không cần chạy thật.

## Tech stack (đã chốt, KHÔNG tự đổi sang React/Celery/Redis)
- Backend: FastAPI (Python)
- Frontend MVP: **Streamlit** (không dùng React/TypeScript cho giai đoạn MVP — tiết kiệm
  thời gian, đủ để demo form nhập URL → xem tiến trình → xem/tải kết quả)
- Scheduler: **APScheduler** (không dùng Celery+Redis cho MVP — quá nặng so với nhu cầu)
- Database: SQLite cho dev/MVP; có thể nâng lên MySQL/Postgres sau nếu cần, không bắt buộc ngay
- Scraping: httpx (site tĩnh) + Playwright (site JS-heavy), có adapter tách biệt
- AI runtime: xem mục (B) ở trên — endpoint Qwen/GLM do GreenNode cấp
- Containerize bằng Docker khi bắt đầu tích hợp Playwright (tránh lỗi thiếu dependency hệ thống)

## Việc CHƯA làm trong MVP (để dành roadmap, đừng tự ý code trước)
- Visual selector (click chọn phần tử trên preview) — phase sau, dùng để sửa tay khi AI đoán sai
- Data Lineage graph (React Flow/D3) — phase sau
- Chuyển frontend sang React+TypeScript — chỉ khi MVP ổn định và còn thời gian
- Celery+Redis — chỉ cân nhắc nếu APScheduler không đủ tải

## Bảo mật khi dev cùng AI coding tool
- KHÔNG dùng API key/credential thật trong `.env` khi làm việc cùng AI coding tool — dùng
  placeholder, điền giá trị thật ngoài phiên làm việc, hoặc dùng biến môi trường hệ thống.
- KHÔNG dùng dữ liệu cào thật có khả năng chứa PII làm dữ liệu test — dùng dữ liệu mẫu giả.
- `.gitignore` phải luôn chặn `.env`, `*.db`, `data/`, `__pycache__/`.
- `.claude/settings.json` nên có deny rule cho `.env*`, `*.pem`, `*.key`, `data/*.db` —
  nhưng đây chỉ là lớp phòng thủ phụ, không thay thế được việc không đặt secret thật vào
  thư mục project khi làm việc cùng AI.

## Quy ước làm việc nhiều máy (git)
- `.env` không nằm trong repo — mỗi máy mới clone về phải tự tạo lại `.env` từ
  `.env.example` và điền key thật riêng.
- Luôn `git pull` trước khi bắt đầu sửa ở 1 máy, và `git push` ngay sau khi xong, tránh
  làm việc trên code cũ hoặc gây conflict.

## Quy ước code
- Comment/docstring bằng tiếng Việt cho phần logic nghiệp vụ.
- Mỗi module (fetch, clean, ai_extract, storage, scheduler) là hàm/class độc lập, test
  được riêng — vì scheduler sẽ gọi lại đúng các hàm này, không viết logic lồng trong route handler.
- Trước khi thêm dependency mới ngoài danh sách tech stack ở trên, hỏi lại thay vì tự quyết.

## Khi không chắc phạm vi
Hỏi lại người dùng trước khi code, đặc biệt về: field bắt buộc cụ thể, ngưỡng confidence,
danh sách domain whitelist ban đầu, format thật của endpoint AI runtime — ưu tiên chạy
được bản MVP tối giản (crawl 1 site tĩnh, lưu DB, xem log) trước khi mở rộng.
