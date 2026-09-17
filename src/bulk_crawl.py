"""Bounded historical pulls and HTML tables; schedules reuse this exact pipeline."""
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
from functools import wraps
from threading import RLock
from typing import Literal
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, Field, model_validator
import soupsieve

from .pipeline import run_crawl_job, run_file_crawl_job
from .storage.file_writer import write_record


_bulk_lock = RLock()


class TableError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def serialized(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        # Existing scheduler deployment uses one API worker. Prevent overlapping
        # manual/scheduled pulls from observing the same pre-insert snapshot.
        with _bulk_lock:
            return function(*args, **kwargs)
    return wrapped


class CrawlOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["fields", "table"] = "fields"
    start_date: date | None = None
    end_date: date | None = None
    window_days: int = Field(default=1, ge=1, le=366)
    lookback_days: int | None = Field(default=None, ge=1, le=366)
    page_start: int = Field(default=1, ge=0, le=100000)
    pages: int = Field(default=1, ge=1, le=100)
    table_selector: str = Field(default="table", min_length=1, max_length=500)
    columns: dict[str, int] = Field(default_factory=dict)
    date_field: str | None = None
    date_format: str = Field(default="%Y-%m-%d", max_length=80)
    max_rows: int = Field(default=1000, ge=1, le=10000)

    @model_validator(mode="after")
    def valid(self):
        if bool(self.start_date) != bool(self.end_date):
            raise ValueError("Cần cả ngày bắt đầu và kết thúc")
        if self.start_date and self.start_date > self.end_date:
            raise ValueError("Ngày bắt đầu phải trước ngày kết thúc")
        if self.lookback_days and self.start_date:
            raise ValueError("Chọn khoảng cố định hoặc khoảng gần nhất")
        if any(n < 1 or n > 500 for n in self.columns.values()):
            raise ValueError("Số cột phải từ 1 đến 500")
        if self.mode == "table":
            try:
                soupsieve.compile(self.table_selector)
            except soupsieve.SelectorSyntaxError as exc:
                raise ValueError("CSS selector không hợp lệ") from exc
            if not self.columns:
                raise ValueError("Cần ánh xạ field sang số cột của bảng")
        return self


def plan_urls(url, options, today=None):
    """Inclusive date windows. No inferred query parameters or invented history."""
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        raise ValueError("URL nguồn phải là HTTP(S), không chứa thông tin đăng nhập")
    if "{" in parts.netloc or "}" in parts.netloc:
        raise ValueError("Placeholder chỉ được dùng trong đường dẫn hoặc query")
    start, end = options.start_date, options.end_date
    if options.lookback_days:
        end = today or datetime.now(timezone.utc).date()
        start = end - timedelta(days=options.lookback_days - 1)
    if options.pages > 1 and "{page}" not in url:
        raise ValueError("Nhiều trang cần {page} trong URL")
    if start and not any(p in url for p in ("{start}", "{end}")) and not (options.mode == "table" and options.date_field):
        raise ValueError("Khoảng ngày cần URL {start}/{end} hoặc cột ngày để lọc bảng")
    windows = [(start, end)]
    if start and any(p in url for p in ("{start}", "{end}")):
        windows = []
        cursor = start
        while cursor <= end:
            stop = cursor + timedelta(days=min(options.window_days - 1, (end - cursor).days))
            windows.append((cursor, stop))
            if len(windows) * options.pages > 100:
                raise ValueError("Tối đa 100 lượt mỗi đợt; chia nhỏ khoảng ngày")
            if stop == end:
                break
            cursor = stop + timedelta(days=1)
    plans = []
    for first, last in windows:
        for page in range(options.page_start, options.page_start + options.pages):
            target = url.replace("{page}", str(page))
            if first:
                target = target.replace("{start}", first.isoformat()).replace("{end}", last.isoformat())
            if "{" in target or "}" in target:
                raise ValueError("Placeholder chưa hợp lệ; dùng {start}, {end}, {page}")
            plans.append((target, first, last))
    return plans


def table_rows(html, options, first, last):
    tables = BeautifulSoup(html, "html.parser").select(options.table_selector)
    if len(tables) != 1 or tables[0].name != "table":
        raise TableError("table_selection", "Selector phải khớp đúng một bảng HTML")
    rows = []
    for tr in tables[0].find_all("tr"):
        if tr.find_parent("table") is not tables[0]:
            continue
        cells = tr.find_all(["td", "th"], recursive=False)
        if not cells or all(cell.name == "th" for cell in cells):
            continue
        if any(cell.get("rowspan", "1") != "1" or cell.get("colspan", "1") != "1" for cell in cells):
            raise TableError("merged_cells", "Bảng có ô gộp; cần cấu hình nguồn bảng phẳng")
        if max(options.columns.values()) > len(cells):
            raise TableError("column_count", "Số cột cấu hình vượt số ô trong dòng")
        data = {name: cells[index - 1].get_text(" ", strip=True) for name, index in options.columns.items()}
        as_of = None
        if options.date_field:
            try:
                parsed = datetime.strptime(data[options.date_field], options.date_format).date()
            except (ValueError, KeyError):
                raise TableError("date_format", "Ngày trong bảng không khớp định dạng đã chọn") from None
            if first and not first <= parsed <= last:
                continue
            as_of = datetime.combine(parsed, time.min, timezone.utc)
        rows.append((data, as_of))
        if len(rows) > options.max_rows:
            raise TableError("row_limit", "Bảng vượt giới hạn dòng; chia nhỏ nguồn hoặc tăng max_rows")
    return rows


def validate_options(field_descriptions, options, storage_mode, write_mode, image_fields):
    if not field_descriptions or storage_mode not in {"db", "file"}:
        raise ValueError("Cần khai báo field và nơi lưu hợp lệ")
    if options.mode == "table" and set(options.columns) != set(field_descriptions):
        raise ValueError("Ánh xạ cột phải khớp tất cả field")
    if options.date_field and options.date_field not in options.columns:
        raise ValueError("Cột ngày phải thuộc bảng")
    if options.mode == "table" and image_fields:
        raise ValueError("Bảng hiện lưu nội dung ô; bỏ chọn tải ảnh")
    if storage_mode == "file" and write_mode != "append":
        raise ValueError("Kéo nhiều lượt dùng file append để không ghi đè dữ liệu")


def preview_bulk(*, url, options, field_descriptions, fetcher, storage_mode="db",
                 write_mode="append", image_fields=None):
    validate_options(field_descriptions, options, storage_mode, write_mode, image_fields)
    plans = plan_urls(url, options)
    result = {"status": "preview", "requests": len(plans), "sample": [],
              "plan": [{"index": i, "start": first.isoformat() if first else None,
                        "end": last.isoformat() if last else None,
                        "page": options.page_start + (i - 1) % options.pages}
                       for i, (_, first, last) in enumerate(plans, 1)], "fetched_pages": 0}
    if options.mode == "table":
        target, first, last = plans[0]
        fetched = fetcher.fetch(target)
        if not fetched.success or fetched.html is None:
            raise TableError("fetch_failed", "Không tải được trang bảng đầu tiên; kiểm tra nguồn và phiên đăng nhập")
        rows = table_rows(fetched.html, options, first, last)
        result.update(sample=[data for data, _ in rows[:10]], matched_rows=len(rows), fetched_pages=1)
    return result


@serialized
def run_bulk(*, url, field_descriptions, options, fetcher, ai_client, storage,
             dataset_id=None, dataset_name=None, storage_mode="db", file_path=None,
             write_mode="append", key_field=None, confidence_threshold=0.7, image_fields=None,
             retry_indices=None, checkpoint=None, progress=None):
    plans = plan_urls(url, options)
    validate_options(field_descriptions, options, storage_mode, write_mode, image_fields)
    indexed_plans = list(enumerate(plans, 1))
    if retry_indices is not None:
        if (not retry_indices or not set(retry_indices) <= set(range(1, len(plans) + 1))
                or storage_mode != "db" or options.mode != "table" or not dataset_id or options.lookback_days):
            raise ValueError("Chỉ chạy lại lượt lỗi của bảng DB với dataset và khoảng ngày cố định")
        indexed_plans = [(i, plan) for i, plan in indexed_plans if i in retry_indices]
    dataset = None
    if storage_mode == "db":
        dataset = storage.get_dataset(dataset_id) if dataset_id else None
        if dataset_id and not dataset:
            raise ValueError("Dataset không tồn tại")
        if dataset and dataset.schema_signature != sorted(field_descriptions):
            raise ValueError("Schema dataset không khớp")
        if not dataset:
            if not dataset_name:
                raise ValueError("Cần tên dataset")
            dataset = storage.create_dataset(dataset_name, sorted(field_descriptions))
        dataset_id = dataset.dataset_id
    # Full history, paginated: overlapping windows and reruns must not duplicate rows.
    seen = set()
    if dataset and options.mode == "table":
        offset = 0
        while True:
            records = storage.list_records(dataset_id, limit=1000, offset=offset)
            seen.update(r.content_hash for r in records)
            if len(records) < 1000:
                break
            offset += len(records)
    results, saved, skipped = [], 0, 0
    cancelled = False
    sources = {source.source_url for source in storage.list_sources(dataset_id, active_only=True)} if dataset else set()
    for index, (target, first, last) in indexed_plans:
        if checkpoint:
            # Release the batch serialization lock while a user pauses so other
            # users and scheduled crawls can proceed. Refresh dedup after reacquiring.
            _bulk_lock.release()
            try:
                proceed = checkpoint()
            finally:
                _bulk_lock.acquire()
            if not proceed:
                cancelled = True
                break
            if dataset and options.mode == "table":
                offset = 0
                while True:
                    current = storage.list_records(dataset_id, limit=1000, offset=offset)
                    seen.update(r.content_hash for r in current)
                    if len(current) < 1000:
                        break
                    offset += len(current)
        if progress:
            progress({"requests": len(indexed_plans), "processed": len(results), "current_index": index,
                      "saved": saved, "skipped": skipped, "dataset_id": dataset_id})
        stage = "fetch"
        try:
            if options.mode == "fields":
                common = dict(url=target, field_descriptions=field_descriptions, fetcher=fetcher,
                              ai_client=ai_client, storage=storage, confidence_threshold=confidence_threshold,
                              image_fields=image_fields)
                result = (run_crawl_job(**common, dataset_id=dataset_id) if dataset else
                          run_file_crawl_job(**common, file_path=file_path, write_mode="append"))
                status = result.status
                saved += status == "saved"
                skipped += status == "unchanged"
            else:
                fetched = fetcher.fetch(target)
                if not fetched.success or fetched.html is None:
                    raise RuntimeError("fetch_failed")
                rows = table_rows(fetched.html, options, first, last)
                stage = "save"
                if dataset and target not in sources:
                    storage.add_source(dataset_id, target)
                    sources.add(target)
                for data, as_of in rows:
                    digest = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                    if dataset:
                        if digest in seen:
                            skipped += 1
                            continue
                        storage.save_record(dataset_id, target, data, digest, confidence=1.0, as_of=as_of)
                        seen.add(digest)
                    else:
                        write_record(file_path=file_path, record={"source_url": target, "data": data,
                                     "crawled_at": datetime.now(timezone.utc).isoformat()},
                                     write_mode="append", field_names=list(field_descriptions))
                    saved += 1
                status = "saved" if rows else "empty"
            results.append({"index": index, "status": status})
        except Exception as exc:
            # No source content, request headers or exception message in reports.
            results.append({"index": index, "status": "error", "error_type": type(exc).__name__,
                            "error_code": exc.code if isinstance(exc, TableError) else f"{stage}_failed",
                            "detail": str(exc) if isinstance(exc, TableError) else
                            ("Không lưu được dữ liệu; báo admin trước khi thử lại" if stage == "save" else
                             "Không tải được nguồn; kiểm tra URL, cookie hoặc báo admin")})
        if progress:
            progress({"processed": len(results), "saved": saved, "skipped": skipped,
                      "failed": sum(r["status"] not in {"saved", "unchanged", "empty"} for r in results)})
    failed = sum(r["status"] not in {"saved", "unchanged", "empty"} for r in results)
    return {"status": "cancelled" if cancelled else "partial" if failed else "completed", "dataset_id": dataset_id,
            "file_path": file_path, "saved": saved, "skipped": skipped, "failed": failed,
            "requests": len(indexed_plans), "results": results}
