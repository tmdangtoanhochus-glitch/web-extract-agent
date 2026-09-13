"""Test PlaywrightFetcher bằng browser/page giả (test double) — không khởi
động Chromium thật, theo adapter/test-double pattern CLAUDE.md mục 6."""
from playwright.sync_api import Error as PlaywrightError

from src.fetch.base import AllowAllRobotsChecker
from src.fetch.playwright_fetcher import PlaywrightFetcher


class _FakeResponse:
    def __init__(self, status: int, ok: bool) -> None:
        self.status = status
        self.ok = ok


class _FakePage:
    def __init__(self, response=None, html: str = "", url: str = "", raise_on_goto=None) -> None:
        self._response = response
        self._html = html
        self.url = url
        self._raise_on_goto = raise_on_goto
        self.closed = False
        self.goto_calls: list[dict] = []

    def goto(self, url: str, timeout: float, wait_until: str):
        self.goto_calls.append({"url": url, "timeout": timeout, "wait_until": wait_until})
        if self._raise_on_goto is not None:
            raise self._raise_on_goto
        return self._response

    def content(self) -> str:
        return self._html

    def close(self) -> None:
        self.closed = True


class _FakeBrowser:
    def __init__(self, page_factory) -> None:
        self._page_factory = page_factory
        self.new_page_calls: list[str] = []
        self.pages: list[_FakePage] = []

    def new_page(self, user_agent: str) -> _FakePage:
        self.new_page_calls.append(user_agent)
        page = self._page_factory()
        self.pages.append(page)
        return page

    def close(self) -> None:
        pass


def _make_fetcher(browser: _FakeBrowser, **kwargs) -> PlaywrightFetcher:
    kwargs.setdefault("robots_checker", AllowAllRobotsChecker())
    return PlaywrightFetcher(user_agent="test-agent/0.1", browser=browser, **kwargs)


def test_fetch_success_returns_html_and_status():
    browser = _FakeBrowser(
        lambda: _FakePage(response=_FakeResponse(200, True), html="<html>OK</html>", url="https://example.com/page")
    )
    fetcher = _make_fetcher(browser)

    result = fetcher.fetch("https://example.com/page")

    assert result.success is True
    assert result.status_code == 200
    assert result.html == "<html>OK</html>"
    assert result.final_url == "https://example.com/page"
    assert result.error is None


def test_fetch_http_error_status_marks_failure():
    browser = _FakeBrowser(lambda: _FakePage(response=_FakeResponse(404, False), html="not found", url="https://example.com/missing"))
    fetcher = _make_fetcher(browser)

    result = fetcher.fetch("https://example.com/missing")

    assert result.success is False
    assert result.status_code == 404
    assert result.error == "http_404"


def test_fetch_no_response_from_goto_marks_failure_without_raising():
    browser = _FakeBrowser(lambda: _FakePage(response=None, html="", url="https://example.com/x"))
    fetcher = _make_fetcher(browser)

    result = fetcher.fetch("https://example.com/x")

    assert result.success is False
    assert result.status_code is None
    assert result.error == "no_response"


def test_fetch_sets_user_agent_on_new_page():
    browser = _FakeBrowser(lambda: _FakePage(response=_FakeResponse(200, True), html="ok", url="https://example.com/"))
    fetcher = PlaywrightFetcher(
        user_agent="custom-agent/1.0", browser=browser, robots_checker=AllowAllRobotsChecker()
    )

    fetcher.fetch("https://example.com/")

    assert browser.new_page_calls == ["custom-agent/1.0"]


def test_fetch_passes_timeout_seconds_in_milliseconds_and_wait_until():
    browser = _FakeBrowser(lambda: _FakePage(response=_FakeResponse(200, True), html="ok", url="https://example.com/"))
    fetcher = PlaywrightFetcher(
        user_agent="test-agent/0.1",
        browser=browser,
        robots_checker=AllowAllRobotsChecker(),
        timeout_seconds=15.0,
        wait_until="load",
    )

    fetcher.fetch("https://example.com/")

    assert browser.pages[0].goto_calls == [
        {"url": "https://example.com/", "timeout": 15000.0, "wait_until": "load"}
    ]


def test_fetch_playwright_error_on_goto_returns_failure_not_raise():
    browser = _FakeBrowser(lambda: _FakePage(raise_on_goto=PlaywrightError("navigation timeout")))
    fetcher = _make_fetcher(browser)

    result = fetcher.fetch("https://example.com/slow")

    assert result.success is False
    assert "navigation timeout" in result.error


def test_page_is_closed_after_successful_fetch():
    browser = _FakeBrowser(lambda: _FakePage(response=_FakeResponse(200, True), html="ok", url="https://example.com/"))
    fetcher = _make_fetcher(browser)

    fetcher.fetch("https://example.com/")

    assert browser.pages[0].closed is True


def test_page_is_closed_even_when_goto_raises():
    browser = _FakeBrowser(lambda: _FakePage(raise_on_goto=PlaywrightError("boom")))
    fetcher = _make_fetcher(browser)

    fetcher.fetch("https://example.com/")

    assert browser.pages[0].closed is True


def test_fetch_respects_robots_checker_and_never_opens_page():
    class _BlockAllRobotsChecker:
        def can_fetch(self, url: str, user_agent: str) -> bool:
            return False

    browser = _FakeBrowser(lambda: _FakePage())
    fetcher = PlaywrightFetcher(
        user_agent="test-agent/0.1", browser=browser, robots_checker=_BlockAllRobotsChecker()
    )

    result = fetcher.fetch("https://blocked.example.com/")

    assert result.success is False
    assert result.error == "blocked_by_robots_txt"
    assert browser.new_page_calls == []


def test_fetch_applies_domain_rate_limit(monkeypatch):
    calls = {"now": 0.0, "sleeps": []}

    def fake_monotonic():
        return calls["now"]

    def fake_sleep(seconds):
        calls["sleeps"].append(seconds)
        calls["now"] += seconds

    monkeypatch.setattr("src.fetch.rate_limiter.time.monotonic", fake_monotonic)
    monkeypatch.setattr("src.fetch.rate_limiter.time.sleep", fake_sleep)

    browser = _FakeBrowser(lambda: _FakePage(response=_FakeResponse(200, True), html="ok", url="https://example.com/"))
    fetcher = _make_fetcher(browser, delay_seconds=2.0)

    fetcher.fetch("https://example.com/a")
    fetcher.fetch("https://example.com/b")

    assert calls["sleeps"] == [2.0]
