"""Test route admin "/admin/*" — panel nội bộ AI gợi ý sửa lỗi + quản lý cookie
đăng nhập theo domain (CLAUDE.md mục 6: mock AI client qua `suggest_fix_fn`
injectable, không gọi AI thật). Xác nhận: Basic Auth bắt buộc, liệt kê đúng
job lỗi (cả job lịch lẫn crawl thủ công), gọi AI thành công/thất bại đều
không crash route, và audit_log được ghi lại mỗi lần gọi."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.ai.debug_assistant import DebugSuggestion
from src.api.admin import create_admin_router
from src.storage.sqlite_storage import SQLiteStorage

_ADMIN_USER = "admin"
_ADMIN_PASS = "s3cr3t"
_AUTH = (_ADMIN_USER, _ADMIN_PASS)


def _make_client(storage, suggest_fix_fn=None, **router_kwargs) -> TestClient:
    app = FastAPI()
    app.include_router(
        create_admin_router(
            storage=storage,
            ai_debug_base_url="https://greennode.example/v1",
            ai_debug_api_key="test-key",
            ai_debug_model="zhipuai/glm-4.6",
            suggest_fix_fn=suggest_fix_fn or _fake_success,
            admin_username=_ADMIN_USER,
            admin_password=_ADMIN_PASS,
            **router_kwargs,
        )
    )
    return TestClient(app)


def _fake_success(**kwargs) -> DebugSuggestion:
    return DebugSuggestion(content="1. Chẩn đoán: ...\n2. Bản vá: ...\n3. Rủi ro: ...", success=True)


def _fake_failure(**kwargs) -> DebugSuggestion:
    return DebugSuggestion(content="", success=False, error="timeout")


# ---- Basic Auth --------------------------------------------------------------
def test_admin_route_rejects_request_without_credentials():
    storage = SQLiteStorage(":memory:")
    client = _make_client(storage)

    response = client.get("/admin/errors")

    assert response.status_code == 401


def test_admin_route_rejects_wrong_credentials():
    storage = SQLiteStorage(":memory:")
    client = _make_client(storage)

    response = client.get("/admin/errors", auth=("admin", "wrong-password"))

    assert response.status_code == 401


def test_admin_route_rejects_everyone_when_not_configured():
    """Chưa set ADMIN_USERNAME/ADMIN_PASSWORD -> từ chối MẶC ĐỊNH, không mở
    cửa ngầm định (nhất quán với nguyên tắc robots.txt ở CLAUDE.md mục 3)."""
    storage = SQLiteStorage(":memory:")
    app = FastAPI()
    app.include_router(
        create_admin_router(
            storage=storage,
            ai_debug_base_url="https://greennode.example/v1",
            ai_debug_api_key="k",
            ai_debug_model="m",
        )
    )
    client = TestClient(app)

    response = client.get("/admin/errors", auth=_AUTH)

    assert response.status_code == 401


def test_admin_route_accepts_correct_credentials():
    storage = SQLiteStorage(":memory:")
    client = _make_client(storage)

    response = client.get("/admin/errors", auth=_AUTH)

    assert response.status_code == 200


# ---- /admin/errors -------------------------------------------------------
def test_list_errors_returns_empty_when_no_failed_jobs():
    storage = SQLiteStorage(":memory:")
    client = _make_client(storage)

    response = client.get("/admin/errors", auth=_AUTH)

    assert response.status_code == 200
    body = response.json()
    assert body == {"scheduled_job_errors": [], "manual_crawl_errors": []}


def test_list_errors_returns_only_jobs_with_error_status():
    storage = SQLiteStorage(":memory:")
    dataset = storage.create_dataset("A", ["x"])
    ok_job = storage.create_scheduled_job(dataset.dataset_id, "https://ok.example.com", {"x": "x"}, "interval", {"hours": 1})
    error_job = storage.create_scheduled_job(dataset.dataset_id, "https://bad.example.com", {"x": "x"}, "interval", {"hours": 1})
    storage.update_scheduled_job_run(ok_job.job_id, status="saved")
    storage.update_scheduled_job_run(error_job.job_id, status="error", traceback_text="RuntimeError: boom")

    client = _make_client(storage)
    response = client.get("/admin/errors", auth=_AUTH)

    assert response.status_code == 200
    body = response.json()
    assert len(body["scheduled_job_errors"]) == 1
    assert body["scheduled_job_errors"][0]["job_id"] == error_job.job_id
    assert body["scheduled_job_errors"][0]["last_error_traceback"] == "RuntimeError: boom"


def test_list_errors_includes_manual_crawl_failures_from_audit_log():
    """Lỗi "Chạy crawl" thủ công (không thuộc job lịch nào) ghi qua
    `_log_manual_crawl_failure` (src/api/main.py) phải xuất hiện ở đây —
    trước đây bị bỏ sót hoàn toàn, chỉ scheduled_jobs mới lên panel."""
    storage = SQLiteStorage(":memory:")
    storage.add_audit_log(
        event_type="crawl_failed",
        detail={"url": "https://batdongsan.com.vn/x", "status": "fetch_failed", "error": "http_403"},
    )

    client = _make_client(storage)
    response = client.get("/admin/errors", auth=_AUTH)

    body = response.json()
    assert len(body["manual_crawl_errors"]) == 1
    assert body["manual_crawl_errors"][0]["detail"]["error"] == "http_403"


def test_suggest_fix_returns_ai_content_for_error_job():
    storage = SQLiteStorage(":memory:")
    dataset = storage.create_dataset("A", ["x"])
    job = storage.create_scheduled_job(dataset.dataset_id, "https://bad.example.com", {"x": "x"}, "interval", {"hours": 1})
    storage.update_scheduled_job_run(job.job_id, status="error", traceback_text="RuntimeError: boom")

    client = _make_client(storage)
    response = client.post(f"/admin/errors/{job.job_id}/suggest-fix", auth=_AUTH)

    assert response.status_code == 200
    assert "Chẩn đoán" in response.json()["content"]


def test_suggest_fix_returns_404_for_unknown_job():
    storage = SQLiteStorage(":memory:")
    client = _make_client(storage)

    response = client.post("/admin/errors/does-not-exist/suggest-fix", auth=_AUTH)

    assert response.status_code == 404


def test_suggest_fix_returns_404_for_job_not_in_error_status():
    storage = SQLiteStorage(":memory:")
    dataset = storage.create_dataset("A", ["x"])
    job = storage.create_scheduled_job(dataset.dataset_id, "https://ok.example.com", {"x": "x"}, "interval", {"hours": 1})
    storage.update_scheduled_job_run(job.job_id, status="saved")

    client = _make_client(storage)
    response = client.post(f"/admin/errors/{job.job_id}/suggest-fix", auth=_AUTH)

    assert response.status_code == 404


def test_suggest_fix_ai_failure_returns_502_not_crash():
    """AI client lỗi (vd. timeout) -> route trả lỗi rõ ràng (502), KHÔNG
    crash — UI đọc được thông báo lỗi thay vì crash toàn trang."""
    storage = SQLiteStorage(":memory:")
    dataset = storage.create_dataset("A", ["x"])
    job = storage.create_scheduled_job(dataset.dataset_id, "https://bad.example.com", {"x": "x"}, "interval", {"hours": 1})
    storage.update_scheduled_job_run(job.job_id, status="error", traceback_text="RuntimeError: boom")

    client = _make_client(storage, _fake_failure)
    response = client.post(f"/admin/errors/{job.job_id}/suggest-fix", auth=_AUTH)

    assert response.status_code == 502
    assert "timeout" in response.json()["detail"]


def test_suggest_fix_writes_audit_log_on_success():
    storage = SQLiteStorage(":memory:")
    dataset = storage.create_dataset("A", ["x"])
    job = storage.create_scheduled_job(dataset.dataset_id, "https://bad.example.com", {"x": "x"}, "interval", {"hours": 1})
    storage.update_scheduled_job_run(job.job_id, status="error", traceback_text="RuntimeError: boom")

    client = _make_client(storage)
    client.post(f"/admin/errors/{job.job_id}/suggest-fix", auth=_AUTH)

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
    client.post(f"/admin/errors/{job.job_id}/suggest-fix", auth=_AUTH)

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

    client = _make_client(storage, _capturing_fake, repo_root=fake_repo)

    client.post(f"/admin/errors/{job.job_id}/suggest-fix", auth=_AUTH)

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

    client = _make_client(storage, _capturing_fake, ai_debug_timeout_seconds=90.0)

    client.post(f"/admin/errors/{job.job_id}/suggest-fix", auth=_AUTH)

    assert captured["timeout_seconds"] == 90.0


# ---- /admin/site-credentials (cookie đăng nhập thủ công theo domain) --------
def test_list_site_credentials_empty_by_default():
    storage = SQLiteStorage(":memory:")
    client = _make_client(storage)

    response = client.get("/admin/site-credentials", auth=_AUTH)

    assert response.status_code == 200
    assert response.json() == []


def test_save_site_credential_then_list_shows_it_without_leaking_cookie_value():
    storage = SQLiteStorage(":memory:")
    client = _make_client(storage)

    save_resp = client.post(
        "/admin/site-credentials",
        json={"domain": "example.com", "cookie_header": "session=abc123"},
        auth=_AUTH,
    )
    assert save_resp.status_code == 200
    assert save_resp.json()["domain"] == "example.com"

    list_resp = client.get("/admin/site-credentials", auth=_AUTH)
    body = list_resp.json()
    assert len(body) == 1
    assert body[0]["domain"] == "example.com"
    assert "cookie_header" not in body[0]  # không lộ cookie thật qua response
    assert body[0]["cookie_length"] == len("session=abc123")

    # Cookie thật vẫn được lưu đúng trong storage (chỉ ẩn ở response API).
    assert storage.get_site_credential("example.com").cookie_header == "session=abc123"


def test_save_site_credential_rejects_empty_fields():
    storage = SQLiteStorage(":memory:")
    client = _make_client(storage)

    response = client.post(
        "/admin/site-credentials", json={"domain": "", "cookie_header": "x"}, auth=_AUTH
    )

    assert response.status_code == 400


def test_delete_site_credential_removes_it():
    storage = SQLiteStorage(":memory:")
    storage.save_site_credential("example.com", "session=abc")
    client = _make_client(storage)

    response = client.delete("/admin/site-credentials/example.com", auth=_AUTH)

    assert response.status_code == 200
    assert storage.get_site_credential("example.com") is None


def test_delete_site_credential_returns_404_when_not_found():
    storage = SQLiteStorage(":memory:")
    client = _make_client(storage)

    response = client.delete("/admin/site-credentials/example.com", auth=_AUTH)

    assert response.status_code == 404


def test_save_site_credential_writes_audit_log():
    storage = SQLiteStorage(":memory:")
    client = _make_client(storage)

    client.post(
        "/admin/site-credentials",
        json={"domain": "example.com", "cookie_header": "session=abc"},
        auth=_AUTH,
    )

    entries = storage.list_audit_log()
    assert any(e.event_type == "site_credential_saved" for e in entries)
