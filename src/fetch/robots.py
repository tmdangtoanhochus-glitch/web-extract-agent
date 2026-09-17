"""Kiểm tra robots.txt THẬT trước khi fetch (CLAUDE.md mục 3) — mặc định LUÔN
bật (xem `HttpxFetcher` dùng class này làm default `robots_checker`), không
phải checkbox tắt/bật dễ dàng.

Dùng `urllib.robotparser.RobotFileParser` (thư viện chuẩn Python, không thêm
dependency ngoài tech stack đã chốt) để parse đúng chuẩn robots.txt.

Cache theo domain (TTL mặc định 1 giờ) để không tải lại robots.txt cho mỗi
request — chỉ tải lại khi cache hết hạn.

Quy ước khi không tải được robots.txt (theo thực hành phổ biến, vd. Google):
- 404 (không có robots.txt) → cho phép crawl (mặc định của chuẩn robots.txt).
- 4xx khác → cũng cho phép (trang không chặn được coi là không có rule).
- 5xx hoặc lỗi mạng → CHẶN tạm thời (fail-closed) tới lần refresh cache sau —
  an toàn hơn là crawl bừa khi không rõ site có muốn chặn hay không.

Muốn bỏ qua robots.txt cho 1 domain cụ thể PHẢI truyền tường minh qua
`override_domains={domain: lý_do}` khi khởi tạo — không có cờ bật/tắt chung.
Mỗi lần dùng đều log WARNING rõ ràng (cả lúc khởi tạo và mỗi lần áp dụng),
đúng yêu cầu "không phải toggle im lặng".
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from .base import RobotsChecker

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 10.0
_DEFAULT_CACHE_TTL_SECONDS = 3600.0


@dataclass(frozen=True)
class _CacheEntry:
    parser: Optional[RobotFileParser]
    allow_all: bool
    deny_all: bool
    fetched_at: float


class HttpRobotsChecker(RobotsChecker):
    def __init__(
        self,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        cache_ttl_seconds: float = _DEFAULT_CACHE_TTL_SECONDS,
        client: Optional[httpx.Client] = None,
        override_domains: Optional[dict[str, str]] = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._cache_ttl_seconds = cache_ttl_seconds
        self._injected_client = client
        self._override_domains = dict(override_domains or {})
        self._cache: dict[str, _CacheEntry] = {}

        for domain, reason in self._override_domains.items():
            logger.warning(
                "robots.txt sẽ bị BỎ QUA tường minh cho domain '%s' — lý do khai báo: %s. "
                "Đây là override có chủ đích lúc khởi tạo checker, không phải mặc định.",
                domain,
                reason,
            )

    def can_fetch(self, url: str, user_agent: str) -> bool:
        domain = urlparse(url).netloc

        if domain in self._override_domains:
            logger.warning(
                "Bỏ qua kiểm tra robots.txt cho %s (domain '%s' nằm trong override, lý do: %s).",
                url,
                domain,
                self._override_domains[domain],
            )
            return True

        entry = self._get_cached_or_fetch(domain, url, user_agent)
        if entry.allow_all:
            return True
        if entry.deny_all:
            return False
        assert entry.parser is not None
        return entry.parser.can_fetch(user_agent, url)

    def _get_cached_or_fetch(self, domain: str, url: str, user_agent: str) -> _CacheEntry:
        cached = self._cache.get(domain)
        now = time.monotonic()
        if cached is not None and (now - cached.fetched_at) < self._cache_ttl_seconds:
            return cached

        entry = self._fetch_robots_txt(domain, url, user_agent)
        self._cache[domain] = entry
        return entry

    def _fetch_robots_txt(self, domain: str, url: str, user_agent: str) -> _CacheEntry:
        scheme = urlparse(url).scheme or "https"
        robots_url = f"{scheme}://{domain}/robots.txt"
        fetched_at = time.monotonic()

        owns_client = self._injected_client is None
        client = self._injected_client or httpx.Client(
            timeout=self._timeout_seconds, follow_redirects=True
        )
        try:
            response = client.get(robots_url, headers={"User-Agent": user_agent})
        except httpx.HTTPError as exc:
            logger.warning(
                "Không tải được robots.txt của %s (%s) — coi như CHẶN tạm thời (fail-closed) "
                "tới lần refresh cache sau.",
                domain,
                exc,
            )
            return _CacheEntry(parser=None, allow_all=False, deny_all=True, fetched_at=fetched_at)
        finally:
            if owns_client:
                client.close()

        if response.status_code == 404:
            logger.info("Domain %s không có robots.txt (404) — mặc định cho phép crawl.", domain)
            return _CacheEntry(parser=None, allow_all=True, deny_all=False, fetched_at=fetched_at)

        if response.status_code >= 500:
            logger.warning(
                "robots.txt của %s trả lỗi %s — coi như CHẶN tạm thời (fail-closed) tới lần "
                "refresh cache sau.",
                domain,
                response.status_code,
            )
            return _CacheEntry(parser=None, allow_all=False, deny_all=True, fetched_at=fetched_at)

        if not response.is_success:
            logger.info(
                "robots.txt của %s trả %s — coi như cho phép crawl (theo quy ước robots.txt).",
                domain,
                response.status_code,
            )
            return _CacheEntry(parser=None, allow_all=True, deny_all=False, fetched_at=fetched_at)

        parser = RobotFileParser()
        parser.parse(response.text.splitlines())
        return _CacheEntry(parser=parser, allow_all=False, deny_all=False, fetched_at=fetched_at)
