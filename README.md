# Web Data Extraction & Management Platform

Ứng dụng cho phép người dùng nghiệp vụ (non-technical) tự cấu hình thu thập dữ liệu từ
website được phép, không cần viết code — nhập URL + mô tả field cần lấy bằng ngôn ngữ
tự nhiên, hệ thống tự crawl và AI trích xuất theo cấu trúc.

Xem `CLAUDE.md` để biết đầy đủ kiến trúc, nguyên tắc thiết kế và quy ước code. Xem
`CHANGELOG.md` cho lịch sử thay đổi chi tiết theo từng phần việc.

## Trạng thái hiện tại

**Đã xong:**
- Crawl 1 URL (fetch → làm sạch HTML → ưu tiên structured data JSON-LD/Open Graph →
  cache chiến lược theo domain → fallback AI) — lưu DB (dataset/schema-match/dedup) hoặc
  ghi file JSON, chọn 1 trong 2 khi tạo job.
- Job crawl định kỳ (APScheduler), quản lý qua UI Streamlit.
- robots.txt thật + rate-limit theo domain trước khi fetch.
- Gắn cờ `needs_review` khi AI confidence thấp hơn ngưỡng cấu hình.
- Panel admin nội bộ "AI gợi ý sửa lỗi" cho job lịch bị lỗi (chỉ gợi ý text, không tự sửa).
- UI Streamlit đầy đủ 5 bước (nguồn → field → chạy & kết quả → dữ liệu đã lưu → lịch).
- Docker image riêng cho Runtime API/UI để deploy lên GreenNode AgentBase (xem mục
  "Deploy lên GreenNode") — **chưa build/test thật với Docker daemon**, mới review tĩnh.
- Lựa chọn PostgreSQL thay SQLite (`DB_BACKEND=postgres`, xem mục "Database" bên dưới) —
  **chưa verify với Postgres thật** (sandbox dev không pull được image Docker Hub), cần tự
  chạy `docker compose --profile postgres up -d postgres` rồi `pytest
  tests/storage/test_postgres_storage.py` để xác nhận.
- Tải ảnh tài sản về `data/images/` khi đánh dấu field là ảnh (checkbox ở Bước 2/5).
- Crawl trang cần đăng nhập bằng cookie/session dán thủ công theo domain (panel admin).
- Panel admin bảo vệ bằng HTTP Basic Auth (`ADMIN_USERNAME`/`ADMIN_PASSWORD`).
- Log tiến trình crawl theo từng bước (`LOG_LEVEL=INFO` để xem trong console/docker logs).

**Đang làm dở / chưa làm:**
- Fetch site JS-heavy bằng Playwright — đã có adapter, chưa bật làm mặc định trong app.
- Chưa xác nhận URL/format registry thật của GreenNode AgentBase (đang để placeholder
  trong README mục Deploy).
- Vị trí dạng bản đồ JS (Google Maps SDK) — chưa làm; lấy địa chỉ/tên dạng text (không
  phải toạ độ) đã dùng được ngay qua field mô tả bình thường, không cần code thêm.
- Data Dictionary / Data Lineage, visual selector, chuyển UI sang React — chưa làm, xem
  `CLAUDE.md` mục "Việc CHƯA làm trong MVP".

## Database (SQLite mặc định, PostgreSQL tuỳ chọn)

```env
# .env — mặc định SQLite, không cần khai báo gì thêm
DB_BACKEND=sqlite
DB_PATH=./data/app.db

# Hoặc dùng Postgres (vd. GreenNode managed Postgres, hoặc service `postgres`
# trong docker-compose khi chạy `docker compose --profile postgres up -d postgres`)
DB_BACKEND=postgres
DATABASE_URL=postgresql://web_extract_agent:web_extract_agent_dev_only@localhost:5432/web_extract_agent
```
Cả 2 cùng implement `StorageEngine` — đổi backend chỉ cần sửa `.env`, không đổi code gọi.

## Panel admin (Basic Auth) + crawl trang cần đăng nhập

```env
# .env — BẮT BUỘC set cả 2 để dùng panel admin (/admin/*, ui/pages/9_Admin_Debug.py)
# — thiếu 1 trong 2 thì panel TỪ CHỐI mọi request (401), không mở cửa ngầm định.
ADMIN_USERNAME=
ADMIN_PASSWORD=
```

