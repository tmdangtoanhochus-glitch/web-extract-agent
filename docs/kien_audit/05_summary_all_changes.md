# 05 — Tổng hợp tất cả thay đổi (Changelog cho team)

> **Date:** 2026-09-16  
> **Author:** Kiên  
> **Project:** web-extract-agent

---

## Danh sách tất cả thay đổi

### Phase 1 — HTML Cleaner Bug (doc 02)

| File | Thay đổi |
|------|----------|
| `src/clean/html_cleaner.py` | Thêm `div`, `span` vào renderable tags. Leaf div/span (không chứa element con) được render text. Container div/span bị skip để tránh duplicate. |

### Phase 2 — Multi-Record Extraction (doc 03)

| File | Thay đổi |
|------|----------|
| `src/ai/base.py` | `ExtractionResult.records: list[dict]` thay vì `fields: dict`. `fields` property = record đầu (backward compat). |
| `src/ai/greennode_client.py` | Prompt đổi từ "1 JSON object" → "JSON array". `_parse_json()` + `_to_records()` thay thế `_parse_json_object()` + `_to_field_extractions()`. `max_tokens=16384`. |
| `src/pipeline.py` | `AiExtractResult.records` list. `ai_extract()` merge structured data với mỗi AI record. `run_crawl_job()` + `run_file_crawl_job()` loop save nhiều records. `PipelineResult.record_count` + `FileCrawlResult.record_count`. |
| `src/api/main.py` | `CrawlResponse.record_count`. `_build_default_app()` tôn trọng `FETCH_RESPECT_ROBOTS_TXT`. |
| `ui/app.py` | CSV UTF-8 BOM. XLSX export (pandas + openpyxl). UI timeout 300s. |
| `.env` | `FETCH_RESPECT_ROBOTS_TXT=false`, `AI_TIMEOUT_SECONDS=300` |

### Phase 3 — File Export + UX (doc 04)

| File | Thay đổi |
|------|----------|
| `src/storage/file_writer.py` | Rewrite: multi-format theo extension (`.json`/`.csv`/`.xlsx`/`.parquet`). `_get_format()`, `_read_records()`, `_write_records()`. |
| `src/api/main.py` | `record_count` trong file mode response. |
| `ui/app.py` | Progress bar với % + color-coded status. Disable Crawl button khi đang xử lý. `st.success()`/`st.error()` notifications. File preview theo format. |
| `requirements.txt` | `openpyxl==3.1.5` |

### Phase 4 — Tabular Columns + Preview + Parquet (chưa log trước đây)

| File | Thay đổi |
|------|----------|
| `src/pipeline.py:294` | Flatten `data` dict → field names thành cột riêng (không nested `data` key). Trước: `{"data": {"title": "..."}}`. Sau: `{"title": "...", "price": "...", ...}`. |
| `src/storage/file_writer.py` | Thêm Parquet support (`.parquet` → pandas + pyarrow). |
| `ui/app.py` | Nút "📊 Preview Data" cho DB mode. Nút "📊 Preview {filename}" cho file mode. JSON → dict view (`st.json`), XLSX/CSV/Parquet → tabular (`st.dataframe`). MIME type đúng theo extension. |

### Phase 5 — AI Timeout + JSON Repair (chưa log trước đây)

| File | Thay đổi |
|------|----------|
| `src/ai/greennode_client.py` | `max_tokens=16384` (từ 8192). `_repair_truncated_json()` — repair JSON array bị cắt giữa chừng do token limit: tìm `}` hoàn chỉnh cuối, đóng `]`. |
| `.env` | `AI_TIMEOUT_SECONDS=300` (từ 180) |

---

## Files bị sửa (tổng cộng)

```
src/ai/base.py
src/ai/greennode_client.py
src/clean/html_cleaner.py
src/pipeline.py
src/api/main.py
src/storage/file_writer.py
ui/app.py
requirements.txt
.env
```

---

1. **Git commit + push** — tối ưu nhất nếu team dùng git
2. **Patch file** — tạo `.patch` để team apply
3. **Zip modified files** — cho team không dùng git
4. **Copy docs** — share `docs/kien_audit/` cho team đọc
