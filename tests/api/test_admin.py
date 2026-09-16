"""Test route admin "/admin/errors" — panel nội bộ AI gợi ý sửa lỗi
(CLAUDE.md mục 6: mock AI client qua `suggest_fix_fn` injectable, không gọi
AI thật). Xác nhận: liệt kê đúng job lỗi, gọi AI thành công/thất bại đều
không crash route, và audit_log được ghi lại mỗi lần gọi."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.ai.debug_assistant import DebugSuggestion
from src.api.admin import create_admin_router
from src.storage.sqlite_storage import SQLiteStorage


def _make_client(storage, suggest_fix_fn) -> TestClient:
    app = FastAPI()
    app.include_router(
        create_admin_router(
            storage=storage,
            ai_debug_base_url="https://greennode.example/v1",
            ai_debug_api_key="test-key",
            ai_debug_model="zhipuai/glm-4.6",
            suggest_fix_fn=suggest_fix_fn,
        )
    )
    return TestClient(app)


def _fake_success(**kwargs) -> DebugSuggestion:
    return DebugSuggestion(content="1. Chẩn đoán: ...\n2. Bản vá: ...\n3. Rủi ro: ...", success=True)


def _fake_failure(**kwargs) -> DebugSuggestion:
    return DebugSuggestion(content="", success=False, error="timeout")


def test_list_errors_returns_empty_when_no_failed_jobs():
    storage = SQLiteStorage(":memory:")
    client = _make_client(storage, _fake_success)

    response = client.get("/admin/errors")

    assert response.status_code == 200
    assert response.json() == []


def test_list_errors_returns_only_jobs_with_error_status():
    storage = SQLiteStorage(":memory:")
    dataset = storage.create_dataset("A", ["x"])
    ok_job = storage.create_scheduled_job(dataset.dataset_id, "https://ok.example.com", {"x": "x"}, "interval", {"hours": 1})
    error_job = storage.create_scheduled_job(dataset.dataset_id, "https://bad.example.com", {"x": "x"}, "interval", {"hours": 1})
    storage.update_scheduled_job_run(ok_job.job_id, status="saved")
    storage.update_scheduled_job_run(error_job.job_id, status="error", traceback_text="RuntimeError: boom")

    client = _make_client(storage, _fake_success)
    response = client.get("/admin/errors")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["job_id"] == error_job.job_id
    assert body[0]["last_error_traceback"] == "RuntimeError: boom"


def test_suggest_fix_returns_ai_content_for_error_job():
    storage = SQLiteStorage(":memory:")
    dataset = storage.create_dataset("A", ["x"])
    job = storage.create_scheduled_job(dataset.dataset_id, "https://bad.example.com", {"x": "x"}, "interval", {"hours": 1})
    storage.update_scheduled_job_run(job.job_id, status="error", traceback_text="RuntimeError: boom")

    client = _make_client(storage, _fake_success)
    response = client.post(f"/admin/errors/{job.job_id}/suggest-fix")

    assert response.status_code == 200
    assert "Chẩn đoán" in response.json()["content"]


def test_suggest_fix_returns_404_for_unknown_job():
    storage = SQLiteStorage(":memory:")
    client = _make_client(storage, _fake_success)

    response = client.post("/admin/errors/does-not-exist/suggest-fix")

    assert response.status_code == 404


def test_suggest_fix_returns_404_for_job_not_in_error_status():
    storage = SQLiteStorage(":memory:")
    dataset = storage.create_dataset("A", ["x"])
    job = storage.create_scheduled_job(dataset.dataset_id, "https://ok.example.com", {"x": "x"}, "interval", {"hours": 1})
    storage.update_scheduled_job_run(job.job_id, status="saved")

    client = _make_client(storage, _fake_success)
    response = client.post(f"/admin/errors/{job.job_id}/suggest-fix")

    assert response.status_code == 404


def test_suggest_fix_ai_failure_returns_502_not_crash(caplog):
    """AI client lỗi (vd. timeout) -> route trả lỗi rõ ràng (502), KHÔNG
    crash — UI đọc được thông báo lỗi thay vì crash toàn trang."""
    storage = SQLiteStorage(":memory:")
    dataset = storage.create_dataset("A", ["x"])
    job = storage.create_scheduled_job(dataset.dataset_id, "https://bad.example.com", {"x": "x"}, "interval", {"hours": 1})
    storage.update_scheduled_job_run(job.job_id, status="error", traceback_text="RuntimeError: boom")

    client = _make_client(storage, _fake_failure)
    response = client.post(f"/admin/errors/{job.job_id}/suggest-fix")

    assert response.status_code == 502
    assert "timeout" in response.json()["detail"]


def test_suggest_fix_writes_audit_log_on_success():
    storage = SQLiteStorage(":memory:")
    dataset = storage.create_dataset("A", ["x"])
    job = storage.create_scheduled_job(dataset.dataset_id, "https://bad.example.com", {"x": "x"}, "interval", {"hours": 1})
    storage.update_scheduled_job_run(job.job_id, status="error", traceback_text="RuntimeError: boom")

    client = _make_client(storage, _fake_success)
    client.post(f"/admin/errors/{job.job_id}/suggest-fix")

    entries = storage.list_audit_log(job_id=job.job_id)
    assert len(entries) == 1
    assert entries[0].event_type == "debug_suggest_fix"
    assert entries[0].detail["ai_call_success"] is True


def test_suggest_fix_writes_audit_log_on_ai_failure_too():
    storage = SQLiteStorage(":memory:")
    dataset = storage.create_dataset("A", ["x"])
    job = storage.create_scheduled_job(dataset.dataset_id, "https://bad.example.com", {"x": "x"}, "interval", {"hours": 1})
    storage.update_scheduled_job_run(job.job_id, status="error", traceback_text="RuntimeError: boom")

    client = _make_client(storage, _fake_failure)
    client.post(f"/admin/errors/{job.job_id}/suggest-fix")

    entries = storage.list_audit_log(job_id=job.job_id)
    assert len(entries) == 1
    assert entries[0].detail["ai_call_success"] is False
    assert entries[0].detail["error"] == "timeout"


def test_suggest_fix_passes_traceback_and_repo_code_to_ai_fn(tmp_path):
    """`related_code` phải lấy đúng nội dung file có thật trong traceback,
    CHỈ ĐỌC (không có cách nào route này ghi file)."""
    storage = SQLiteStorage(":memory:")
    dataset = storage.create_dataset("A", ["x"])
    job = storage.create_scheduled_job(dataset.dataset_id, "https://bad.example.com", {"x": "x"}, "interval", {"hours": 1})

    fake_repo = tmp_path
    (fake_repo / "src").mkdir()
    (fake_repo / "src" / "pipeline.py").write_text("def run_crawl_job():\n    pass\n", encoding="utf-8")
    traceback_text = 'Traceback...\n  File "src/pipeline.py", line 1, in run_crawl_job\nKeyError'
    storage.update_scheduled_job_run(job.job_id, status="error", traceback_text=traceback_text)

    captured = {}

    def _capturing_fake(**kwargs) -> DebugSuggestion:
        captured.update(kwargs)
        return DebugSuggestion(content="ok", success=True)

    app = FastAPI()
    app.include_router(
        create_admin_router(
            storage=storage,
            ai_debug_base_url="https://greennode.example/v1",
            ai_debug_api_key="k",
            ai_debug_model="m",
            repo_root=fake_repo,
            suggest_fix_fn=_capturing_fake,
        )
    )
    client = TestClient(app)

    client.post(f"/admin/errors/{job.job_id}/suggest-fix")

    assert captured["traceback_text"] == traceback_text
    assert "def run_crawl_job" in captured["related_code"]
    assert job.url in captured["context_note"]


def test_suggest_fix_passes_configured_timeout_to_ai_fn():
    """`ai_debug_timeout_seconds` phải đọc từ cấu hình (`.env` qua Settings),
    không hardcode — xác nhận route truyền đúng giá trị xuống suggest_fix_fn."""
    storage = SQLiteStorage(":memory:")
    dataset = storage.create_dataset("A", ["x"])
    job = storage.create_scheduled_job(dataset.dataset_id, "https://bad.example.com", {"x": "x"}, "interval", {"hours": 1})
    storage.update_scheduled_job_run(job.job_id, status="error", traceback_text="RuntimeError: boom")

    captured = {}

    def _capturing_fake(**kwargs) -> DebugSuggestion:
        captured.update(kwargs)
        return DebugSuggestion(content="ok", success=True)

    app = FastAPI()
    app.include_router(
        create_admin_router(
            storage=storage,
            ai_debug_base_url="https://greennode.example/v1",
            ai_debug_api_key="k",
            ai_debug_model="m",
            ai_debug_timeout_seconds=90.0,
            suggest_fix_fn=_capturing_fake,
        )
    )
    client = TestClient(app)

    client.post(f"/admin/errors/{job.job_id}/suggest-fix")

    assert captured["timeout_seconds"] == 90.0
