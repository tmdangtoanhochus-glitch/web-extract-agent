"""Test rate-limit theo domain của HttpxFetcher (CLAUDE.md mục 3) — dùng đồng
hồ giả (`_FakeClock`) để test xác định, không sleep thật (test nhanh, không
phụ thuộc thời gian máy chạy test)."""
import httpx
import pytest

from src.fetch.base import AllowAllRobotsChecker
from src.fetch.httpx_fetcher import HttpxFetcher


class _FakeClock:
    """Thay `time.monotonic`/`time.sleep` — `sleep()` cộng dồn luôn vào đồng hồ
    giả để mô phỏng thời gian trôi qua, khỏi phải chờ thật trong test."""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start
        self.sleep_calls: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleep_calls.append(seconds)
        self.now += seconds

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _make_fetcher(monkeypatch, handler, delay_seconds: float, clock: _FakeClock) -> HttpxFetcher:
    monkeypatch.setattr("src.fetch.rate_limiter.time.monotonic", clock.monotonic)
    monkeypatch.setattr("src.fetch.rate_limiter.time.sleep", clock.sleep)
    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    return HttpxFetcher(
        user_agent="test-agent/0.1",
        client=mock_client,
        robots_checker=AllowAllRobotsChecker(),
        delay_seconds=delay_seconds,
    )


def _ok_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, text="ok")


def test_no_delay_by_default_when_delay_seconds_is_zero(monkeypatch):
    clock = _FakeClock()
    fetcher = _make_fetcher(monkeypatch, _ok_handler, delay_seconds=0.0, clock=clock)

    fetcher.fetch("https://example.com/a")
    fetcher.fetch("https://example.com/b")

    assert clock.sleep_calls == []


def test_first_fetch_to_a_domain_does_not_wait(monkeypatch):
    clock = _FakeClock()
    fetcher = _make_fetcher(monkeypatch, _ok_handler, delay_seconds=2.0, clock=clock)

    fetcher.fetch("https://example.com/a")

    assert clock.sleep_calls == []


def test_second_immediate_fetch_to_same_domain_waits_full_delay(monkeypatch):
    clock = _FakeClock()
    fetcher = _make_fetcher(monkeypatch, _ok_handler, delay_seconds=2.0, clock=clock)

    fetcher.fetch("https://example.com/a")
    fetcher.fetch("https://example.com/b")  # cùng domain, gọi ngay lập tức

    assert clock.sleep_calls == [2.0]


def test_reservation_keeps_consecutive_requests_spaced_by_delay(monkeypatch):
    clock = _FakeClock()
    fetcher = _make_fetcher(monkeypatch, _ok_handler, delay_seconds=2.0, clock=clock)

    fetcher.fetch("https://example.com/a")
    fetcher.fetch("https://example.com/b")
    fetcher.fetch("https://example.com/c")

    # request 1: t=0, không chờ. request 2: chờ tới t=2. request 3: chờ tới t=4
    # (cách request 2 đúng 2s), dù request 3 được gọi ngay sau request 2.
    assert clock.sleep_calls == [2.0, 2.0]
    assert clock.now == pytest.approx(4.0)


def test_no_wait_when_enough_time_already_passed(monkeypatch):
    clock = _FakeClock()
    fetcher = _make_fetcher(monkeypatch, _ok_handler, delay_seconds=2.0, clock=clock)

    fetcher.fetch("https://example.com/a")
    clock.advance(10.0)  # đã qua lâu hơn delay_seconds
    fetcher.fetch("https://example.com/b")

    assert clock.sleep_calls == []


def test_different_domains_are_rate_limited_independently(monkeypatch):
    clock = _FakeClock()
    fetcher = _make_fetcher(monkeypatch, _ok_handler, delay_seconds=2.0, clock=clock)

    fetcher.fetch("https://a.example.com/x")
    fetcher.fetch("https://b.example.com/x")  # domain khác, không phải chờ

    assert clock.sleep_calls == []


def test_rate_limit_does_not_apply_when_blocked_by_robots(monkeypatch):
    """Request bị robots.txt chặn không nên tốn slot rate-limit của domain đó."""
    clock = _FakeClock()
    monkeypatch.setattr("src.fetch.rate_limiter.time.monotonic", clock.monotonic)
    monkeypatch.setattr("src.fetch.rate_limiter.time.sleep", clock.sleep)

    class _BlockAllRobotsChecker:
        def can_fetch(self, url: str, user_agent: str) -> bool:
            return False

    mock_client = httpx.Client(transport=httpx.MockTransport(_ok_handler))
    fetcher = HttpxFetcher(
        user_agent="test-agent/0.1",
        client=mock_client,
        robots_checker=_BlockAllRobotsChecker(),
        delay_seconds=2.0,
    )

    result = fetcher.fetch("https://example.com/a")

    assert result.success is False
    assert clock.sleep_calls == []
