"""Rate-limit theo domain (CLAUDE.md mục 3) — tách riêng để `HttpxFetcher` và
`PlaywrightFetcher` dùng chung, không lặp lại logic giữa 2 fetch engine.

Thuật toán "đặt chỗ" (reservation): mỗi domain giữ mốc thời gian sớm nhất được
phép fetch tiếp theo; request mới chờ tới mốc đó rồi tự đặt chỗ mốc kế tiếp =
mốc vừa chờ + `delay_seconds`. Giữ lock khi TÍNH và ĐẶT CHỖ (không giữ lock lúc
sleep) để nhiều request đồng thời cùng domain xếp hàng đúng khoảng cách thay vì
cùng đọc mốc cũ rồi cùng sleep 1 khoảng như nhau (thundering herd).
"""
from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)


class DomainRateLimiter:
    def __init__(self, delay_seconds: float = 0.0) -> None:
        self._delay_seconds = delay_seconds
        self._next_allowed_at: dict[str, float] = {}
        self._lock = threading.Lock()

    def wait(self, domain: str) -> None:
        if self._delay_seconds <= 0:
            return

        with self._lock:
            now = time.monotonic()
            start_at = max(now, self._next_allowed_at.get(domain, now))
            self._next_allowed_at[domain] = start_at + self._delay_seconds

        wait_seconds = start_at - now
        if wait_seconds > 0:
            logger.debug("Rate-limit domain %s: chờ %.2fs.", domain, wait_seconds)
            time.sleep(wait_seconds)
