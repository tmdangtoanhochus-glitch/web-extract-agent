from pathlib import Path
import httpx
from streamlit.testing.v1 import AppTest

PAGE = Path(__file__).resolve().parents[2] / "ui" / "app.py"


def test_cookie_and_report_after_rendering_error(monkeypatch):
    calls = []
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, path, json):
            calls.append((path, dict(json)))
            if path == "/crawl":
                # Unhashable status triggers TypeError in result rendering after successful fetch.
                return httpx.Response(200, json={"dataset_id": "d1", "status": [], "confidence": "bad"},
                                      headers={"X-Crawl-Request-ID": "00000000-0000-0000-0000-000000000001"})
            return httpx.Response(201, json={"report_id": "r1"})
    monkeypatch.setattr(httpx, "Client", Client)
    app = AppTest.from_file(str(PAGE))
    app.session_state["step"] = 3
    app.session_state["urls"] = ["https://example.test/table?query=synthetic"]
    app.session_state["fields"] = [{"name": "price", "desc": "Price"}]
    app.session_state["dataset_name"] = "History"
    app.run()
    assert not app.exception
    next(w for w in app.text_input if w.label == "Cookie cho lượt kéo").set_value("session=synthetic-cookie")
    next(w for w in app.button if w.label == "🚀 Chạy crawl").click().run()
    assert not app.exception
    assert app.session_state["crawl_ui_error"]["error_type"] == "TypeError"
    next(w for w in app.button if w.label == "Gửi báo lỗi").click().run()
    payload = next(body for path, body in calls if path == "/crawl-reports")
    assert payload["error_type"] == "TypeError"
    assert payload["request_id"].endswith("1")
    assert "synthetic" not in str(payload)
    assert "cookie_header" not in app.session_state["last_crawl_config"]


def test_bulk_handoff_preserves_dataset_columns_and_rolling_dates(monkeypatch):
    calls = []
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, path):
            data = [{"dataset_id": "history", "dataset_name": "History", "schema_signature": ["day"]}] if path == "/datasets" else []
            return httpx.Response(200, json=data, request=httpx.Request("GET", "http://test" + path))
        def post(self, path, json):
            calls.append((path, json))
            return httpx.Response(200, json={"job_id": "j1"})
    monkeypatch.setattr(httpx, "Client", Client)
    app = AppTest.from_file(str(PAGE))
    app.session_state["step"] = 5
    app.session_state["last_crawl_config"] = {
        "url": "https://example.test/?from={start}&to={end}", "dataset_id": "history",
        "field_descriptions": {"day": "date"},
        "crawl_options": {"mode": "table", "columns": {"day": 1}, "date_field": "day",
                          "start_date": "2026-09-01", "end_date": "2026-09-16"}}
    app.run()
    assert not app.exception
    next(w for w in app.button if w.label == "Tạo lịch append theo cấu hình này").click().run()
    body = next(body for path, body in calls if path == "/schedules")
    assert body["dataset_id"] == "history" and body["crawl_options"]["columns"] == {"day": 1}
    assert body["crawl_options"]["lookback_days"] == 7
    assert "start_date" not in body["crawl_options"]


def test_preview_and_report_work_without_a_ui_exception(monkeypatch):
    calls = []
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, path, json):
            calls.append((path, dict(json)))
            if path == "/crawl/preview":
                return httpx.Response(200, json={"status": "preview", "requests": 1,
                    "fetched_pages": 1, "plan": [{"index": 1}], "matched_rows": 1, "sample": [{"price": "10"}]},
                    headers={"X-Crawl-Request-ID": "00000000-0000-0000-0000-000000000002"})
            return httpx.Response(201, json={"report_id": "r2"})
    monkeypatch.setattr(httpx, "Client", Client)
    app = AppTest.from_file(str(PAGE))
    app.session_state["step"] = 3
    app.session_state["urls"] = ["https://example.test/table"]
    app.session_state["fields"] = [{"name": "price", "desc": "Price"}]
    app.session_state["dataset_name"] = "History"
    app.run()
    next(w for w in app.checkbox if w.label == "Kéo nhiều lượt / kéo bảng").check().run()
    next(w for w in app.radio if w.label == "Kiểu dữ liệu").set_value("Bảng HTML").run()
    next(w for w in app.button if w.label == "Xem trước đợt kéo").click().run()
    assert not app.exception and not app.session_state["run_log"]
    assert "last_crawl_config" not in app.session_state
    next(w for w in app.button if w.label == "Gửi báo lỗi").click().run()
    assert not app.exception
    report = next(body for path, body in calls if path == "/crawl-reports")
    assert report["error_type"] == "Other" and report["request_id"].endswith("2")
    assert not any(path == "/crawl" for path, _ in calls)


def test_retry_uses_original_config_and_fresh_cookie_without_retaining_it(monkeypatch):
    calls = []
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, path, json):
            calls.append((path, dict(json)))
            return httpx.Response(200, json={"status": "completed", "request_id": "r-new",
                "dataset_id": "d1", "requests": 1, "saved": 1, "failed": 0, "skipped": 0,
                "results": [{"index": 2, "status": "saved"}]}, headers={"X-Crawl-Request-ID": "r-new"})
    monkeypatch.setattr(httpx, "Client", Client)
    app = AppTest.from_file(str(PAGE))
    app.session_state["step"] = 3
    app.session_state["urls"] = ["https://changed.test/"]
    app.session_state["fields"] = [{"name": "changed", "desc": "Changed"}]
    app.session_state["run_log"] = [{"url": "https://example.test/?page={page}",
        "request_id": "r-old", "dataset_id": "d1", "status": "partial", "failed": 1,
        "_retry_config": {"url": "https://example.test/?page={page}",
            "field_descriptions": {"id": "Identifier"}, "dataset_name": "History",
            "crawl_options": {"mode": "table", "pages": 2, "columns": {"id": 1}}}}]
    app.run()
    next(w for w in app.text_input if w.label == "Cookie mới cho nguồn này (nếu cần)").set_value("session=synthetic")
    next(w for w in app.button if w.label == "Chạy lại lượt lỗi").click().run()
    assert not app.exception
    body = calls[0][1]
    assert body["retry_of"] == "r-old" and body["dataset_id"] == "d1"
    assert body["field_descriptions"] == {"id": "Identifier"}
    assert body["cookie_origin"] == "https://example.test" and body["cookie_header"] == "session=synthetic"
    assert "cookie_header" not in app.session_state["run_log"][-1]["_retry_config"]
