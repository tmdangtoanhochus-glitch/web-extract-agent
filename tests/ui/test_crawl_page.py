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


def test_export_all_is_explicit_and_cached_file_hidden_when_filter_changes(monkeypatch):
    calls = []
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, path):
            calls.append(path)
            request = httpx.Request("GET", "http://test" + path)
            if path == "/datasets":
                return httpx.Response(200, json=[{"dataset_id": "history", "dataset_name": "History", "schema_signature": ["id"]}], request=request)
            if "export.csv" in path:
                return httpx.Response(200, content=b"data.id\r\n1\r\n", request=request)
            return httpx.Response(200, json=[], request=request)
    monkeypatch.setattr(httpx, "Client", Client)
    app = AppTest.from_file(str(PAGE))
    app.session_state["step"] = 4
    app.run()
    assert not app.exception and not any("export.csv" in p for p in calls)
    next(w for w in app.button if w.label == "Chuẩn bị CSV toàn bộ").click().run()
    assert app.session_state["dataset_csv_download"]["path"] == "/datasets/history/export.csv"
    assert len(app.get("download_button")) == 1
    next(w for w in app.checkbox if w.label == "Lọc khoảng ngày khi xuất").check().run()
    assert not app.exception and len(app.get("download_button")) == 0
    next(w for w in app.button if w.label == "Chuẩn bị CSV toàn bộ").click().run()
    assert "date_basis=crawled_at" in app.session_state["dataset_csv_download"]["path"]
    next(w for w in app.button if w.label == "Xóa file đã chuẩn bị khỏi phiên").click().run()
    assert "dataset_csv_download" not in app.session_state


def test_current_page_csv_escapes_formula_cells_and_headers():
    import ast
    import csv
    import io
    tree = ast.parse(PAGE.read_text(encoding="utf-8"))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_records_to_csv")
    namespace = {"csv": csv, "io": io}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(PAGE), "exec"), namespace)
    content = namespace["_records_to_csv"]([{"record_id": "r", "source_url": "https://example.test",
        "crawled_at": "2026-09-16", "data": {"=header": "\t=SUM(1,2)", "number": -12}}])
    rows = list(csv.reader(io.StringIO(content)))
    assert "'=header" in rows[0] and "'\t=SUM(1,2)" in rows[1] and "-12" in rows[1]


def test_background_submission_and_pause_resume_controls(monkeypatch):
    import copy
    calls = []
    state = {"value": "running"}
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, path, json, headers=None):
            calls.append((path, copy.deepcopy(json), headers))
            if path == "/crawl-jobs":
                data = {"id": "job1", "control": "synthetic-control", "state": "queued"}
            else:
                state["value"] = "paused" if json["action"] == "pause" else "running"
                data = {"state": state["value"]}
            return httpx.Response(200, json=data, request=httpx.Request("POST", "http://test" + path))
        def get(self, path, headers=None):
            assert headers == {"X-Crawl-Control": "synthetic-control"}
            return httpx.Response(200, json={"id": "job1", "state": state["value"],
                "progress": {"sources": 1, "source_index": 1, "requests": 2, "processed": 1,
                             "request_id": "00000000-0000-0000-0000-000000000001"}},
                request=httpx.Request("GET", "http://test" + path))
    monkeypatch.setattr(httpx, "Client", Client)
    app = AppTest.from_file(str(PAGE))
    app.session_state["step"] = 3
    app.session_state["urls"] = ["https://example.test/?page={page}"]
    app.session_state["fields"] = [{"name": "id", "desc": "Identifier"}]
    app.session_state["dataset_name"] = "History"
    app.run()
    next(w for w in app.checkbox if w.label == "Kéo nhiều lượt / kéo bảng").check().run()
    next(w for w in app.text_input if w.label == "Cookie cho lượt kéo").set_value("session=synthetic-cookie")
    next(w for w in app.button if w.label == "🚀 Chạy crawl").click().run()
    assert not app.exception
    assert calls[0][0] == "/crawl-jobs"
    assert calls[0][1]["requests"][0]["cookie_header"] == "session=synthetic-cookie"
    assert "cookie_header" not in app.session_state["active_crawl_job"]["configs"][0]
    next(w for w in app.button if w.label == "Tạm dừng crawl").click().run()
    assert not app.exception and state["value"] == "paused"
    next(w for w in app.button if w.label == "Tiếp tục crawl").click().run()
    assert not app.exception and state["value"] == "running"


def test_schedule_pause_and_timing_edit_do_not_change_crawl_config(monkeypatch):
    calls = []
    job = {"job_id": "j1", "dataset_id": "d1", "url": "https://example.test/", "enabled": True,
           "trigger_type": "interval", "trigger_args": {"hours": 2}, "timezone": "UTC"}
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, path):
            data = [job] if path == "/schedules" else [{"dataset_id": "d1", "dataset_name": "History", "schema_signature": ["id"]}] if path == "/datasets" else []
            return httpx.Response(200, json=data, request=httpx.Request("GET", "http://test" + path))
        def patch(self, path, json):
            calls.append((path, dict(json)))
            job.update(json)
            return httpx.Response(200, json=job)
    monkeypatch.setattr(httpx, "Client", Client)
    app = AppTest.from_file(str(PAGE))
    app.session_state["step"] = 5
    app.run()
    next(w for w in app.button if w.label == "Tạm dừng lịch").click().run()
    assert not app.exception and job["enabled"] is False
    next(w for w in app.number_input if w.label == "Chu kỳ mới (giờ)").set_value(6)
    next(w for w in app.button if w.label == "Lưu thời gian mới").click().run()
    assert not app.exception and job["trigger_args"]["hours"] == 6 and job["enabled"] is False
    assert all(set(body) <= {"enabled", "trigger_type", "trigger_args"} for _, body in calls)
    assert job["dataset_id"] == "d1" and job["url"] == "https://example.test/"
