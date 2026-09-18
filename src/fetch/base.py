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


class OverrideRobotsChecker(RobotsChecker):
    """Bỏ qua robots.txt CHỈ cho đúng 1 domain, có lý do bắt buộc (CLAUDE.md mục
    3: hành động tường minh + cảnh báo + ghi log, không phải toggle im lặng).
    Domain khác vẫn đi qua checker gốc. Mỗi lần áp dụng đều log WARNING."""

    def __init__(self, inner: RobotsChecker, domain: str, reason: str) -> None:
        self._inner = inner
        self._domain = domain
        self._reason = reason

    def can_fetch(self, url: str, user_agent: str) -> bool:
        if domain_of(url) == self._domain:
            logger.warning(
                "BỎ QUA robots.txt cho %s theo yêu cầu tường minh của người dùng. Lý do: %s",
                url, self._reason,
            )
            return True
        return self._inner.can_fetch(url, user_agent)


class FetchEngine(ABC):
    """Interface chung cho mọi engine fetch (httpx, Playwright, ...)."""

    @abstractmethod
    def fetch(self, url: str) -> FetchResult:
        raise NotImplementedError


class HybridFetcher(FetchEngine):
    """Thử httpx trước (nhanh); nếu fail (403/5xx/HTML quá nhỏ) → fallback
    Playwright (chậm nhưng render JS + bypass block)."""

    def __init__(self, primary: FetchEngine, fallback: FetchEngine, min_html: int = 2000, min_markdown_ratio: float = 0.01):
        self._primary = primary
        self._fallback = fallback
        self._min_html = min_html
        self._min_markdown_ratio = min_markdown_ratio

    def fetch(self, url: str) -> FetchResult:
        result = self._primary.fetch(url)
        need_fallback = (
            not result.success
            or result.html is None
            or (result.status_code is not None and result.status_code in (403, 429) or (result.status_code is not None and result.status_code >= 500))
            or len(result.html or "") < self._min_html
        )
        if not need_fallback and result.html:
            try:
                from ..clean.html_cleaner import clean_html
                cleaned = clean_html(result.html)
                if len(result.html) > 10000 and len(cleaned.markdown) < len(result.html) * self._min_markdown_ratio:
                    logger.info("HTML lớn nhưng markdown quá ngắn cho %s — JS-heavy, fallback Playwright.", url)
                    need_fallback = True
            except Exception:
                pass
        if need_fallback:
            logger.info("httpx fail/empty cho %s — fallback Playwright.", url)
            return self._fallback.fetch(url)
        return result

    def with_request_cookie(self, url: str, cookie: str) -> "HybridFetcher":
        clone = HybridFetcher(self._primary, self._fallback, self._min_html, self._min_markdown_ratio)
        if hasattr(self._primary, "with_request_cookie"):
            clone._primary = self._primary.with_request_cookie(url, cookie)
        if hasattr(self._fallback, "with_request_cookie"):
            clone._fallback = self._fallback.with_request_cookie(url, cookie)
        return clone


def _hybrid_with_robots_ignored(self, domain: str, reason: str) -> "HybridFetcher":
    clone = HybridFetcher(self._primary, self._fallback, self._min_html, self._min_markdown_ratio)
    for attr in ("_primary", "_fallback"):
        engine = getattr(self, attr)
        if hasattr(engine, "with_robots_ignored"):
            setattr(clone, attr, engine.with_robots_ignored(domain, reason))
    return clone


HybridFetcher.with_robots_ignored = _hybrid_with_robots_ignored


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def domain_of(url: str) -> str:
    """Dùng chung cho `HttpxFetcher`/`PlaywrightFetcher`/`pipeline.py` (rate
    limit, robots.txt, cache chiến lược extract theo domain — CLAUDE.md mục 3+5)."""
    return urlparse(url).netloc
