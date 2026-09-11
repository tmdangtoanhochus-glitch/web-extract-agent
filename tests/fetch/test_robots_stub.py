"""Test riêng cho AllowAllRobotsChecker — xác nhận rõ đây là stub luôn cho phép,
không phải logic robots.txt thật (xem docstring trong src/fetch/base.py)."""
from src.fetch.base import AllowAllRobotsChecker


def test_allow_all_robots_checker_always_allows():
    checker = AllowAllRobotsChecker()

    assert checker.can_fetch("https://example.com/", "any-agent") is True
    assert checker.can_fetch("https://disallowed.example.com/private", "any-agent") is True
