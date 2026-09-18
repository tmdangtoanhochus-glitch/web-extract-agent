"""Test HttpxFetcher bằng httpx.MockTransport — không gọi mạng thật."""
import httpx
import pytest

from src.fetch.base import AllowAllRobotsChecker, FetchResult, RobotsChecker
from src.fetch.httpx_fetcher import HttpxFetcher, domain_of


def _make_fetcher(handler, **kwargs) -> HttpxFetcher:
    """Mặc định inject `AllowAllRobotsChecker` — các test ở đây kiểm tra cơ chế
    fetch/parse HTML, không phải hành vi robots.txt (đã có test riêng ở
    `test_http_robots_checker.py`), và default thật (`HttpRobotsChecker`) sẽ
    gọi mạng thật để tải robots.txt nếu không override."""
    kwargs.setdefault("robots_checker", AllowAllRobotsChecker())
    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    return HttpxFetcher(user_agent="test-agent/0.1", client=mock_client, **kwargs)


def test_fetch_success_returns_html_and_status():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html><body>OK</body></html>")

    fetcher = _make_fetcher(handler)
    result = fetcher.fetch("https://example.com/page")

    assert isinstance(result, FetchResult)
    assert result.success is True
    assert result.status_code == 200
    assert "OK" in result.html
    assert result.error is None


def test_fetch_http_error_status_marks_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    fetcher = _make_fetcher(handler)
    result = fetcher.fetch("https://example.com/missing")

    assert result.success is False
    assert result.status_code == 404
    assert result.error == "http_404"


def test_fetch_network_error_is_caught_not_raised():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    fetcher = _make_fetcher(handler)
    result = fetcher.fetch("https://example.com/")

    assert result.success is False
    assert result.status_code is None
    assert result.html is None
    assert "boom" in result.error


def test_fetch_uses_configured_user_agent():
    seen_headers = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers["user-agent"] = request.headers.get("user-agent")
        return httpx.Response(200, text="ok")

    fetcher = _make_fetcher(handler)
    fetcher.fetch("https://example.com/")

    assert seen_headers["user-agent"] == "test-agent/0.1"


def test_fetch_attaches_cookie_header_from_credential_provider_for_matching_domain():
    seen_headers = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers["cookie"] = request.headers.get("cookie")
        return httpx.Response(200, text="ok")

    fetcher = _make_fetcher(
        handler, credential_provider=lambda domain: "session=abc123" if domain == "example.com" else None
    )
    fetcher.fetch("https://example.com/")

    assert seen_headers["cookie"] == "session=abc123"


def test_fetch_no_cookie_header_when_credential_provider_returns_none():
    seen_headers = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers["cookie"] = request.headers.get("cookie")
        return httpx.Response(200, text="ok")

    fetcher = _make_fetcher(handler, credential_provider=lambda domain: None)
    fetcher.fetch("https://example.com/")

    assert seen_headers["cookie"] is None


def test_fetch_no_cookie_header_when_no_credential_provider_configured():
    seen_headers = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers["cookie"] = request.headers.get("cookie")
        return httpx.Response(200, text="ok")

    fetcher = _make_fetcher(handler)
    fetcher.fetch("https://example.com/")

    assert seen_headers["cookie"] is None


class _BlockingRobotsChecker(RobotsChecker):
    def can_fetch(self, url: str, user_agent: str) -> bool:
        return False


def test_fetch_respects_robots_checker_test_double():
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, text="should not be reached")

    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    fetcher = HttpxFetcher(
        user_agent="test-agent/0.1",
        client=mock_client,
        robots_checker=_BlockingRobotsChecker(),
    )

    result = fetcher.fetch("https://blocked.example.com/")

    assert called is False
    assert result.success is False
    assert result.error == "blocked_by_robots_txt"


@pytest.mark.parametrize(
    "url,expected_domain",
    [
        ("https://example.com/a/b", "example.com"),
        ("http://sub.example.org:8080/x", "sub.example.org:8080"),
    ],
)
def test_domain_of(url, expected_domain):
    assert domain_of(url) == expected_domain
