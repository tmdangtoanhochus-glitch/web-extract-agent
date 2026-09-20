"""Kho tiến độ crawl trong bộ nhớ — cho UI biết ĐANG chạy code (tải/làm sạch trang) hay đang chờ model AI, và AI đang ở
đoạn thứ mấy. Chỉ chứa nhãn giai đoạn + số đếm (không có nội dung trang, cookie hay dữ liệu) và tự hết hạn.

Luồng: UI sinh `progress_id` (32 hex) gửi kèm `/crawl`; pipeline/AI client gọi `reporter(sự_kiện)` để cập nhật; UI hỏi
`GET /crawl-progress/{progress_id}` mỗi ~1 giây trong lúc `/crawl` còn đang chạy."""
from __future__ import annotations

import re
import threading
import time
from typing import Callable, Optional

PROGRESS_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
ProgressCallback = Callable[[dict], None]


class ProgressStore:
    def __init__(self, ttl_seconds: float = 900.0, max_entries: int = 500, clock: Callable[[], float] = time.monotonic):
        self._ttl = ttl_seconds
        self._max = max_entries
        self._clock = clock
        self._lock = threading.Lock()
        self._items: dict[str, tuple[float, dict]] = {}

    def _purge(self, now: float) -> None:
        for key in [k for k, (touched, _) in self._items.items() if now - touched > self._ttl]:
            del self._items[key]
        while len(self._items) > self._max:
            del self._items[min(self._items, key=lambda k: self._items[k][0])]

    def update(self, progress_id: str, event: dict) -> None:
        with self._lock:
            now = self._clock()
            self._purge(now)
            _, current = self._items.get(progress_id, (now, {}))
            self._items[progress_id] = (now, {**current, **event, "updated_at": time.time()})

    def get(self, progress_id: str) -> Optional[dict]:
        with self._lock:
            self._purge(self._clock())
            entry = self._items.get(progress_id)
            return dict(entry[1]) if entry else None

    def reporter(self, progress_id: str) -> ProgressCallback:
        return lambda event: self.update(progress_id, event)


def safe_emit(callback: Optional[ProgressCallback], event: dict) -> None:
    """Gọi callback tiến độ; lỗi ở callback KHÔNG BAO GIỜ được làm hỏng crawl."""
    if callback is None:
        return
    try:
        callback(event)
    except Exception:  # pragma: no cover - phòng thủ
        import logging

        logging.getLogger(__name__).debug("callback tiến độ lỗi, bỏ qua", exc_info=True)
