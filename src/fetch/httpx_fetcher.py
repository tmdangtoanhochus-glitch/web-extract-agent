"""Fetch engine dùng httpx — cho site tĩnh (không cần chạy JS).

Site JS-heavy sẽ dùng 1 implementation `FetchEngine` khác dựa trên Playwright,
thêm sau (xem CLAUDE.md — chưa làm trong bước này).
"""
from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urlparse

import httpx

from .base import AllowAllRobotsChecker, FetchEngine, FetchResult, RobotsChecker, utcnow

logger = logging.getLogger(__name__)


class HttpxFetcher(FetchEngine):
    """Fetch site tĩnh bằng httpx.

    `client` cho phép inject 1 `httpx.Client` có sẵn (vd. dùng `httpx.MockTransport`
    khi test) thay vì luôn tạo client thật — theo adapter/test-double pattern ở
    CLAUDE.md mục 6.

    `robots_checker` mặc định là `AllowAllRobotsChecker` (stub, luôn cho phép) —
    chưa implement kiểm tra robots.txt thật trong bước này, chỉ có chỗ cắm sẵn.

    `delay_seconds` giữ chỗ cho rate-limit theo domain (CLAUDE.md mục 3) —
    hiện tại CHƯA implement (stub, không sleep thật), sẽ làm cùng lúc với
    robots_checker thật ở bước sau.
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
        self._robots_checker = robots_checker or AllowAllRobotsChecker()
        self._injected_client = client
        self._delay_seconds = delay_seconds

    def _wait_for_domain(self, url: str) -> None:
        """STUB — giữ chỗ cho rate-limit/delay giữa các request cùng domain.
        TODO: track lần fetch gần nhất theo domain (netloc) và sleep đủ
        `delay_seconds` nếu cần, khi implement robots.txt thật."""
        return None

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


def domain_of(url: str) -> str:
    return urlparse(url).netloc
