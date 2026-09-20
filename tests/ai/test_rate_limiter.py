"""Bộ giới hạn request/phút theo từng model (GreenNode: qwen 2, GLM 5...) — dùng đồng hồ giả để không phải chờ thật."""
import threading
import time

from src.ai.rate_limiter import ModelRateLimiter, parse_model_limits


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.slept = 0.0
        self.lock = threading.Lock()

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds
        self.slept += seconds


def _limiter(limits, **kw):
    clock = FakeClock()
    return ModelRateLimiter(limits, clock=clock, sleep=clock.sleep, **kw), clock


def test_parse_model_limits_reads_the_env_line_and_skips_invalid_entries():
    raw = "qwen/qwen3.6-flash=2,z-ai/glm-5.3-flash-thirdparty=5,google/gemma-4-31b-it=10,loi,x=0,y=abc, ,=3"
    assert parse_model_limits(raw) == {
        "qwen/qwen3.6-flash": 2, "z-ai/glm-5.3-flash-thirdparty": 5, "google/gemma-4-31b-it": 10,
    }
    assert parse_model_limits("") == {} and parse_model_limits(None) == {}


def test_calls_within_the_limit_do_not_wait():
    limiter, clock = _limiter({"m": 2})
    assert limiter.acquire("m") == 0 and limiter.acquire("m") == 0
    assert clock.slept == 0


def test_call_over_the_limit_waits_for_the_window_to_pass():
    limiter, clock = _limiter({"m": 2}, window_seconds=60.0, margin_seconds=1.0)
    limiter.acquire("m")
    limiter.acquire("m")
    waited = limiter.acquire("m")  # lượt thứ 3 trong 1 phút -> phải chờ hết cửa sổ (61s)
    assert 60.0 <= waited <= 62.0
    assert 60.0 <= clock.slept <= 62.0


def test_window_is_sliding_so_any_60s_span_holds_at_most_limit_calls():
    limiter, clock = _limiter({"m": 2}, window_seconds=60.0, margin_seconds=0.0)
    stamps = []
    for _ in range(6):
        limiter.acquire("m")
        stamps.append(clock.now)
    for i in range(len(stamps) - 2):
        assert stamps[i + 2] - stamps[i] >= 60.0  # 3 lượt liên tiếp không bao giờ nằm gọn trong 60s


def test_each_model_has_its_own_bucket_and_unknown_model_is_unlimited():
    limiter, clock = _limiter({"qwen": 1, "glm": 5})
    limiter.acquire("qwen")
    for _ in range(5):
        limiter.acquire("glm")  # GLM không bị ảnh hưởng bởi hạn mức của qwen
    for _ in range(50):
        limiter.acquire("model-la")  # không cấu hình = không giới hạn
    assert clock.slept == 0


def test_api_header_overrides_the_configured_limit():
    limiter, _ = _limiter({"m": 2})
    limiter.learn("m", 5)
    assert limiter.limit_for("m") == 5
    limiter.learn("khac", 3)  # model chưa cấu hình cũng học được từ header
    assert limiter.limit_for("khac") == 3


def test_penalize_blocks_every_caller_for_the_retry_after_period_even_for_unlimited_models():
    limiter, clock = _limiter({})
    limiter.penalize("m", 21)
    waited = limiter.acquire("m")
    assert 20.9 <= waited <= 22.0


def test_on_wait_reports_remaining_seconds_while_waiting():
    limiter, _ = _limiter({"m": 1}, window_seconds=10.0, margin_seconds=0.0)
    limiter.acquire("m")
    seen = []
    limiter.acquire("m", on_wait=seen.append)
    assert seen and seen[0] > 5 and seen[-1] < seen[0]  # đếm ngược giảm dần


def test_a_failing_on_wait_callback_never_breaks_the_call():
    limiter, _ = _limiter({"m": 1}, window_seconds=5.0, margin_seconds=0.0)
    limiter.acquire("m")

    def boom(_):
        raise RuntimeError("callback hỏng")
    assert limiter.acquire("m", on_wait=boom) > 0


def test_concurrent_threads_never_exceed_the_limit_in_any_window():
    """Chế độ 'Nhanh' và nhiều người dùng gọi cùng lúc: bộ giới hạn phải an toàn giữa các luồng."""
    limiter = ModelRateLimiter({"m": 2}, window_seconds=0.4, margin_seconds=0.0)
    stamps, lock = [], threading.Lock()

    def worker():
        limiter.acquire("m")
        with lock:
            stamps.append(time.monotonic())

    threads = [threading.Thread(target=worker) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    stamps.sort()
    assert len(stamps) == 6
    for i in range(len(stamps) - 2):
        assert stamps[i + 2] - stamps[i] >= 0.35  # cho phép sai số đồng hồ nhỏ
