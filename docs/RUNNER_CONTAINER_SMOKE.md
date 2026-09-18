# Smoke test container không dùng secret

Phạm vi: API/UI local, SQLite giả lập và Chromium với HTML tự tạo. Không dùng
compose mặc định, không mount thư mục data/config của project, không truy cập UAT.

## Chuẩn bị build context

```powershell
python -B scripts/prepare_container_context.py
```

Lệnh trả JSON với `context` là thư mục mới bên trong `.test-work`. Chỉ copy Python
source của `src`/`ui`, các module workbook API cần và file đóng gói được chọn rõ
trong script. Không copy toàn workspace, không đọc dotenv/workbook/runtime state.
Từ chối symlink/junction; bỏ qua tên ẩn hoặc tên chứa secret/credential/password/token.
Chuẩn hóa LF cho build Linux và ghi SHA-256 mỗi file vào BUILD_MANIFEST.json.
Đây là danh sách source được phép, không phải công cụ phát hiện secret hardcode.

Tạo thư mục cấu hình Docker rỗng riêng trong workspace. Trong các lệnh dưới,
`<DOCKER_CONFIG>` là thư mục đó và `<CONTEXT>` là đường dẫn vừa tạo. Nếu cần chỉ
định engine local, thêm `--host npipe:////./pipe/docker_engine` trên Windows.
Không dùng registry cần đăng nhập cho smoke này.

```text
docker --config <DOCKER_CONFIG> build -f <CONTEXT>/Dockerfile.ui -t web-extract-phase24-ui:local <CONTEXT>
docker --config <DOCKER_CONFIG> build -f <CONTEXT>/Dockerfile.api -t web-extract-phase24-api:local <CONTEXT>
```

## Các ca trong container dùng một lần

Tạo tên container và volume mới riêng cho lần thử. Không dùng tên volume production.
Không publish port; probe gọi loopback bên trong container. Đặt
`CONTAINER_SMOKE_ONLY=1` và `PYTHON_DOTENV_DISABLED=1`; probe từ chối chạy nếu thiếu
cờ smoke. Không truyền biến môi trường kế thừa dạng `-e TEN_BIEN`.

| Container | Cấu hình | Probe và kỳ vọng |
| --- | --- | --- |
| UI bình thường | Image UI, network none, telemetry tắt | `python scripts/container_probe.py ui`: health/ready/trang gốc 200 |
| Chỉ nginx | Image UI, network none, entrypoint nginx, args `-g "daemon off;"` | `ui-down`: health 200, ready 502 |
| API seed | Image API, network none, volume mới tại /smoke-data | `api-seed`: health/datasets 200, runner/me 401, tạo dataset/audit giả |
| API tạo lại | Container mới, cùng volume seed | `api-verify`: dataset/audit còn, dataset đọc được qua HTTP |
| Chromium | Container API, network none | `browser`: mở HTML tổng hợp và kiểm tra title/button |

API smoke cần các biến không nhạy cảm:

```text
RUNNER_ENABLED=true
RUNNER_AI_ENABLED=false
DB_PATH=/smoke-data/crawl.db
RUNNER_DB_PATH=/smoke-data/runner.db
RUNNER_DATA_ROOT=/smoke-data/runner
```

UI đặt `STREAMLIT_BROWSER_GATHER_USAGE_STATS=false`. API không có AI/admin secret;
admin từ chối truy cập là hành vi mong đợi. Probe còn tạo workbook trong RAM để
kiểm tra dependency import và bảo đảm chỉ sinh header testcase, không settings.

Chạy probe bằng `docker exec <CONTAINER> python scripts/container_probe.py <MODE>`.
Sau kiểm tra, dừng đúng container vừa tạo. Giữ hoặc xóa đúng volume synthetic của
lần thử theo nhu cầu; không dùng prune hay thao tác trên container/volume khác.

## Giới hạn bằng chứng

HTTP trang gốc 200 chưa chứng minh WebSocket/tương tác Streamlit đúng. Dữ liệu
volume còn sau tạo lại container chưa kiểm chứng backup/khôi phục hoặc PostgreSQL.
Chromium synthetic không phải executor UAT. Kết quả thực tế được ghi riêng trong
RUNNER_UAT_RESULTS.md; không đánh dấu GreenNode hoặc phase 25 đạt từ smoke này.