Panel admin (tab "🔑 Cookie đăng nhập theo domain") cho phép dán cookie/session đã đăng
nhập sẵn (tự đăng nhập bằng trình duyệt thật, copy cookie từ DevTools) cho 1 domain cần
đăng nhập mới crawl được — hệ thống chỉ gắn header `Cookie` vào request khi fetch domain
đó, KHÔNG tự động đăng nhập/điền form login. Cookie hết hạn thì tự vào panel cập nhật lại.

## Setup môi trường lần đầu ở máy mới

**Cách 1 (khuyến nghị, đảm bảo môi trường nhất quán giữa các máy): dùng Docker.**
Không phụ thuộc những gì đã cài sẵn trên từng máy — máy nào chạy `docker compose up`
cũng ra environment giống hệt nhau, khỏi phải nhớ đúng version Python/package theo trí nhớ.

```bash
cp .env.example .env
# điền .env

docker compose up --build
```
- API: http://localhost:8000 (health check: http://localhost:8000/health)
- UI: http://localhost:8501 (health check: http://localhost:8501/health)

**Cách 2 (nhanh hơn để dev/debug, nhưng cần tự quản lý version Python đúng theo
`.python-version`):** venv trực tiếp.

```bash
python --version   # phải khớp .python-version (3.12.14) — nếu không, cài đúng version qua pyenv
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt   # version đã cố định (pip freeze) — cài lại ra đúng y hệt bản đã test
playwright install chromium

cp .env.example .env
# điền AI_BASE_URL / AI_API_KEY thật vào .env

python -m pytest tests/ -v          # chạy test bằng mock, không cần credentials
uvicorn src.api.main:app --reload    # chạy backend
streamlit run ui/app.py              # chạy giao diện (terminal khác)
```

> `requirements.txt` dùng version CỐ ĐỊNH (`==`, sinh bằng `pip freeze` từ venv sạch),
> không phải `>=` — cài lại ở máy khác ra đúng y hệt version, không lệch theo thời điểm
> cài. Muốn nâng version package nào, cài thủ công rồi `pip freeze > requirements.txt`
> lại từ 1 venv sạch (không sửa tay số version).

## AI runtime (GreenNode MaaS)

Format API đã xác nhận qua docs.greennode.ai (không phải giả định — xem docstring
`src/ai/greennode_client.py` để biết chi tiết/nguồn):
- `AI_BASE_URL` phải có hậu tố `/v1` (VD: `https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1`).
  Client tự nối `/chat/completions` vào sau — thiếu `/v1` sẽ khiến mọi request 404
  (client có log cảnh báo khi thiếu).
- `AI_MODEL` phải là ID có prefix nhà cung cấp lấy từ catalog GreenNode (VD xác nhận
  được: `openai/gpt-4o`), KHÔNG phải tên hiển thị như "Qwen 3.6 Flash" — lấy ID thật
  qua `GET {AI_BASE_URL}/models` hoặc trang API Keys/Model Catalog trên console GreenNode.
- Auth: header `Authorization: Bearer <AI_API_KEY>` — không cần header nào khác cho
  chat completions.
- `AI_CONFIDENCE_THRESHOLD` (mặc định `0.7`): record vẫn LUÔN được lưu bất kể confidence
  — ngưỡng này chỉ gắn cờ `needs_review=true` trong record/response `/crawl` để UI cảnh
  báo người dùng xem lại, KHÔNG loại bỏ hay chặn lưu record nào.
- `AI_DEBUG_BASE_URL`/`AI_DEBUG_API_KEY`/`AI_DEBUG_MODEL`/`AI_DEBUG_TIMEOUT_SECONDS`:
  cấu hình riêng cho panel admin "AI gợi ý sửa lỗi" (`ui/pages/9_Admin_Debug.py`) —
  KHÔNG dùng trong pipeline crawl/extract. Mỗi biến fallback về biến `AI_*` tương ứng
  nếu để trống (dùng chung endpoint/model với extract theo mặc định).

## Deploy lên GreenNode (AgentBase)

Nền tảng GreenNode AgentBase: **mỗi Agent Runtime = 1 container/1 image riêng**. App này
có 2 service (FastAPI backend + Streamlit UI) → deploy thành **2 Agent Runtime riêng**,
mỗi cái build từ 1 Dockerfile riêng (`Dockerfile.api`, `Dockerfile.ui`) — KHÔNG dùng
`docker-compose.yml` để deploy lên GreenNode (file đó chỉ để chạy dev/test local).

Yêu cầu bắt buộc của nền tảng (đã áp dụng trong 2 Dockerfile): container lắng nghe cổng
**8080**, có route `GET /health` trả `200` cho liveness/readiness check.

