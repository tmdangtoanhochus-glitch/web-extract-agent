"""Interface trừu tượng cho tầng fetch (adapter pattern — xem CLAUDE.md mục 6).

Mọi engine fetch thật (httpx cho site tĩnh, Playwright cho site JS-heavy sau này)
đều implement `FetchEngine`, để scheduler/route handler gọi qua interface chung,
không phụ thuộc trực tiếp vào thư viện cụ thể.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FetchResult:
    """Kết quả 1 lần fetch — thành công hay thất bại đều trả về object này,
    không raise exception cho lỗi mạng/HTTP thường gặp (timeout, 4xx/5xx)."""

    url: str
    final_url: str
    status_code: Optional[int]
    html: Optional[str]
    fetched_at: datetime
    success: bool
    error: Optional[str] = None


class RobotsChecker(ABC):
    """Interface kiểm tra robots.txt trước khi fetch một URL."""

    @abstractmethod
    def can_fetch(self, url: str, user_agent: str) -> bool:
        """Trả về True nếu user_agent được phép fetch url theo robots.txt."""
        raise NotImplementedError


class AllowAllRobotsChecker(RobotsChecker):
    """LUÔN cho phép fetch, KHÔNG tải/parse robots.txt — chỉ dùng làm test
    double khi test không cần quan tâm hành vi robots.txt (vd. test cơ chế
    fetch/parse HTML), hoặc dev cục bộ.

    KHÔNG phải default của `HttpxFetcher` (default thật là `HttpRobotsChecker`
    ở `src/fetch/robots.py`, có tải + parse robots.txt — CLAUDE.md mục 3: mặc
    định phải luôn kiểm tra, không phải toggle). Muốn dùng class này cho crawl
    thật phải tự truyền tường minh `robots_checker=AllowAllRobotsChecker()`
    khi khởi tạo `HttpxFetcher` — không có cờ bật/tắt ẩn nào.
    """

    def can_fetch(self, url: str, user_agent: str) -> bool:
        logger.warning(
            "AllowAllRobotsChecker (stub) đang được dùng cho %s — CHƯA kiểm tra "
            "robots.txt thật, chỉ dùng cho dev/test.",
            url,
        )
        return True


class FetchEngine(ABC):
    """Interface chung cho mọi engine fetch (httpx, Playwright, ...)."""

    @abstractmethod
    def fetch(self, url: str) -> FetchResult:
        raise NotImplementedError


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def domain_of(url: str) -> str:
    """Dùng chung cho `HttpxFetcher`/`PlaywrightFetcher`/`pipeline.py` (rate
    limit, robots.txt, cache chiến lược extract theo domain — CLAUDE.md mục 3+5)."""
    return urlparse(url).netloc
