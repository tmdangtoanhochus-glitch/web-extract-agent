# 03 — Multi-Record Extraction + Export Fixes

> **Date:** 2026-09-16  
> **Reporter:** Kiên  
> **Severity:** HIGH — core functionality broken for listing pages

---

## 1. Issues Reported

| # | Issue | Root Cause |
|---|-------|------------|
| 1 | Chỉ kéo được 1 quote đầu, không kéo toàn page | AI prompt yêu cầu "1 JSON object" → chỉ trả 1 record |
| 2 | File XLSX lưu ra hỏng, không mở được | CSV thiếu UTF-8 BOM; không có XLSX export |
| 3 | books.toscrape.com không kéo được | AI trả `null` vì nhận ra "trang list 20 sách" + robots.txt block trong backend |

---

## 2. Root Cause Analysis

### 2.1. Single-Record AI Prompt

**File:** `src/ai/greennode_client.py:39-48`

System prompt yêu cầu:
> "CHỈ trả lời bằng 1 JSON object duy nhất"

AI chỉ trả 1 bản ghi dù trang có 10 quotes hoặc 20 sách.

### 2.2. Pipeline Single-Record Design

**File:** `src/pipeline.py:217-231`

`run_crawl_job()` chỉ save 1 record per crawl:
```python
data = {name: fe.value for name, fe in extraction.fields.items()}
record = storage.save_record(...)
return PipelineResult(status="saved", dataset=dataset, record=record)
```

### 2.3. books.toscrape.com AI Response

AI trả `null` cho tất cả fields với evidence:
> "This is a product listing page containing 20 books, not a single book detail page."

AI đủ thông minh để biết không nên trả 1 sách khi có 20, nhưng prompt bắt trả 1 object.

### 2.4. CSV Export Missing BOM

**File:** `ui/app.py:437-457`

`_records_to_csv()` trả string không có UTF-8 BOM (`\ufeff`). Excel không nhận diện UTF-8 → font lỗi/tiếng Việt hỏng.

### 2.5. No XLSX Export

UI chỉ có nút "Tải CSV". Không có XLSX export dù `pandas` + `openpyxl` đã có trong `requirements.txt`.

### 2.6. Robots.txt Block in Backend

**File:** `src/api/main.py:289-292`

`_build_default_app()` không truyền `robots_checker` → mặc định `HttpRobotsChecker()`. Backend process không fetch được `robots.txt` (network restriction) → fail-closed → block all crawl.

Setting `FETCH_RESPECT_ROBOTS_TXT` trong `.env` được load nhưng **không bao giờ dùng**.

### 2.7. Selector Cache Poisoning

**File:** `src/pipeline.py:115-125`

Lần crawl trước cache CSS selector cho field "quote" → selector trỏ tới element quote đầu. Lần crawl sau, `ai_extract()` tìm thấy cached selector → extract value quote đầu → **skip AI** → chỉ 1 record.

---

## 3. Fixes Applied

### 3.1. AI Prompt → Array of Records

**File:** `src/ai/greennode_client.py:39-48`

Changed `_SYSTEM_PROMPT` to request JSON array:
> "Trả về 1 JSON array, mỗi phần tử là 1 object... Nếu trang chỉ có 1 bản ghi, trả về array 1 phần tử."

### 3.2. AI Parsing → Multiple Records

**File:** `src/ai/greennode_client.py:128-169` (new `_parse_json` + `_to_records`)

- `_parse_json()`: Handles both JSON array and single object (backward compat)
- `_to_records()`: Returns `list[dict[str, FieldExtraction]]` instead of single dict

### 3.3. ExtractionResult → Records List

**File:** `src/ai/base.py:24-37`

Added `records: list[dict[str, FieldExtraction]]` field. `fields` property maintained for backward compat (returns first record).

### 3.4. Pipeline → Save Multiple Records

**File:** `src/pipeline.py`

- `AiExtractResult.records`: list of field dicts
- `ai_extract()`: merges structured data/cache fields with each AI record
- `run_crawl_job()`: loops through `extraction.records`, saves each to DB
- `run_file_crawl_job()`: loops through records, writes each to file
- `PipelineResult.record_count` / `FileCrawlResult.record_count`: new field

### 3.5. API Response → Record Count

**File:** `src/api/main.py:50-59`

Added `record_count: int` to `CrawlResponse`.

### 3.6. CSV UTF-8 BOM

**File:** `ui/app.py:437-457`

Added `"\ufeff" +` prefix to CSV output for Excel UTF-8 compatibility.

### 3.7. XLSX Export

**File:** `ui/app.py:460-477`

New `_records_to_xlsx()` function using `pandas.to_excel()` with `openpyxl` engine. Added "⬇ Tải XLSX" download button in Step 4.

### 3.8. Robots.txt Setting Respected

**File:** `src/api/main.py:287-310`

`_build_default_app()` now checks `settings.fetch_respect_robots_txt`:
- `true` → `HttpRobotsChecker()` (default, real robots.txt check)
- `false` → `AllowAllRobotsChecker()` (skip robots.txt)

**File:** `.env` — set `FETCH_RESPECT_ROBOTS_TXT=false` for dev/test.

### 3.9. AI Timeout + Max Tokens

**File:** `.env` — `AI_TIMEOUT_SECONDS=120` (was 30)
**File:** `src/ai/greennode_client.py:64` — `max_tokens=8192` (was 2048)

Multiple records need more tokens and time.

---

## 4. Files Modified

| File | Change |
|------|--------|
| `src/ai/base.py` | `ExtractionResult.records` list + `fields` property |
| `src/ai/greennode_client.py` | Array prompt, `_parse_json`, `_to_records`, `max_tokens=8192` |
| `src/pipeline.py` | Multi-record `ai_extract`, `run_crawl_job`, `run_file_crawl_job` |
| `src/api/main.py` | `record_count` in response, `FETCH_RESPECT_ROBOTS_TXT` honored |
| `ui/app.py` | CSV BOM, XLSX export button |
| `.env` | `FETCH_RESPECT_ROBOTS_TXT=false`, `AI_TIMEOUT_SECONDS=120` |

---

## 5. Test Results

### quotes.toscrape.com
```
Status: 200, record_count: 10
Total in DB: 10
  Steve Martin: A day without sunshine is like, you know, night....
  Eleanor Roosevelt: A woman is like a tea bag; you never know how stro...
  Thomas A. Edison: I have not failed. I've just found 10,000 ways tha...
  ... +7 more
```

### books.toscrape.com
```
Status: 200, record_count: 20
Total in DB: 20
  It's Only the Himalayas: £45.17
  Libertarianism for Beginners: £51.33
  Mesaerion: The Best Science ...: £37.59
  ... +17 more
```

### CSV/XLSX Export
- CSV: UTF-8 BOM added → Excel opens correctly
- XLSX: New export button using pandas + openpyxl

---

## 6. Known Limitations

1. **Selector cache** still caches single-element selectors. If cache exists from a previous single-record crawl, subsequent crawls may return 1 record. **Workaround:** delete `data/app.db` or use new dataset name.
2. **AI token limit**: 8192 tokens may not be enough for very large pages (100+ items). May need pagination or chunking.
3. **AI timeout**: 120s timeout may still be too short for very large pages. Monitor and adjust.
4. **robots.txt disabled**: `FETCH_RESPECT_ROBOTS_TXT=false` in `.env` for dev. **Must set back to `true` for production.**
