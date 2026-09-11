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
class Record:
    record_id: str
    dataset_id: str
    source_url: str
    data: dict[str, Any]
    content_hash: str
    evidence: dict[str, Any] = field(default_factory=dict)
    confidence: Optional[float] = None
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
