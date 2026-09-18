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

from .base import FetchEngine, OverrideRobotsChecker, FetchResult, RobotsChecker, domain_of, utcnow
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
        wait_until: str = "domcontentloaded",
        robots_checker: Optional[RobotsChecker] = None,
        delay_seconds: float = 0.0,
        browser: Optional[_Browser] = None,
        chrome_executable_path: Optional[str] = None,
    ) -> None:
        self._user_agent = user_agent
        self._timeout_seconds = timeout_seconds
        self._wait_until = wait_until
        self._robots_checker = robots_checker or HttpRobotsChecker()
        self._rate_limiter = DomainRateLimiter(delay_seconds)
        self._injected_browser = browser
        self._chrome_executable_path = chrome_executable_path
        self._cookie_header: Optional[str] = None
        self._cookie_origin: Optional[str] = None

    def with_request_cookie(self, url: str, cookie: str) -> "PlaywrightFetcher":
        clone = PlaywrightFetcher(
            user_agent=self._user_agent,
            timeout_seconds=self._timeout_seconds,
            wait_until=self._wait_until,
            robots_checker=self._robots_checker,
            chrome_executable_path=self._chrome_executable_path,
        )
        clone._rate_limiter = self._rate_limiter
        clone._cookie_header = cookie
        clone._cookie_origin = url
        return clone

    def with_robots_ignored(self, domain: str, reason: str) -> "PlaywrightFetcher":
        """Bản sao dùng riêng cho 1 request: bỏ qua robots.txt của đúng `domain`."""
        import copy
        clone = copy.copy(self)
        clone._robots_checker = OverrideRobotsChecker(self._robots_checker, domain, reason)
        return clone

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
                launch_kwargs = {"headless": True}
                if self._chrome_executable_path:
                    launch_kwargs["executable_path"] = self._chrome_executable_path
                browser = playwright.chromium.launch(**launch_kwargs)
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
        if self._cookie_header:
            try:
                from urllib.parse import urlsplit
                parts = urlsplit(self._cookie_origin or url)
                cookies = []
                for pair in self._cookie_header.split(";"):
                    pair = pair.strip()
                    if "=" in pair:
                        name, value = pair.split("=", 1)
                        cookies.append({"name": name.strip(), "value": value.strip(),
                                       "domain": parts.hostname, "path": "/"})
                if cookies:
                    context = page.context
                    context.add_cookies(cookies)
            except Exception:
                pass
        api_json_data = []
        try:
            def _capture_api(response):
                try:
                    if response.request.resource_type in ("xhr", "fetch"):
                        body = response.text()
                        if body and body.strip().startswith("["):
                            import json
                            parsed = json.loads(body)
                            if isinstance(parsed, list) and len(parsed) > 2:
                                api_json_data.append(parsed)
                                logger.info("API interception captured %d records from %s", len(parsed), response.url[:80])
                except Exception as exc:
                    logger.debug("API interception bỏ qua %s: %s", response.url[:80], exc)  # thường là request quảng cáo/đã điều hướng
            page.on("response", _capture_api)
            response = page.goto(
                url, timeout=self._timeout_seconds * 1000, wait_until=self._wait_until
            )
            # Chờ AJAX xong theo trạng thái mạng thay vì sleep cố định 8 giây/trang;
            # quá hạn thì dùng luôn DOM hiện có.
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except PlaywrightError:
                pass
            html = page.content()
            if api_json_data:
                largest = max(api_json_data, key=len)
                html = _inject_api_data_as_table(html, largest)
                logger.info("Injected %d records from API interception into HTML.", len(largest))
            else:
                # Fallback: read rendered DOM tables directly (AJAX already loaded data)
                if not api_json_data:
                    try:
                        table_html = page.evaluate(
                            """() => {
                                const tables = document.querySelectorAll('table');
                                let result = '';
                                for (const t of tables) {
                                    const rows = t.querySelectorAll('tr');
                                    if (rows.length > 3) {
                                        result += t.outerHTML;
                                    }
                                }
                                return result;
                            }"""
                        )
                        if table_html and len(table_html) > 200:
                            html = html + table_html
                            logger.info("Injected rendered DOM tables: %d chars", len(table_html))
                    except Exception:
                        pass
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


def _inject_api_data_as_table(html: str, records: list) -> str:
    """Convert API JSON array records into HTML table and inject before </body>."""
    if not records or not isinstance(records[0], dict):
        return html
    from html import escape
    keys = list(records[0].keys())
    rows_html = []
    rows_html.append("<tr>" + "".join(f"<th>{escape(str(k))}</th>" for k in keys) + "</tr>")
    for r in records:
        cells = "".join(f"<td>{escape(str(r.get(k, '')))}</td>" for k in keys)
        rows_html.append(f"<tr>{cells}</tr>")
    table_html = f'<table id="api-data"><tbody>{"".join(rows_html)}</tbody></table>'
    if "</body>" in html:
        return html.replace("</body>", f"{table_html}</body>")
    return html + table_html
