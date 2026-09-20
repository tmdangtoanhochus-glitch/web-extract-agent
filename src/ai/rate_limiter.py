"""Giới hạn tốc độ gọi AI theo TỪNG MODEL.

GreenNode MaaS đặt số request/phút riêng cho từng model (đo thật: qwen 2, GLM 5) và trả 429 kèm `Retry-After`
khi vượt. Thay vì bắn rồi nhận 429, mọi lời gọi AI đi qua `acquire()` để tự xếp hàng (delay) đúng hạn mức.

- Cửa sổ TRƯỢT (không phải cửa sổ cố định của server): mọi khoảng 60 giây liền nhau chứa tối đa N lượt gọi, nên luôn
  an toàn với cửa sổ cố định phía server. Có `margin_seconds` để bù độ trễ mạng giữa lúc ta gửi và lúc server tính.
- Hạn mức lấy từ `AI_MODEL_LIMITS` (vd. `qwen/qwen3.6-flash=2,z-ai/glm-5.3-flash-thirdparty=5`); khi API trả header
  `x-ratelimit-limit-minute` thì HEADER LÀ CHUẨN, ghi đè số cấu hình (xem `learn`).
- Model không có hạn mức → không giới hạn (chỉ áp dụng phạt sau khi gặp 429, xem `penalize`).
- An toàn giữa nhiều luồng (chế độ "Nhanh" gọi song song, nhiều người dùng crawl cùng lúc)."""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def parse_model_limits(raw: Optional[str]) -> dict[str, int]:
    """`"modelA=2,modelB=5"` -> `{"modelA": 2, "modelB": 5}`. Mục sai định dạng bị bỏ qua kèm cảnh báo
    (gõ nhầm 1 mục không làm sập cả dịch vụ)."""
    limits: dict[str, int] = {}
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        model, sep, value = part.rpartition("=")
        model = model.strip()
        try:
            number = int(value.strip())
        except ValueError:
            number = 0
        if not sep or not model or number <= 0:
            logger.warning("AI_MODEL_LIMITS: bỏ qua mục không hợp lệ %r (dạng đúng: model=số_request_mỗi_phút)", part)
            continue
        limits[model] = number
    return limits


class ModelRateLimiter:
    def __init__(
        self,
        limits: Optional[dict[str, int]] = None,
        window_seconds: float = 60.0,
        margin_seconds: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._limits = dict(limits or {})
        self._window = window_seconds + margin_seconds
        self._clock = clock
        self._sleep = sleep
        self._calls: dict[str, deque[float]] = {}
        self._blocked_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def limit_for(self, model: str) -> Optional[int]:
        with self._lock:
            return self._limits.get(model)

    def learn(self, model: str, limit: int) -> None:
        """Header của API là nguồn chuẩn: nếu khác số đang dùng thì cập nhật (BTC nâng/hạ hạn mức là tự khớp)."""
        if limit <= 0:
            return
        with self._lock:
            if self._limits.get(model) != limit:
                logger.info("Hạn mức AI của %s cập nhật theo header API: %s request/phút.", model, limit)
                self._limits[model] = limit

    def penalize(self, model: str, seconds: float) -> None:
        """Sau khi nhận 429: chặn MỌI luồng gọi model này trong `seconds` (theo `Retry-After`)."""
        with self._lock:
            self._blocked_until[model] = max(self._blocked_until.get(model, 0.0), self._clock() + max(seconds, 0.0))

    def acquire(self, model: str, on_wait: Optional[Callable[[float], None]] = None) -> float:
        """Chặn cho tới khi được phép gọi `model` rồi giữ chỗ 1 lượt. `on_wait(giây_còn_lại)` được gọi mỗi ~1 giây
        khi đang chờ (để UI hiện đếm ngược). Trả về tổng số giây đã chờ."""
        waited = 0.0
        while True:
            with self._lock:
                now = self._clock()
                wait = max(self._blocked_until.get(model, 0.0) - now, 0.0)
                if wait == 0.0:
                    limit = self._limits.get(model)
                    if not limit:
                        return waited
                    calls = self._calls.setdefault(model, deque())
                    while calls and now - calls[0] >= self._window:
                        calls.popleft()
                    if len(calls) < limit:
                        calls.append(now)
                        return waited
                    wait = calls[0] + self._window - now
            if on_wait is not None:
                try:
                    on_wait(wait)
                except Exception:  # callback tiến độ không bao giờ được làm hỏng lời gọi AI
                    logger.debug("on_wait lỗi, bỏ qua", exc_info=True)
            step = min(max(wait, 0.05), 1.0)
            self._sleep(step)
            waited += step
