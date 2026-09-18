"""robots.txt: mặc định luôn kiểm tra; bỏ qua chỉ theo request, đúng 1 domain, có log."""
import logging

from src.fetch.base import HybridFetcher, OverrideRobotsChecker, RobotsChecker
from src.fetch.httpx_fetcher import HttpxFetcher
from src.fetch.playwright_fetcher import PlaywrightFetcher
from src.fetch.robots import HttpRobotsChecker


class _DenyAll(RobotsChecker):
    def can_fetch(self, url, user_agent):
        return False


def test_override_only_applies_to_given_domain_and_logs_warning(caplog):
    checker = OverrideRobotsChecker(_DenyAll(), "a.com", "chủ site cho phép")
    with caplog.at_level(logging.WARNING):
        assert checker.can_fetch("https://a.com/x", "ua") is True
    assert "chủ site cho phép" in caplog.text
    assert checker.can_fetch("https://b.com/x", "ua") is False


def test_playwright_default_checks_robots_not_allow_all():
    assert isinstance(PlaywrightFetcher(user_agent="ua")._robots_checker, HttpRobotsChecker)


def test_playwright_cookie_clone_keeps_robots_checker():
    fetcher = PlaywrightFetcher(user_agent="ua", robots_checker=_DenyAll())
    assert isinstance(fetcher.with_request_cookie("https://a.com", "k=v")._robots_checker, _DenyAll)


def test_with_robots_ignored_returns_clone_and_leaves_original_blocking():
    httpx_fetcher = HttpxFetcher(user_agent="ua", robots_checker=_DenyAll())
    pw = PlaywrightFetcher(user_agent="ua", robots_checker=_DenyAll())
    hybrid = HybridFetcher(httpx_fetcher, pw)

    clone = hybrid.with_robots_ignored("a.com", "lý do test")

    assert clone._primary._robots_checker.can_fetch("https://a.com/", "ua") is True
    assert clone._fallback._robots_checker.can_fetch("https://a.com/", "ua") is True
    assert httpx_fetcher._robots_checker.can_fetch("https://a.com/", "ua") is False
    assert pw._robots_checker.can_fetch("https://a.com/", "ua") is False
