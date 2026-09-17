"""Fetch engine dùng Playwright (Chromium headless) — cho site JS-heavy cần
chạy JS mới render được nội dung (site tĩnh dùng `HttpxFetcher`, xem CLAUDE.md
mục "Tech stack": "httpx (site tĩnh) + Playwright (site JS-heavy), có adapter
tách biệt").

`playwright` đã có trong requirements.txt nhưng cần chạy `playwright install
chromium` 1 lần trước khi dùng (xem README) — KHÔNG tự cài driver lúc runtime
(side-effect nặng, không phù hợp chạy trong lúc xử lý 1 request web).

Cùng tuân thủ robots.txt + rate-limit theo domain như `HttpxFetcher` (CLAUDE.md
mục 3) — dùng chung `HttpRobotsChecker`/`DomainRateLimiter`.
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Protocol

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from .base import FetchEngine, FetchResult, RobotsChecker, domain_of, utcnow
from .rate_limiter import DomainRateLimiter
from .robots import HttpRobotsChecker

logger = logging.getLogger(__name__)

_DEFAULT_WAIT_UNTIL = "networkidle"


class _Page(Protocol):
    url: str

    def goto(self, url: str, timeout: float, wait_until: str) -> Any: ...
    def content(self) -> str: ...
    def close(self) -> None: ...


class _Browser(Protocol):
    """Chỉ cần đúng 2 method này — cho phép inject browser giả (test double)
    thay vì luôn khởi động Chromium thật, theo adapter/test-double pattern
    CLAUDE.md mục 6. Không ràng buộc kiểu `playwright.sync_api.Browser` cụ thể
    để test không cần cài Playwright/Chromium thật vẫn chạy được."""

    def new_page(self, user_agent: str) -> _Page: ...
    def close(self) -> None: ...


class PlaywrightFetcher(FetchEngine):
    """`browser` cho phép inject 1 browser đã khởi tạo sẵn (thật hoặc test
    double) — khi không inject, tự khởi động + đóng Chromium headless cho MỖI
    lần fetch (đơn giản, đúng hướng "ưu tiên chạy được bản MVP tối giản trước"
    — tái sử dụng 1 browser instance dùng chung nhiều lần là tối ưu để sau,
    chỉ làm khi có bằng chứng đây là bottleneck thật)."""

    def __init__(
        self,
        user_agent: str,
        timeout_seconds: float = 30.0,
        wait_until: str = _DEFAULT_WAIT_UNTIL,
        robots_checker: Optional[RobotsChecker] = None,
        delay_seconds: float = 0.0,
        browser: Optional[_Browser] = None,
    ) -> None:
        self._user_agent = user_agent
        self._timeout_seconds = timeout_seconds
        self._wait_until = wait_until
        self._robots_checker = robots_checker or HttpRobotsChecker()
        self._rate_limiter = DomainRateLimiter(delay_seconds)
        self._injected_browser = browser

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

        self._rate_limiter.wait(domain_of(url))

        if self._injected_browser is not None:
            return self._fetch_with_browser(self._injected_browser, url)

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                try:
                    return self._fetch_with_browser(browser, url)
                finally:
                    browser.close()
        except PlaywrightError as exc:
            logger.warning("Playwright lỗi khi khởi động Chromium cho %s: %s", url, exc)
            return FetchResult(
                url=url, final_url=url, status_code=None, html=None,
                fetched_at=utcnow(), success=False, error=str(exc),
            )

    def _fetch_with_browser(self, browser: _Browser, url: str) -> FetchResult:
        page = browser.new_page(user_agent=self._user_agent)
        try:
            response = page.goto(
                url, timeout=self._timeout_seconds * 1000, wait_until=self._wait_until
            )
            html = page.content()
            status_code = response.status if response is not None else None
            success = response is not None and response.ok
            error = None
            if not success:
                error = f"http_{status_code}" if status_code else "no_response"
            return FetchResult(
                url=url,
                final_url=page.url,
                status_code=status_code,
                html=html,
                fetched_at=utcnow(),
                success=success,
                error=error,
            )
        except PlaywrightError as exc:
            logger.warning("Playwright lỗi khi load %s: %s", url, exc)
            return FetchResult(
                url=url, final_url=url, status_code=None, html=None,
                fetched_at=utcnow(), success=False, error=str(exc),
            )
        finally:
            page.close()
