"""Interface trừu tượng cho AI client (adapter pattern — CLAUDE.md mục 6).

AI CHỈ trích xuất dữ liệu theo mô tả field — trả JSON có cấu trúc + confidence +
evidence quote (CLAUDE.md mục 1). AI KHÔNG quyết định lưu vào dataset nào, có
trùng dữ liệu không, retry hay không — những việc đó nằm ở tầng gọi (rule-based).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class FieldExtraction:
    """Kết quả trích xuất 1 field."""

    value: Any
    confidence: float
    evidence: Optional[str] = None


@dataclass(frozen=True)
class ExtractionResult:
    """Kết quả trích xuất toàn bộ field được yêu cầu cho 1 trang."""

    fields: dict[str, FieldExtraction] = field(default_factory=dict)
    raw_response: Optional[str] = None
    success: bool = True
    error: Optional[str] = None


class AIClient(ABC):
    """Interface chung cho mọi AI client dùng ở bước classify/extract."""

    @abstractmethod
    def extract(self, markdown: str, field_descriptions: dict[str, str]) -> ExtractionResult:
        """Trích xuất các field được mô tả trong `field_descriptions`
        (tên field -> mô tả tự nhiên) từ nội dung `markdown` đã làm sạch.

        KHÔNG raise exception cho lỗi mạng/response không hợp lệ — trả về
        `ExtractionResult(success=False, error=...)`, giống quy ước của
        `FetchEngine.fetch()`."""
        raise NotImplementedError
