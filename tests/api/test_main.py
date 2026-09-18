"""Test API bằng FastAPI TestClient + test double cho fetch/AI, storage
in-memory thật — không gọi mạng/AI/endpoint thật (CLAUDE.md mục 6)."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from src.ai.base import AIClient, ExtractionResult, FieldExtraction
from src.api.main import create_app
from src.fetch.base import FetchEngine, FetchResult, utcnow
from src.storage.file_writer import EXPORTS_ROOT
from src.storage.sqlite_storage import SQLiteStorage


class _FakeFetcher(FetchEngine):
    def __init__(self, html: str | None = "<html><body><p>giá 75.000.000</p></body></html>"):
        self._html = html

    def fetch(self, url: str) -> FetchResult:
        if self._html is None:
            return FetchResult(
                url=url, final_url=url, status_code=404, html=None,
                fetched_at=utcnow(), success=False, error="not_found",
            )
        return FetchResult(
            url=url, final_url=url, status_code=200, html=self._html,
            fetched_at=utcnow(), success=True,
        )


class _FakeAIClient(AIClient):
    def __init__(self, success: bool = True, error: str | None = None):
        self._success = success
        self._error = error

    def extract(self, markdown: str, field_descriptions: dict[str, str]) -> ExtractionResult:
        if not self._success:
            return ExtractionResult(success=False, error=self._error)
        return ExtractionResult(
            records=[{
                name: FieldExtraction(value="giá trị mẫu", confidence=0.9, evidence="bằng chứng")
                for name in field_descriptions
            }],
            raw_response="{}",
            success=True,
        )


_ADMIN_AUTH = ("admin", "test-admin-pass")


@pytest.fixture
def client():
    fetcher = _FakeFetcher()
    ai_client = _FakeAIClient()
    storage = SQLiteStorage(":memory:")
    app = create_app(
        fetcher=fetcher, ai_client=ai_client, storage=storage,
        admin_username=_ADMIN_AUTH[0], admin_password=_ADMIN_AUTH[1],
    )
    return TestClient(app)


def test_health_returns_200_ok(client):
    """Liveness cho nền tảng deploy (GreenNode AgentBase) — không phụ thuộc
    DB/AI, không cần setup gì thêm ngoài `client` fixture chuẩn."""
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_runner_login_boundary_does_not_gate_public_crawl(tmp_path):
    from src.runner.repository import Repository
    from src.runner.service import Service
    repo = Repository()
    storage = SQLiteStorage(":memory:")
    app = create_app(fetcher=_FakeFetcher(), ai_client=_FakeAIClient(), storage=storage,
                     runner_service=Service(repo, tmp_path / "runner"))
    client = TestClient(app)
    try:
        response = client.post("/crawl", json={"url": "https://example.test", "field_descriptions": {"price": "giá"}, "dataset_name": "Public"})
        assert response.status_code == 200
        for route in ("/runner/me", "/runner/runs", "/runner/agents", "/runner/authoring/capabilities"):
            assert client.get(route).status_code == 401
        assert client.post("/runner/authoring/describe", json={"description": "Điền role rồi đăng nhập", "reviewed_no_secrets": True}).status_code == 401
    finally:
        repo.close()


def test_crawl_creates_dataset_and_returns_saved_status(client):
    response = client.post(
        "/crawl",
        json={
            "url": "https://example.com/gold",
            "field_descriptions": {"price": "giá vàng"},
            "dataset_name": "Giá vàng SJC",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "saved"
    assert body["dataset_id"]
    assert body["record_id"]
    assert body["data"] == {"price": "giá trị mẫu"}
    assert body["needs_review"] is False  # confidence 0.9 >= ngưỡng mặc định 0.7


def test_crawl_flags_needs_review_when_confidence_below_configured_threshold():
    fetcher = _FakeFetcher()
    ai_client = _FakeAIClient()  # confidence cố định 0.9
    storage = SQLiteStorage(":memory:")
    app = create_app(fetcher=fetcher, ai_client=ai_client, storage=storage, confidence_threshold=0.95)
    client = TestClient(app)

    response = client.post(
        "/crawl",
        json={
            "url": "https://example.com/gold",
            "field_descriptions": {"price": "giá vàng"},
            "dataset_name": "Giá vàng SJC",
        },
    )

    assert response.status_code == 200
    assert response.json()["needs_review"] is True  # 0.9 < 0.95


def test_crawl_still_saves_record_even_when_needs_review_is_true():
    fetcher = _FakeFetcher()
    ai_client = _FakeAIClient()
    storage = SQLiteStorage(":memory:")
    app = create_app(fetcher=fetcher, ai_client=ai_client, storage=storage, confidence_threshold=0.95)
    client = TestClient(app)

    response = client.post(
        "/crawl",
        json={
            "url": "https://example.com/gold",
            "field_descriptions": {"price": "giá vàng"},
            "dataset_name": "Giá vàng SJC",
        },
    )

    assert response.json()["status"] == "saved"  # KHÔNG bị chặn lưu


def test_crawl_without_dataset_id_or_dataset_name_returns_422(client):
    response = client.post(
        "/crawl", json={"url": "https://example.com/x", "field_descriptions": {"price": "giá"}}
    )

    assert response.status_code == 422


def test_crawl_with_empty_field_descriptions_returns_422(client):
    response = client.post(
        "/crawl",
        json={"url": "https://example.com/x", "field_descriptions": {}, "dataset_name": "X"},
    )

    assert response.status_code == 422


def test_crawl_with_unknown_dataset_id_returns_404(client):
    response = client.post(
        "/crawl",
        json={
            "url": "https://example.com/x",
            "field_descriptions": {"price": "giá"},
            "dataset_id": "does-not-exist",
        },
    )

    assert response.status_code == 404


def test_crawl_fetch_failure_returns_502():
    fetcher = _FakeFetcher(html=None)
    ai_client = _FakeAIClient()
    storage = SQLiteStorage(":memory:")
    app = create_app(fetcher=fetcher, ai_client=ai_client, storage=storage)
    client = TestClient(app)

    response = client.post(
        "/crawl",
        json={
            "url": "https://example.com/missing",
            "field_descriptions": {"price": "giá"},
            "dataset_name": "X",
        },
    )

    assert response.status_code == 502


def test_list_datasets_and_records_after_crawl(client):
    crawl_response = client.post(
        "/crawl",
        json={
            "url": "https://example.com/gold",
            "field_descriptions": {"price": "giá vàng"},
            "dataset_name": "Giá vàng SJC",
        },
    )
    dataset_id = crawl_response.json()["dataset_id"]

    datasets_response = client.get("/datasets")
    records_response = client.get(f"/datasets/{dataset_id}/records")

    assert datasets_response.status_code == 200
    assert len(datasets_response.json()) == 1
    assert datasets_response.json()[0]["dataset_id"] == dataset_id

    assert records_response.status_code == 200
    assert len(records_response.json()) == 1
    assert records_response.json()[0]["data"] == {"price": "giá trị mẫu"}


def test_records_for_unknown_dataset_returns_404(client):
    response = client.get("/datasets/does-not-exist/records")

    assert response.status_code == 404


def test_create_schedule_returns_job_for_matching_dataset(client):
    crawl_response = client.post(
        "/crawl",
        json={
            "url": "https://example.com/gold",
            "field_descriptions": {"price": "giá vàng"},
            "dataset_name": "Giá vàng SJC",
        },
    )
    dataset_id = crawl_response.json()["dataset_id"]

    response = client.post(
        "/schedules",
        json={
            "dataset_id": dataset_id,
            "url": "https://example.com/gold",
            "field_descriptions": {"price": "giá vàng"},
            "trigger_type": "interval",
            "trigger_args": {"hours": 1},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["job_id"]
    assert body["dataset_id"] == dataset_id
    assert body["trigger_type"] == "interval"
    assert body["enabled"] is True


def test_create_schedule_for_unknown_dataset_returns_404(client):
    response = client.post(
        "/schedules",
        json={
            "dataset_id": "does-not-exist",
            "url": "https://example.com/x",
            "field_descriptions": {"price": "giá"},
            "trigger_type": "interval",
            "trigger_args": {"hours": 1},
        },
    )

    assert response.status_code == 404


def test_create_schedule_with_mismatched_schema_returns_409(client):
    crawl_response = client.post(
        "/crawl",
        json={
            "url": "https://example.com/gold",
            "field_descriptions": {"price": "giá vàng"},
            "dataset_name": "Giá vàng SJC",
        },
    )
    dataset_id = crawl_response.json()["dataset_id"]

    response = client.post(
        "/schedules",
        json={
            "dataset_id": dataset_id,
            "url": "https://example.com/gold",
            "field_descriptions": {"other_field": "khác hoàn toàn"},
            "trigger_type": "interval",
            "trigger_args": {"hours": 1},
        },
    )

    assert response.status_code == 409


def test_list_schedules_returns_created_jobs(client):
    crawl_response = client.post(
        "/crawl",
        json={
            "url": "https://example.com/gold",
            "field_descriptions": {"price": "giá vàng"},
            "dataset_name": "Giá vàng SJC",
        },
    )
    dataset_id = crawl_response.json()["dataset_id"]
    client.post(
        "/schedules",
        json={
            "dataset_id": dataset_id,
            "url": "https://example.com/gold",
            "field_descriptions": {"price": "giá vàng"},
            "trigger_type": "interval",
            "trigger_args": {"hours": 1},
        },
    )

    response = client.get("/schedules")

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_delete_schedule_removes_it(client):
    crawl_response = client.post(
        "/crawl",
        json={
            "url": "https://example.com/gold",
            "field_descriptions": {"price": "giá vàng"},
            "dataset_name": "Giá vàng SJC",
        },
    )
    dataset_id = crawl_response.json()["dataset_id"]
    create_response = client.post(
        "/schedules",
        json={
            "dataset_id": dataset_id,
            "url": "https://example.com/gold",
            "field_descriptions": {"price": "giá vàng"},
            "trigger_type": "interval",
            "trigger_args": {"hours": 1},
        },
    )
    job_id = create_response.json()["job_id"]

    delete_response = client.delete(f"/schedules/{job_id}")
    list_response = client.get("/schedules")

    assert delete_response.status_code == 200
    assert list_response.json() == []


def test_delete_unknown_schedule_returns_404(client):
    response = client.delete("/schedules/does-not-exist")

    assert response.status_code == 404


def test_scheduler_starts_and_stops_with_app_lifespan():
    """Dùng `with TestClient(app)` để kích hoạt lifespan thật (startup/shutdown)
    — xác nhận CrawlScheduler thật sự start/shutdown theo vòng đời app, không
    chỉ test qua unit test riêng của CrawlScheduler."""
    fetcher = _FakeFetcher()
    ai_client = _FakeAIClient()
    storage = SQLiteStorage(":memory:")
    app = create_app(fetcher=fetcher, ai_client=ai_client, storage=storage)

    with TestClient(app) as client:
        response = client.get("/schedules")
        assert response.status_code == 200


# ---- storage_mode="file" (lựa chọn lưu file, mục 5+6) ----------------------
@pytest.fixture
def export_file():
    """1 filename tương đối thật dưới `data/exports/` (đã gitignore) — API
    dùng đúng `exports_root` mặc định nên test ghi thật vào đây rồi tự dọn."""
    name = "api_test_export.json"
    path = EXPORTS_ROOT / name
    yield name, path
    path.unlink(missing_ok=True)


def test_crawl_file_mode_writes_file_and_returns_file_path(client, export_file):
    file_name, full_path = export_file

    response = client.post(
        "/crawl",
        json={
            "url": "https://example.com/gold",
            "field_descriptions": {"price": "giá vàng"},
            "storage_mode": "file",
            "file_path": file_name,
            "write_mode": "append",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "saved"
    assert body["file_path"] == file_name
    assert body["dataset_id"] is None
    assert body["needs_review"] is False  # confidence 0.9 >= ngưỡng mặc định 0.7
    assert full_path.exists()


def test_crawl_file_mode_does_not_create_any_dataset(client, export_file):
    file_name, _ = export_file
    client.post(
        "/crawl",
        json={
            "url": "https://example.com/gold",
            "field_descriptions": {"price": "giá vàng"},
            "storage_mode": "file",
            "file_path": file_name,
            "write_mode": "append",
        },
    )

    assert client.get("/datasets").json() == []


def test_crawl_file_mode_missing_file_path_returns_400(client):
    response = client.post(
        "/crawl",
        json={
            "url": "https://example.com/gold",
            "field_descriptions": {"price": "giá vàng"},
            "storage_mode": "file",
            "write_mode": "append",
        },
    )

    assert response.status_code == 400


def test_crawl_file_mode_invalid_file_path_returns_400(client):
    response = client.post(
        "/crawl",
        json={
            "url": "https://example.com/gold",
            "field_descriptions": {"price": "giá vàng"},
            "storage_mode": "file",
            "file_path": "../escape.json",
            "write_mode": "append",
        },
    )

    assert response.status_code == 400


def test_crawl_file_mode_overwrite_row_missing_key_field_returns_400(client):
    response = client.post(
        "/crawl",
        json={
            "url": "https://example.com/gold",
            "field_descriptions": {"price": "giá vàng"},
            "storage_mode": "file",
            "file_path": "gold.json",
            "write_mode": "overwrite_row",
        },
    )

    assert response.status_code == 400


def test_crawl_file_mode_key_field_not_in_field_descriptions_returns_400(client):
    response = client.post(
        "/crawl",
        json={
            "url": "https://example.com/gold",
            "field_descriptions": {"price": "giá vàng"},
            "storage_mode": "file",
            "file_path": "gold.json",
            "write_mode": "overwrite_row",
            "key_field": "not_declared",
        },
    )

    assert response.status_code == 400


def test_crawl_invalid_storage_mode_returns_400(client):
    response = client.post(
        "/crawl",
        json={
            "url": "https://example.com/gold",
            "field_descriptions": {"price": "giá vàng"},
            "storage_mode": "not_a_real_mode",
        },
    )

    assert response.status_code == 400


# ---- GET /exports/{path} ----------------------------------------------------
def test_download_export_returns_file_content(client, export_file):
    file_name, full_path = export_file
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(json.dumps([{"price": 1}]), encoding="utf-8")

    response = client.get(f"/exports/{file_name}")

    assert response.status_code == 200
    assert response.json() == [{"price": 1}]


def test_download_export_missing_file_returns_404(client):
    response = client.get("/exports/does-not-exist.json")

    assert response.status_code == 404


def test_download_export_path_traversal_returns_400(client):
    response = client.get("/exports/..%2F..%2Fetc%2Fpasswd")

    assert response.status_code in (400, 404)  # tuỳ cách FastAPI/starlette chuẩn hoá path


# ---- storage_mode="file" cho /schedules ------------------------------------
def test_create_schedule_file_mode_does_not_require_dataset(client):
    response = client.post(
        "/schedules",
        json={
            "url": "https://example.com/gold",
            "field_descriptions": {"price": "giá vàng"},
            "trigger_type": "interval",
            "trigger_args": {"hours": 1},
            "storage_mode": "file",
            "file_path": "scheduled_gold.json",
            "write_mode": "append",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["dataset_id"] is None
    assert body["storage_mode"] == "file"
    assert body["file_path"] == "scheduled_gold.json"


def test_create_schedule_db_mode_without_dataset_id_returns_422(client):
    response = client.post(
        "/schedules",
        json={
            "url": "https://example.com/gold",
            "field_descriptions": {"price": "giá vàng"},
            "trigger_type": "interval",
            "trigger_args": {"hours": 1},
        },
    )

    assert response.status_code == 422


def test_create_schedule_file_mode_invalid_write_mode_returns_400(client):
    response = client.post(
        "/schedules",
        json={
            "url": "https://example.com/gold",
            "field_descriptions": {"price": "giá vàng"},
            "trigger_type": "interval",
            "trigger_args": {"hours": 1},
            "storage_mode": "file",
            "file_path": "gold.json",
            "write_mode": "not_a_real_mode",
        },
    )

    assert response.status_code == 400


# ---- panel admin (/admin/errors, xem tests/api/test_admin.py cho chi tiết) --
def test_admin_errors_route_is_mounted(client):
    response = client.get("/admin/errors", auth=_ADMIN_AUTH)

    assert response.status_code == 200
    assert response.json() == {"scheduled_job_errors": [], "manual_crawl_errors": []}


def test_admin_errors_route_requires_auth(client):
    response = client.get("/admin/errors")

    assert response.status_code == 401


def test_manual_crawl_failure_is_logged_to_audit_log_for_admin_panel():
    """Lỗi "Chạy crawl" thủ công (502 fetch_failed/extract_failed) phải ghi
    vào audit_log để panel admin thấy lại được — trước đây bị bỏ sót hoàn
    toàn, chỉ scheduled_jobs mới lên /admin/errors."""
    storage = SQLiteStorage(":memory:")
    app = create_app(
        fetcher=_FakeFetcher(html=None),  # html=None -> fetch luôn fail (error="not_found")
        ai_client=_FakeAIClient(),
        storage=storage,
        admin_username=_ADMIN_AUTH[0], admin_password=_ADMIN_AUTH[1],
    )
    client = TestClient(app)

    response = client.post(
        "/crawl",
        json={
            "url": "https://batdongsan.com.vn/x",
            "field_descriptions": {"price": "giá"},
            "dataset_name": "Test",
        },
    )
    assert response.status_code == 502

    errors = client.get("/admin/errors", auth=_ADMIN_AUTH).json()
    assert len(errors["manual_crawl_errors"]) == 1
    assert errors["manual_crawl_errors"][0]["detail"]["url"] == "https://batdongsan.com.vn/x"
    assert errors["manual_crawl_errors"][0]["detail"]["error"] == "not_found"


def test_ignore_robots_requires_reason_and_uses_overridden_fetcher(caplog):
    class _Fetcher(_FakeFetcher):
        def __init__(self):
            super().__init__()
            self.ignored = None

        def with_robots_ignored(self, domain, reason):
            clone = _Fetcher()
            clone.ignored = (domain, reason)
            _Fetcher.last = clone
            return clone

    app = create_app(fetcher=_Fetcher(), ai_client=_FakeAIClient(), storage=SQLiteStorage(":memory:"))
    client = TestClient(app)
    body = {"url": "https://example.com/p", "field_descriptions": {"a": "b"}, "dataset_name": "D",
            "ignore_robots": True}

    assert client.post("/crawl", json=body).status_code == 400

    with caplog.at_level("WARNING"):
        resp = client.post("/crawl", json={**body, "ignore_robots_reason": "Tôi là chủ website"})
    assert resp.status_code == 200
    assert _Fetcher.last.ignored == ("example.com", "Tôi là chủ website")
    assert "BỎ QUA robots.txt" in caplog.text
