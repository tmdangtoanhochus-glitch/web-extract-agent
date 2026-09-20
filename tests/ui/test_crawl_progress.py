"""Hai thanh tiến độ ① CODE (tải/làm sạch) và ② AI (từng đoạn) ở màn Crawl."""
import re
import threading
import time
from pathlib import Path

import httpx
import pytest
from streamlit.testing.v1 import AppTest

from ui.crawl_progress import phase_view, run_with_progress

PAGE = Path(__file__).resolve().parents[2] / "ui" / "Crawl.py"


# ---------------------------------------------------------------- phase_view (hàm thuần)
def test_no_progress_yet_means_code_is_starting_and_ai_has_not_started():
    view = phase_view(None)
    assert view["crawl_value"] == 0.0 and view["ai_value"] == 0.0
    assert "CODE" in view["who"]


def test_fetching_and_cleaning_are_code_work_ai_bar_stays_empty():
    fetch = phase_view({"phase": "fetch"})
    clean = phase_view({"phase": "clean"})
    assert "tải trang" in fetch["who"] and "CODE" in fetch["who"] and fetch["ai_value"] == 0.0
    assert "làm sạch" in clean["who"] and 0 < fetch["crawl_value"] < clean["crawl_value"] < 1.0


def test_after_cleaning_the_crawl_bar_is_full_and_shows_how_much_text_goes_to_ai():
    view = phase_view({"phase": "cleaned", "markdown_chars": 214947})
    assert view["crawl_value"] == 1.0 and "214.947" in view["crawl_label"]
    assert "sắp gửi" in view["ai_label"]


def test_ai_phase_shows_chunk_progress_and_says_the_model_is_working():
    view = phase_view({"phase": "ai", "ai_model": "qwen/qwen3.6-flash", "ai_chunks_total": 6, "ai_chunks_done": 2,
                       "ai_calling": 1, "ai_current_chunk": 3})
    assert view["ai_value"] == pytest.approx(2 / 6)
    assert "2/6" in view["ai_label"] and "đoạn 3/6" in view["ai_label"]
    assert "MODEL AI" in view["who"] and "qwen/qwen3.6-flash" in view["who"]
    assert view["crawl_value"] == 1.0  # code đã xong, đang đợi model


def test_waiting_for_rate_limit_is_explained_as_deliberate_delay_not_an_error():
    view = phase_view({"phase": "ai", "ai_chunks_total": 4, "ai_chunks_done": 1, "ai_waiting": 3, "ai_wait_seconds": 41})
    assert "chờ hạn mức" in view["who"] and "41" in view["who"] and "không phải lỗi" in view["who"]
    assert "3 đoạn chờ hạn mức" in view["ai_label"]


def test_parallel_mode_does_not_claim_a_specific_chunk_index():
    view = phase_view({"phase": "ai", "ai_chunks_total": 6, "ai_chunks_done": 1, "ai_calling": 3})
    assert "3 đoạn" in view["ai_label"] and "đoạn 2/6" not in view["ai_label"]


def test_retries_failures_and_truncation_are_visible():
    view = phase_view({"phase": "ai", "ai_chunks_total": 6, "ai_chunks_done": 4, "ai_chunks_failed": 1,
                       "ai_retries": 2, "ai_truncated": True})
    for text in ("thử lại 2", "1 đoạn lỗi", "quá dài"):
        assert text in view["ai_label"]


def test_ai_skipped_reasons_and_final_states():
    unchanged = phase_view({"phase": "done", "ai_skipped": True, "unchanged": True})
    cached = phase_view({"phase": "ai_skipped", "ai_skipped": True})
    done = phase_view({"phase": "done", "ai_chunks_total": 3, "ai_chunks_done": 3})
    assert unchanged["ai_value"] == 1.0 and "không đổi" in unchanged["ai_label"]
    assert cached["ai_value"] == 1.0 and "có sẵn" in cached["ai_label"]
    assert done["ai_value"] == 1.0 and "Hoàn tất" in done["who"]
    assert phase_view({"phase": "save", "ai_chunks_total": 3, "ai_chunks_done": 3})["who"].startswith("💾")


# ---------------------------------------------------------------- run_with_progress (luồng nền + polling)
class _Panel:
    def __init__(self):
        self.updates = []

    def update(self, data):
        self.updates.append(data)


