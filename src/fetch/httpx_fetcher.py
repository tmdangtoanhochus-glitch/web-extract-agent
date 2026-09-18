"""Fetch engine dùng httpx — cho site tĩnh (không cần chạy JS).

Site JS-heavy dùng `PlaywrightFetcher` (xem `src/fetch/playwright_fetcher.py`)
thay vì engine này.
"""
from __future__ import annotations

import logging
from urllib.parse import urlsplit
from typing import Callable, Optional

import httpx

from .base import FetchEngine, FetchResult, OverrideRobotsChecker, RobotsChecker, domain_of, utcnow
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

    `credential_provider`: hàm `domain -> cookie_header hoặc None`, tra cứu
    cookie đăng nhập THỦ CÔNG người dùng đã lưu cho domain đó (xem
    `StorageEngine.get_site_credential`, `src/api/admin.py`) — KHÔNG tự động
    đăng nhập/điền form, chỉ gắn thẳng header `Cookie` nếu có cấu hình sẵn cho
    domain của URL đang fetch. `None` (mặc định) = không gắn cookie nào.
    """

    def __init__(
        self,
        user_agent: str,
        timeout_seconds: float = 30.0,
        robots_checker: Optional[RobotsChecker] = None,
        client: Optional[httpx.Client] = None,
        delay_seconds: float = 0.0,
        credential_provider: Optional[Callable[[str], Optional[str]]] = None,
    ) -> None:
        self._user_agent = user_agent
        self._timeout_seconds = timeout_seconds
        self._robots_checker = robots_checker or HttpRobotsChecker()
        self._injected_client = client
        self._rate_limiter = DomainRateLimiter(delay_seconds)
        self._credential_provider = credential_provider
        self._request_cookie = None
        self._cookie_origin = None

    def with_request_cookie(self, url: str, cookie: str):
        """New fetcher per request; no shared credential persistence or redirects across origins."""
        clone = HttpxFetcher(self._user_agent, self._timeout_seconds, self._robots_checker,
                             self._injected_client)
        clone._rate_limiter = self._rate_limiter
        clone._request_cookie = cookie
        clone._cookie_origin = urlsplit(url)[:2]
        return clone

    def with_robots_ignored(self, domain: str, reason: str):
        """Bản sao dùng riêng cho 1 request: bỏ qua robots.txt của đúng `domain`."""
        import copy
        clone = copy.copy(self)
        clone._robots_checker = OverrideRobotsChecker(self._robots_checker, domain, reason)
        return clone

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
            if self._request_cookie is not None:
                current = url
                for _ in range(11):
                    if urlsplit(current)[:2] != self._cookie_origin:
                        return FetchResult(url=url, final_url=url, status_code=None, html=None,
                                           fetched_at=utcnow(), success=False, error="cookie_cross_origin_redirect_blocked")
                    if current != url:
                        if not self._robots_checker.can_fetch(current, self._user_agent):
                            return FetchResult(url=url, final_url=url, status_code=None, html=None,
                                fetched_at=utcnow(), success=False, error="blocked_by_robots_txt")
                        self._wait_for_domain(current)
                    response = client.get(current, headers={"User-Agent": self._user_agent,
                        "Cookie": self._request_cookie}, follow_redirects=False)
                    if response.has_redirect_location:
                        current = str(response.url.join(response.headers["location"]))
                        continue
                    html = response.text
                    for part in self._request_cookie.split(";"):
                        value = part.partition("=")[2].strip()
                        if value:
                            html = html.replace(value, "[REDACTED]")
                    return FetchResult(url=url, final_url=str(response.url), status_code=response.status_code,
                        html=html, fetched_at=utcnow(), success=response.is_success,
                        error=None if response.is_success else f"http_{response.status_code}")
                return FetchResult(url=url, final_url=url, status_code=None, html=None,
                                   fetched_at=utcnow(), success=False, error="redirect_limit")
            # Set header tường minh trên từng request (không chỉ dựa vào default
            # header của client) để user-agent luôn đúng kể cả khi client được
            # inject từ ngoài (test double).
            headers = {"User-Agent": self._user_agent}
            cookie_header = self._credential_provider(domain_of(url)) if self._credential_provider else None
            if cookie_header:
                headers["Cookie"] = cookie_header
                logger.info("Dùng cookie đăng nhập đã lưu cho domain %s khi fetch %s", domain_of(url), url)
            response = client.get(url, headers=headers)
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
            if self._request_cookie is not None:
                return FetchResult(url=url, final_url=url, status_code=None, html=None,
                                   fetched_at=utcnow(), success=False, error="request_cookie_fetch_failed")
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
