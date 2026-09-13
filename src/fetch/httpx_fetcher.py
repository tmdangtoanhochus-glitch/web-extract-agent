"""Fetch engine dùng httpx — cho site tĩnh (không cần chạy JS).

Site JS-heavy dùng `PlaywrightFetcher` (xem `src/fetch/playwright_fetcher.py`)
thay vì engine này.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from .base import FetchEngine, FetchResult, RobotsChecker, domain_of, utcnow
from .rate_limiter import DomainRateLimiter
from .robots import HttpRobotsChecker

logger = logging.getLogger(__name__)


class HttpxFetcher(FetchEngine):
    """Fetch site tĩnh bằng httpx.

    `client` cho phép inject 1 `httpx.Client` có sẵn (vd. dùng `httpx.MockTransport`
    khi test) thay vì luôn tạo client thật — theo adapter/test-double pattern ở
    CLAUDE.md mục 6.

    `robots_checker` mặc định là `HttpRobotsChecker` (tải + parse robots.txt
    thật, xem `src/fetch/robots.py`) — LUÔN bật kiểm tra theo CLAUDE.md mục 3,
    không phải checkbox tắt/bật. Test/dev muốn bỏ qua robots.txt phải tự truyền
    tường minh `robots_checker=AllowAllRobotsChecker()` (xem `src/fetch/base.py`),
    không có cờ bật/tắt ẩn nào ở đây.

    `delay_seconds` là khoảng cách TỐI THIỂU (giây) giữa 2 lần fetch cùng
    domain (CLAUDE.md mục 3) — mặc định 0 (không giới hạn); app thật nên
    truyền `settings.fetch_default_delay_seconds` (xem `src/api/main.py`).
    Rate-limit dùng chung `DomainRateLimiter` (xem `src/fetch/rate_limiter.py`)
    với `PlaywrightFetcher`.
    """

    def __init__(
        self,
        user_agent: str,
        timeout_seconds: float = 30.0,
        robots_checker: Optional[RobotsChecker] = None,
        client: Optional[httpx.Client] = None,
        delay_seconds: float = 0.0,
    ) -> None:
        self._user_agent = user_agent
        self._timeout_seconds = timeout_seconds
        self._robots_checker = robots_checker or HttpRobotsChecker()
        self._injected_client = client
        self._rate_limiter = DomainRateLimiter(delay_seconds)

    def _wait_for_domain(self, url: str) -> None:
        self._rate_limiter.wait(domain_of(url))

    def fetch(self, url: str) -> FetchResult:
        if not self._robots_checker.can_fetch(url, self._user_agent):
            logger.info("Bỏ qua fetch %s — bị chặn bởi robots.txt", url)
            return FetchResult(
                url=url,
                final_url=url,
                status_code=None,
                html=None,
                fetched_at=utcnow(),
                success=False,
                error="blocked_by_robots_txt",
            )

        self._wait_for_domain(url)

        owns_client = self._injected_client is None
        client = self._injected_client or httpx.Client(
            timeout=self._timeout_seconds,
            follow_redirects=True,
        )
        try:
            # Set header tường minh trên từng request (không chỉ dựa vào default
            # header của client) để user-agent luôn đúng kể cả khi client được
            # inject từ ngoài (test double).
            response = client.get(url, headers={"User-Agent": self._user_agent})
            return FetchResult(
                url=url,
                final_url=str(response.url),
                status_code=response.status_code,
                html=response.text,
                fetched_at=utcnow(),
                success=response.is_success,
                error=None if response.is_success else f"http_{response.status_code}",
            )
        except httpx.HTTPError as exc:
            logger.warning("Fetch lỗi cho %s: %s", url, exc)
            return FetchResult(
                url=url,
                final_url=url,
                status_code=None,
                html=None,
                fetched_at=utcnow(),
                success=False,
                error=str(exc),
            )
        finally:
            if owns_client:
                client.close()
