"""Test HttpRobotsChecker bằng httpx.MockTransport — không gọi mạng thật
(CLAUDE.md mục 3 + 6)."""
import httpx

from src.fetch.robots import HttpRobotsChecker

_ROBOTS_TXT = """
User-agent: *
Disallow: /private
Allow: /
"""


def _make_checker(handler, **kwargs) -> HttpRobotsChecker:
    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    return HttpRobotsChecker(client=mock_client, **kwargs)


def test_allows_path_not_disallowed_by_robots_txt():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_ROBOTS_TXT)

    checker = _make_checker(handler)

    assert checker.can_fetch("https://example.com/public", "any-agent") is True


def test_blocks_path_disallowed_by_robots_txt():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_ROBOTS_TXT)

    checker = _make_checker(handler)

    assert checker.can_fetch("https://example.com/private/data", "any-agent") is False


def test_missing_robots_txt_404_allows_crawl():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    checker = _make_checker(handler)

    assert checker.can_fetch("https://example.com/anything", "any-agent") is True


def test_server_error_fails_closed_and_denies_crawl(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal error")

    checker = _make_checker(handler)

    with caplog.at_level("WARNING"):
        result = checker.can_fetch("https://example.com/anything", "any-agent")

    assert result is False
    assert any("fail-closed" in record.message for record in caplog.records)


def test_network_error_fails_closed_and_denies_crawl():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    checker = _make_checker(handler)

    assert checker.can_fetch("https://example.com/anything", "any-agent") is False


def test_caches_result_per_domain_within_ttl():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, text=_ROBOTS_TXT)

    checker = _make_checker(handler, cache_ttl_seconds=3600.0)

    checker.can_fetch("https://example.com/a", "agent")
    checker.can_fetch("https://example.com/b", "agent")

    assert len(calls) == 1  # 2 request cùng domain, chỉ tải robots.txt 1 lần


def test_different_domains_are_cached_independently():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, text=_ROBOTS_TXT)

    checker = _make_checker(handler, cache_ttl_seconds=3600.0)

    checker.can_fetch("https://a.example.com/x", "agent")
    checker.can_fetch("https://b.example.com/x", "agent")

    assert len(calls) == 2


def test_refetches_after_cache_ttl_expires():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, text=_ROBOTS_TXT)

    checker = _make_checker(handler, cache_ttl_seconds=0.0)

    checker.can_fetch("https://example.com/a", "agent")
    checker.can_fetch("https://example.com/a", "agent")

    assert len(calls) == 2


def test_override_domain_bypasses_check_and_logs_warning_on_use(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="User-agent: *\nDisallow: /")

    with caplog.at_level("WARNING"):
        checker = _make_checker(
            handler, override_domains={"example.com": "chủ sở hữu xác nhận qua email 2026-09-12"}
        )
        caplog.clear()
        result = checker.can_fetch("https://example.com/anything", "agent")

    assert result is True
    assert any("Bỏ qua kiểm tra robots.txt" in record.message for record in caplog.records)


def test_override_domain_logs_warning_at_construction_time(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    with caplog.at_level("WARNING"):
        _make_checker(handler, override_domains={"example.com": "lý do test"})

    assert any("BỎ QUA tường minh" in record.message for record in caplog.records)


def test_domain_not_in_override_is_still_checked_normally():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="User-agent: *\nDisallow: /")

    checker = _make_checker(handler, override_domains={"other.example.com": "lý do test"})

    assert checker.can_fetch("https://example.com/anything", "agent") is False
