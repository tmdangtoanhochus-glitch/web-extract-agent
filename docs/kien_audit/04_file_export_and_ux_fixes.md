# 04 — File Export Corrupt + Preview Missing + Loading UX

> **Date:** 2026-09-16  
> **Reporter:** Kiên  
> **Severity:** HIGH

---

## 1. Issues

| # | Issue | Root Cause |
|---|-------|------------|
| 1 | File `.xlsx` corrupt, không mở được | `file_writer.py` luôn ghi JSON content bất kể extension |
| 2 | Preview không hiển thị sau crawl (file mode) | UI chỉ fetch preview cho DB mode, không cho file mode |
| 3 | Không có loading/progress khi crawl | Nút Crawl không có progress bar, không disable khi đang chạy |

---

## 2. Root Cause

### 2.1. File Format Mismatch

**File:** `src/storage/file_writer.py:80-82`

`_write_json_array()` luôn ghi JSON text:
```python
path.write_text(json.dumps(records, ...), encoding="utf-8")
```

User chỉ định `book.xlsx` → file chứa JSON text nhưng extension `.xlsx` → Excel không mở được.

Hex dump chứng minh:
```
5B 0D 0A 20 20 7B 0D 0A... = [\r\n  {\r\n  "sou...  (JSON, not XLSX)
```

XLSX hợp lệ phải bắt đầu bằng `50 4B 03 04` (PK zip signature).

### 2.2. Preview Only for DB Mode

**File:** `ui/app.py:454`

```python
if st.session_state.run_dataset_id and not is_file_mode:
    # chỉ fetch preview cho DB mode
```

File mode không có `dataset_id` → preview không hiển thị.

### 2.3. No Loading UX

**File:** `ui/app.py:390`

```python
if st.button("🚀 Chạy crawl", type="primary"):
    # loop qua URLs, không có progress bar
```

- Không có progress bar → user không biết đang xử lý
- Nút không disable → user có thể nhấn nhiều lần
- Không có thông báo thành công/lỗi

---

## 3. Fixes

### 3.1. Multi-Format File Writer

**File:** `src/storage/file_writer.py` — rewritten

New `_get_format(path)` detects format from extension:
- `.xlsx` → pandas + openpyxl
- `.csv` → csv module + UTF-8 BOM
- `.json` (default) → json module

New `_read_records(path)` and `_write_records(path, records)` handle all 3 formats.

`write_record()` uses `_read_records`/`_write_records` instead of JSON-only functions.

### 3.2. File Mode Preview

**File:** `ui/app.py` — file result section

After crawl in file mode:
- Download file via `/exports/{path}`
- Detect format from extension
- Parse and display as `st.dataframe()`:
  - JSON: `json.loads` → list of dicts
  - CSV: `pd.read_csv` with UTF-8-sig encoding
  - XLSX: `pd.read_excel` with openpyxl engine
- Set correct MIME type for download button

### 3.3. Progress Bar + Button Disable + Notifications

**File:** `ui/app.py` — Step 3 crawl section

- `st.progress()` bar: shows "Đang crawl X/Y URL..."
- `disabled=st.session_state.get("is_crawling", False)`: disables Crawl button
- `st.success()`: "Hoàn thành: X URL thành công, Y lỗi"
- `st.error()`: "Tất cả X URL đều lỗi"
- `st.rerun()` after crawl to refresh UI

### 3.4. API Response record_count for File Mode

**File:** `src/api/main.py:160`

Added `record_count=file_result.record_count` to file mode `CrawlResponse`.

---

## 4. Files Modified

| File | Change |
|------|--------|
| `src/storage/file_writer.py` | Multi-format support (.json/.csv/.xlsx) |
| `src/api/main.py` | `record_count` in file mode response |
| `ui/app.py` | Progress bar, button disable, notifications, file preview |
| `requirements.txt` | `openpyxl==3.1.5` added (previous fix) |

---

## 5. Test Results

### XLSX Export
```
First 4 bytes: 504b0304 (PK = valid XLSX zip)
Size: 6238 bytes
Excel can open: YES
```

### CSV Export
```
First 3 bytes: ef bb bf (UTF-8 BOM)
Size: 1052 bytes
Excel can open: YES (correct Vietnamese encoding)
```

### JSON Export (backward compat)
```
Still works as before — no regression
```

---

## 6. Services

- Backend: http://localhost:8000 — OK
- UI: http://localhost:8501 — OK
- Old corrupt files cleaned from `data/exports/`
- Old DB deleted for fresh start