### Bước 1 — Build + tag + push 2 image (làm TRƯỚC khi vào form "Create an Agent runtime")

> ⚠️ Registry thật (Agent Base registry của GreenNode) **chưa xác nhận URL/format** tại
> thời điểm viết README này — thay `<GREENNODE_REGISTRY_URL>` bên dưới bằng giá trị thật
> lấy từ console GreenNode/BTC trước khi chạy. Cách `docker login`/tag có thể khác đôi
> chút tuỳ registry thật, kiểm tra lại hướng dẫn chính thức của GreenNode khi có.

```bash
# Runtime API
docker build -f Dockerfile.api -t <GREENNODE_REGISTRY_URL>/web-extract-agent-api:latest .
docker push <GREENNODE_REGISTRY_URL>/web-extract-agent-api:latest

# Runtime UI
docker build -f Dockerfile.ui -t <GREENNODE_REGISTRY_URL>/web-extract-agent-ui:latest .
docker push <GREENNODE_REGISTRY_URL>/web-extract-agent-ui:latest
```

### Bước 2 — Tạo Agent Runtime cho API TRƯỚC

Trong form "Create an Agent runtime" trên GreenNode, chọn image
`web-extract-agent-api:latest` vừa push, điền biến môi trường:

| Biến | Ghi chú |
|---|---|
| `AI_BASE_URL` | Endpoint GreenNode MaaS thật, phải có hậu tố `/v1` (xem mục "AI runtime" trên) |
| `AI_API_KEY` | API key thật — KHÔNG commit vào repo |
| `AI_MODEL` | Model ID có prefix nhà cung cấp (VD `openai/gpt-4o`), lấy từ catalog GreenNode |
| `AI_CONFIDENCE_THRESHOLD` | Mặc định `0.7` nếu không set |
| `AI_DEBUG_BASE_URL`/`AI_DEBUG_API_KEY`/`AI_DEBUG_MODEL`/`AI_DEBUG_TIMEOUT_SECONDS` | Panel admin — để trống nếu dùng chung với `AI_*` ở trên |
| `DB_PATH` | Đường dẫn SQLite trong container, vd `./data/app.db` — cần mount volume/disk bền vững theo cơ chế storage của GreenNode, nếu không dữ liệu mất khi container restart |
| `FETCH_USER_AGENT`, `FETCH_DEFAULT_DELAY_SECONDS`, `FETCH_RESPECT_ROBOTS_TXT` | Cấu hình fetch/compliance — xem `.env.example` |
| `LOG_LEVEL` | Mặc định `INFO` nếu không set |

Sau khi tạo xong, **lấy URL public của Runtime API** (GreenNode cấp sau khi deploy) — cần
URL này ở bước 3.

### Bước 3 — Tạo Agent Runtime cho UI SAU, dùng URL của Runtime API ở bước 2

Chọn image `web-extract-agent-ui:latest`, điền biến môi trường:

| Biến | Ghi chú |
|---|---|
| `API_BASE_URL` | **Bắt buộc** — URL public của Runtime API vừa tạo ở Bước 2 (VD `https://<runtime-api>.greennode.ai`), KHÔNG phải `localhost` |

Thứ tự bắt buộc: **phải deploy xong Runtime API và có URL trước, rồi mới tạo Runtime UI**
— vì `API_BASE_URL` của UI phụ thuộc vào URL đó.

## Compliance

Mặc định luôn kiểm tra `robots.txt` và có delay giữa các request theo domain
(`FETCH_DEFAULT_DELAY_SECONDS` trong `.env`). Không tắt kiểm tra robots.txt trừ khi có
lý do rõ ràng và được ghi log lại tường minh.

## Cấu trúc project

Xem mục "Nguyên tắc thiết kế bắt buộc" trong `CLAUDE.md` — tóm tắt: fetch/clean/AI/storage
tách rời theo adapter pattern, AI chỉ trích xuất chứ không tự quyết định nghiệp vụ, dữ liệu
lưu dạng `dataset` + JSON linh hoạt thay vì tạo bảng SQL riêng từng loại.
# Runner local

Hướng dẫn bật Runner, tạo tài khoản và chạy agent: [Runner setup](docs/RUNNER_SETUP.md).
Runner mặc định tắt. Bản tích hợp hiện hỗ trợ workbook local/Hybrid và summary;
Record local và Describe AI xuất workbook nháp đã có; Inspector/AI repair chưa triển khai.
