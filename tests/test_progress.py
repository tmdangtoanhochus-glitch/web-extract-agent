"""Kho tiến độ crawl trong bộ nhớ: gộp sự kiện, tự hết hạn, giới hạn số mục, callback lỗi không làm hỏng crawl."""
from src.progress import PROGRESS_ID_PATTERN, ProgressStore, safe_emit


class Clock:
    now = 0.0

    def __call__(self):
        return self.now


def test_update_merges_events_and_get_returns_a_copy():
    store = ProgressStore()
    store.update("a" * 32, {"phase": "fetch", "ai_chunks_total": 0})
    store.update("a" * 32, {"phase": "ai", "ai_chunks_total": 3})
    data = store.get("a" * 32)
    assert data["phase"] == "ai" and data["ai_chunks_total"] == 3 and "updated_at" in data
    data["phase"] = "bi-sua"
    assert store.get("a" * 32)["phase"] == "ai"  # không sửa được kho từ bên ngoài


def test_unknown_id_returns_none():
    assert ProgressStore().get("b" * 32) is None


def test_entries_expire_after_ttl():
    clock = Clock()
    store = ProgressStore(ttl_seconds=100, clock=clock)
    store.update("a" * 32, {"phase": "ai"})
    clock.now = 99
    assert store.get("a" * 32) is not None
    clock.now = 101
    assert store.get("a" * 32) is None


def test_store_is_bounded_and_evicts_the_oldest_entry():
    clock = Clock()
    store = ProgressStore(max_entries=3, clock=clock)
    for i in range(5):
        clock.now = i
        store.update(f"{i:032x}", {"phase": "ai"})
    assert store.get(f"{0:032x}") is None and store.get(f"{1:032x}") is None
    assert store.get(f"{4:032x}") is not None


def test_reporter_writes_into_the_given_id():
    store = ProgressStore()
    store.reporter("c" * 32)({"phase": "clean"})
    assert store.get("c" * 32)["phase"] == "clean"


def test_progress_id_must_be_32_lowercase_hex():
    assert PROGRESS_ID_PATTERN.match("0123456789abcdef0123456789abcdef")
    for bad in ("", "abc", "G" * 32, "a" * 31, "a" * 33, "../etc/passwd", "A" * 32):
        assert not PROGRESS_ID_PATTERN.match(bad)


def test_safe_emit_ignores_none_and_swallows_callback_errors():
    safe_emit(None, {"phase": "x"})

    def boom(_):
        raise RuntimeError("UI hỏng")

    safe_emit(boom, {"phase": "x"})  # không raise