def test_job_runs_in_background_thread_while_progress_is_polled_and_result_is_returned():
    panel, main = _Panel(), threading.get_ident()
    ran_in = {}

    def job():
        ran_in["thread"] = threading.get_ident()
        time.sleep(0.35)
        return "ket-qua"

    steps = iter(range(100))
    result = run_with_progress(job, lambda: {"phase": "ai", "n": next(steps)}, panel, interval=0.05)

    assert result == "ket-qua"
    assert ran_in["thread"] != main  # request chặn KHÔNG chạy ở luồng chính -> luồng chính rảnh để vẽ
    assert len(panel.updates) >= 3  # đã cập nhật nhiều lần trong lúc chờ, không chỉ 1 lần cuối


def test_errors_in_the_job_are_re_raised_in_the_main_thread():
    def job():
        raise RuntimeError("mất mạng")

    with pytest.raises(RuntimeError, match="mất mạng"):
        run_with_progress(job, lambda: None, _Panel(), interval=0.05)


def test_a_failing_progress_fetch_never_breaks_the_crawl():
    def fetch():
        raise ConnectionError("không lấy được tiến độ")

    assert run_with_progress(lambda: 42, fetch, _Panel(), interval=0.05) == 42


# ---------------------------------------------------------------- tích hợp trên trang Crawl
def _crawl_page_app(monkeypatch, progress_payload):
    seen = {"bodies": [], "progress_paths": []}

    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass

        def post(self, path, json=None, **kw):
            seen["bodies"].append((path, dict(json or {})))
            return httpx.Response(200, json={"status": "saved", "record_count": 1},
                                  request=httpx.Request("POST", "http://t" + path))

        def get(self, path, **kw):
            if path.startswith("/crawl-progress/"):
                seen["progress_paths"].append(path)
                return httpx.Response(200, json=progress_payload, request=httpx.Request("GET", "http://t" + path))
            return httpx.Response(200, json=[], request=httpx.Request("GET", "http://t" + path))

    monkeypatch.setattr(httpx, "Client", Client)
    app = AppTest.from_file(str(PAGE), default_timeout=30)
    app.session_state["step"] = 3
    app.session_state["urls"] = ["https://example.test/page"]
    app.session_state["fields"] = [{"name": "price", "desc": "Price"}]
    app.session_state["dataset_name"] = "History"
    return app, seen


def test_crawl_sends_a_fresh_32_hex_progress_id_and_polls_that_exact_id(monkeypatch):
    app, seen = _crawl_page_app(monkeypatch, {"phase": "done", "ai_chunks_total": 3, "ai_chunks_done": 3})
    app.run()
    next(w for w in app.button if w.label == "🚀 Chạy crawl").click().run()
    assert not app.exception

    body = next(b for path, b in seen["bodies"] if path == "/crawl")
    assert re.fullmatch(r"[0-9a-f]{32}", body["progress_id"])
    assert seen["progress_paths"] and all(path == f"/crawl-progress/{body['progress_id']}" for path in seen["progress_paths"])


def test_crawl_page_shows_two_separate_bars_and_who_is_working(monkeypatch):
    app, _ = _crawl_page_app(monkeypatch, {"phase": "done", "ai_chunks_total": 3, "ai_chunks_done": 3,
                                            "markdown_chars": 9000})
    app.run()
    next(w for w in app.button if w.label == "🚀 Chạy crawl").click().run()
    assert not app.exception

    bars = [e.proto.text for e in app.get("progress") if getattr(e.proto, "text", "")]
    assert any(text.startswith("① Crawl") for text in bars) and any(text.startswith("② AI") for text in bars)
    assert any("3/3 đoạn xong" in text for text in bars)
    assert any("Hoàn tất" in str(m.value) for m in app.markdown)


def test_progress_id_is_not_stored_in_the_saved_config_used_for_retries_and_schedules(monkeypatch):
    app, _ = _crawl_page_app(monkeypatch, {"phase": "done"})
    app.run()
    next(w for w in app.button if w.label == "🚀 Chạy crawl").click().run()
    assert "progress_id" not in app.session_state["last_crawl_config"]
    assert "progress_id" not in app.session_state["run_log"][-1]["_retry_config"]


def test_page_still_works_when_the_progress_endpoint_is_unavailable(monkeypatch):
    app, _ = _crawl_page_app(monkeypatch, None)  # /crawl-progress trả JSON null -> coi như chưa có tiến độ
    app.run()
    next(w for w in app.button if w.label == "🚀 Chạy crawl").click().run()
    assert not app.exception
    assert app.session_state["run_log"][-1]["status"] == "saved"
