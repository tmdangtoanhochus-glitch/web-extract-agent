"""Interface trừu tượng cho tầng storage (adapter pattern — CLAUDE.md mục 6).

Schema dynamic qua JSON, KHÔNG tạo bảng SQL riêng từng job (CLAUDE.md mục 4):
- `datasets`: 1 dataset ứng với 1 "hình dạng" dữ liệu (schema_signature).
- `dataset_sources`: lịch sử các URL nguồn của 1 dataset — đổi nguồn = thêm dòng
  mới active=True, đánh dấu dòng cũ active=False, KHÔNG xóa (giữ audit).
- `records`: từng bản ghi dữ liệu thật, field linh hoạt nằm trong `data` (JSON).

Việc "khớp schema → dùng dataset cũ hay tạo dataset mới" và "gộp nguồn dữ liệu"
là quyết định nghiệp vụ rule-based, KHÔNG phải AI quyết định (CLAUDE.md mục 1).
`StorageEngine` chỉ thực thi theo lệnh gọi tường minh từ tầng gọi nó (vd. API sau
khi người dùng xác nhận), không tự ý gộp/suy luận thêm.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Dataset:
    dataset_id: str
    dataset_name: str
    schema_signature: list[str]
    created_at: datetime


@dataclass(frozen=True)
class DatasetSource:
    dataset_id: str
    source_url: str
    active: bool
    added_at: datetime


@dataclass(frozen=True)
class ExtractionStrategy:
    """"Chiến lược" extract đã cache cho 1 field trên 1 domain (CLAUDE.md mục
    5) — `selector` là CSS selector rule-based (xem `src/extract/selector_finder.py`),
    áp lại được KHÔNG cần gọi AI, chỉ gọi AI lại khi selector không còn khớp."""

    domain: str
    field_name: str
    selector: str
    sample_value: Optional[str]
    updated_at: datetime


@dataclass(frozen=True)
class ScheduledJob:
    """1 job crawl định kỳ (CLAUDE.md mục "Tech stack": APScheduler thay
    Celery+Redis cho MVP) — lưu lại để nạp lại đúng lịch sau khi app restart
    (`BackgroundScheduler` mặc định của APScheduler không tự lưu qua process).

    `trigger_type`/`trigger_args` truyền thẳng vào `apscheduler.add_job(func,
    trigger_type, **trigger_args)` — vd. `trigger_type="interval",
    trigger_args={"hours": 1}` hoặc `trigger_type="cron",
    trigger_args={"hour": 8, "minute": 0}`.

    `storage_mode` ("db" | "file") chọn lưu DB (`dataset_id` bắt buộc) hay ghi
    ra file (`file_path`/`write_mode`/`key_field` — không có `dataset_id`, xem
    "Lựa chọn lưu file" trong yêu cầu tính năng và `src/storage/file_writer.py`)
    — NGANG HÀNG, không phải ghi kép."""

    job_id: str
    url: str
    field_descriptions: dict[str, str]
    trigger_type: str
    trigger_args: dict[str, Any]
    enabled: bool
    created_at: datetime
    dataset_id: Optional[str] = None
    storage_mode: str = "db"
    file_path: Optional[str] = None
    write_mode: Optional[str] = None
    key_field: Optional[str] = None
    image_fields: list[str] = field(default_factory=list)
    crawl_options: Optional[dict] = None
    last_run_at: Optional[datetime] = None
    last_status: Optional[str] = None
    last_error_traceback: Optional[str] = None


@dataclass(frozen=True)
class AuditLogEntry:
    """1 dòng nhật ký dùng tính năng nội bộ (vd. panel admin "AI gợi ý sửa
    lỗi") — KHÔNG liên quan tới dữ liệu crawl/dataset, chỉ để theo dõi việc
    dùng các tính năng debug/admin."""

    id: str
    event_type: str
    job_id: Optional[str]
    occurred_at: datetime
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SiteCredential:
    """Cookie/session đăng nhập THỦ CÔNG cho 1 domain cần đăng nhập mới crawl
    được — người dùng tự đăng nhập bằng trình duyệt thật, copy cookie, dán
    vào (KHÔNG tự động điền form login, xem `src/fetch/httpx_fetcher.py`).
    Lưu theo domain, dùng lại cho mọi job (crawl 1 lần lẫn job lịch) cùng
    domain — người dùng tự cập nhật lại khi cookie hết hạn."""

    domain: str
    cookie_header: str
    updated_at: datetime


@dataclass(frozen=True)
class Record:
    """`needs_review`: `confidence` < `AI_CONFIDENCE_THRESHOLD` (mặc định 0.7,
    xem `src/config.py`) — CHỈ để cảnh báo người dùng qua UI/API, KHÔNG chặn
    lưu record (record vẫn lưu bình thường dù confidence thấp)."""

    record_id: str
    dataset_id: str
    source_url: str
    data: dict[str, Any]
    content_hash: str
    evidence: dict[str, Any] = field(default_factory=dict)
    confidence: Optional[float] = None
    needs_review: bool = False
    crawled_at: datetime = field(default_factory=utcnow)
    as_of: Optional[datetime] = None


class StorageEngine(ABC):
    """Interface chung cho mọi implementation storage (SQLite cho MVP, có thể
    thêm Postgres/MySQL sau — xem CLAUDE.md mục "Tech stack")."""

    # -- datasets --------------------------------------------------------
    @abstractmethod
    def create_dataset(self, dataset_name: str, schema_signature: list[str]) -> Dataset:
        raise NotImplementedError

    @abstractmethod
    def find_dataset_by_schema(self, schema_signature: list[str]) -> Optional[Dataset]:
        """So khớp schema_signature (không phân biệt thứ tự field) với dataset
        đã có — dùng khi quyết định lưu record vào dataset nào (CLAUDE.md mục 4)."""
        raise NotImplementedError

    @abstractmethod
    def get_dataset(self, dataset_id: str) -> Optional[Dataset]:
        raise NotImplementedError

    @abstractmethod
    def list_datasets(self) -> list[Dataset]:
        raise NotImplementedError

    # -- dataset_sources ---------------------------------------------------
    @abstractmethod
    def add_source(self, dataset_id: str, source_url: str) -> DatasetSource:
        """Thêm 1 nguồn active cho dataset — KHÔNG đụng tới các nguồn active
        khác của dataset này. 1 dataset có thể có nhiều nguồn active cùng lúc
        (vd. nhiều URL cùng schema đổ vào 1 dataset)."""
        raise NotImplementedError

    @abstractmethod
    def replace_source(
        self, dataset_id: str, old_source_url: str, new_source_url: str
    ) -> DatasetSource:
        """"Đổi nguồn" (CLAUDE.md mục 4): đánh dấu `old_source_url` thành
        active=False (KHÔNG xoá, giữ audit) rồi thêm `new_source_url` active.
        Chỉ gọi khi người dùng đã xác nhận tường minh muốn thay nguồn — bản
        thân storage không tự quyết định khi nào là "đổi nguồn"."""
        raise NotImplementedError

    @abstractmethod
    def list_sources(self, dataset_id: str, active_only: bool = False) -> list[DatasetSource]:
        raise NotImplementedError

    # -- records -----------------------------------------------------------
    @abstractmethod
    def save_record(
        self,
        dataset_id: str,
        source_url: str,
        data: dict[str, Any],
        content_hash: str,
        evidence: Optional[dict[str, Any]] = None,
        confidence: Optional[float] = None,
        needs_review: bool = False,
        as_of: Optional[datetime] = None,
    ) -> Record:
        raise NotImplementedError

    @abstractmethod
    def get_latest_record_for_source(self, dataset_id: str, source_url: str) -> Optional[Record]:
        """Lấy record mới nhất của 1 nguồn — tầng gọi tự so `content_hash` với
        record này để quyết định có phải lưu record mới hay không (change
        detection là rule-based, không nằm trong storage)."""
        raise NotImplementedError

    @abstractmethod
    def list_records(self, dataset_id: str, limit: int = 100, offset: int = 0) -> list[Record]:
        raise NotImplementedError

    def export_record_page(self, dataset_id: str, cutoff: datetime,
                           after: Optional[tuple[datetime, str]] = None,
                           limit: int = 500) -> list[Record]:
        """Stable keyset pagination for append-only records at or before cutoff."""
        raise NotImplementedError

    # -- extraction_strategies (cache CLAUDE.md mục 5) ----------------------
    @abstractmethod
    def get_extraction_strategy(self, domain: str, field_name: str) -> Optional[ExtractionStrategy]:
        """`None` nếu chưa từng cache chiến lược cho field này trên domain
        này — tầng gọi (`pipeline.py`) fallback sang AI khi đó."""
        raise NotImplementedError

    @abstractmethod
    def save_extraction_strategy(
        self, domain: str, field_name: str, selector: str, sample_value: Optional[str] = None
    ) -> ExtractionStrategy:
        """Lưu/ghi đè chiến lược cho (domain, field_name) — gọi lại mỗi khi AI
        vừa tìm được vị trí field mới, kể cả khi ghi đè 1 chiến lược cũ đã
        fail (site đổi cấu trúc)."""
        raise NotImplementedError

    # -- scheduled_jobs (APScheduler — xem src/scheduler.py) ----------------
    @abstractmethod
    def create_scheduled_job(
        self,
        dataset_id: Optional[str],
        url: str,
        field_descriptions: dict[str, str],
        trigger_type: str,
        trigger_args: dict[str, Any],
        storage_mode: str = "db",
        file_path: Optional[str] = None,
        write_mode: Optional[str] = None,
        key_field: Optional[str] = None,
        image_fields: Optional[list[str]] = None,
        crawl_options: Optional[dict] = None,
    ) -> ScheduledJob:
        """`dataset_id` chỉ bắt buộc khi `storage_mode="db"` — `None` cho job
        `storage_mode="file"` (không tạo dataset cho luồng file). `image_fields`:
        field nào người dùng đã đánh dấu tường minh là ảnh cần tải về (xem
        `src/storage/image_downloader.py`), áp dụng lại mỗi lần job chạy."""
        raise NotImplementedError

    @abstractmethod
    def get_scheduled_job(self, job_id: str) -> Optional[ScheduledJob]:
        raise NotImplementedError

    @abstractmethod
    def list_scheduled_jobs(self, enabled_only: bool = False) -> list[ScheduledJob]:
        raise NotImplementedError

    @abstractmethod
    def update_scheduled_job_run(
        self, job_id: str, status: str, traceback_text: Optional[str] = None
    ) -> None:
        """Ghi lại kết quả lần chạy gần nhất (`last_run_at`=now, `last_status`,
        `last_error_traceback` nếu có) — gọi sau MỖI lần `CrawlScheduler` chạy
        job, kể cả khi lỗi."""
        raise NotImplementedError

    @abstractmethod
    def delete_scheduled_job(self, job_id: str) -> None:
        raise NotImplementedError

    def configure_scheduled_job(self, job_id: str, enabled: bool,
                                trigger_type: str, trigger_args: dict) -> None:
        """Update timing/enabled only; preserve source, destination and run history."""
        raise NotImplementedError

    # -- audit_log (dùng cho panel admin "AI gợi ý sửa lỗi") ----------------
    @abstractmethod
    def add_audit_log(
        self, event_type: str, job_id: Optional[str] = None, detail: Optional[dict[str, Any]] = None
    ) -> AuditLogEntry:
        raise NotImplementedError

    @abstractmethod
    def list_audit_log(self, job_id: Optional[str] = None, limit: int = 100) -> list[AuditLogEntry]:
        raise NotImplementedError

    # -- site_credentials (cookie đăng nhập thủ công theo domain) -----------
    @abstractmethod
    def save_site_credential(self, domain: str, cookie_header: str) -> SiteCredential:
        """Lưu/ghi đè cookie cho 1 domain — ghi đè hoàn toàn cookie cũ (nếu có)."""
        raise NotImplementedError

    @abstractmethod
    def get_site_credential(self, domain: str) -> Optional[SiteCredential]:
        raise NotImplementedError

    @abstractmethod
    def list_site_credentials(self) -> list[SiteCredential]:
        raise NotImplementedError

    @abstractmethod
    def delete_site_credential(self, domain: str) -> None:
        raise NotImplementedError
