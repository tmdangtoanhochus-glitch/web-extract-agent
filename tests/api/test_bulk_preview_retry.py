import json
import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.bulk_crawl import CrawlOptions, run_bulk
from src.fetch.base import FetchResult, utcnow
from src.scheduler import CrawlScheduler
from src.storage.sqlite_storage import SQLiteStorage


class Fetcher:
    def __init__(self, fail_second=False):
        self.calls = []
        self.fail_second = fail_second
        self.html = None

    def fetch(self, url):
        self.calls.append(url)
        page = "2" if "page=2" in url else "1"
        success = not (page == "2" and self.fail_second)
        html = self.html or f"<table><tr><th>id</th></tr><tr><td>{page}</td></tr></table>"
        return FetchResult(url=url, final_url=url, status_code=200 if success else 503,
                           html=html if success else None, success=success, fetched_at=utcnow())


@pytest.fixture
def setup():
    storage = SQLiteStorage(":memory:")
    fetcher = Fetcher()
    client = TestClient(create_app(fetcher, None, storage, admin_username="test", admin_password="synthetic"))
    body = {"url": "https://example.test/?page={page}", "dataset_name": "History",
            "field_descriptions": {"id": "Identifier"},
            "crawl_options": {"mode": "table", "pages": 2, "columns": {"id": 1}}}
    return storage, fetcher, client, body


def test_preview_reads_first_page_without_dataset_cache_or_data_in_audit(setup):
    storage, fetcher, client, body = setup
    fetcher.html = "<table>" + "".join(f"<tr><td>synthetic-row-{i}</td></tr>" for i in range(15)) + "</table>"
    response = client.post("/crawl/preview", json=body)
    assert response.status_code == 200
    result = response.json()
    assert result["requests"] == 2 and result["matched_rows"] == 15 and len(result["sample"]) == 10
    assert fetcher.calls == ["https://example.test/?page=1"]
    assert storage.list_datasets() == []
    assert storage.get_extraction_strategy("example.test", "id") is None
    assert "synthetic-row" not in str([entry.detail for entry in storage.list_audit_log()])
    assert client.post("/crawl-reports", json={"request_id": result["request_id"], "ui_step": 3}).status_code == 201


def test_fields_preview_never_fetches_and_oversized_plan_rejected(setup):
    storage, fetcher, client, body = setup
    body["crawl_options"] = {"mode": "fields", "pages": 2}
    assert client.post("/crawl/preview", json=body).json()["fetched_pages"] == 0
    body["url"] += "&from={start}&to={end}"
    body["crawl_options"].update(start_date="2026-01-01", end_date="2026-12-31")
    assert client.post("/crawl/preview", json=body).status_code == 400
    assert fetcher.calls == [] and storage.list_datasets() == []


def test_retry_only_failed_indices_same_dataset_and_no_duplicate_records(setup):
    storage, fetcher, client, body = setup
    fetcher.fail_second = True
    initial = client.post("/crawl", json=body).json()
    assert initial["failed"] == 1 and initial["saved"] == 1
    fetcher.fail_second = False
    fetcher.calls.clear()
    retry = {**body, "dataset_id": initial["dataset_id"], "retry_of": initial["request_id"]}
    response = client.post("/crawl", json=retry)
    assert response.status_code == 200
    result = response.json()
    assert result["requests"] == 1 and result["results"] == [{"index": 2, "status": "saved"}]
    assert fetcher.calls == ["https://example.test/?page=2"]
    assert len(storage.list_records(initial["dataset_id"])) == 2
    assert client.post("/crawl", json=retry).json()["skipped"] == 1
    retry["retry_of"] = result["request_id"]
    assert client.post("/crawl", json=retry).status_code == 409


def test_retry_rejects_changed_config_or_dataset_before_fetch(setup):
    storage, fetcher, client, body = setup
    fetcher.fail_second = True
    result = client.post("/crawl", json=body).json()
    retry = {**body, "dataset_id": result["dataset_id"], "retry_of": result["request_id"]}
    fetcher.calls.clear()
    assert client.post("/crawl", json={**retry, "url": "https://other.test/?page={page}"}).status_code == 409
    assert client.post("/crawl", json={**retry, "dataset_id": "other"}).status_code == 409
    assert client.post("/crawl", json={**retry, "field_descriptions": {"id": "changed"}}).status_code == 409
    assert client.post("/crawl/preview", json=retry).status_code == 400
    assert fetcher.calls == []


def test_file_and_field_retry_rejected_without_fetch(setup):
    _, fetcher, client, body = setup
    body["retry_of"] = "00000000-0000-0000-0000-000000000001"
    body["storage_mode"] = "file"
    assert client.post("/crawl", json=body).status_code == 400
    body["storage_mode"] = "db"
    body["crawl_options"] = {"mode": "fields"}
    assert client.post("/crawl", json=body).status_code == 400
    assert fetcher.calls == []


def test_invalid_date_safe_diagnostic_preview_and_run(setup):
    storage, fetcher, client, body = setup
    fetcher.html = "<table><tr><td>synthetic-private-cell</td></tr></table>"
    body["crawl_options"]["date_field"] = "id"
    preview = client.post("/crawl/preview", json=body)
    assert preview.status_code == 400 and "synthetic-private-cell" not in preview.text
    result = client.post("/crawl", json=body).json()
    assert result["results"][0]["error_code"] == "date_format"
    assert "synthetic-private-cell" not in json.dumps(result)
    assert storage.list_records(result["dataset_id"]) == []


def test_partial_schedule_visible_in_admin_with_per_page_errors(setup):
    storage, fetcher, client, body = setup
    fetcher.fail_second = True
    dataset = storage.create_dataset("History", ["id"])
    scheduler = CrawlScheduler(fetcher, None, storage)
    job = scheduler.add_job(dataset.dataset_id, body["url"], body["field_descriptions"],
                            "interval", {"hours": 1}, crawl_options=body["crawl_options"])
    scheduler._run_job(job.job_id)
    response = client.get("/admin/errors", auth=("test", "synthetic"))
    listed = response.json()["scheduled_job_errors"][0]
    assert listed["last_status"] == "partial"
    assert listed["bulk_results"][1]["error_code"] == "fetch_failed"


def test_retry_rejects_moving_date_windows(setup):
    storage, fetcher, _, body = setup
    dataset = storage.create_dataset("History", ["id"])
    with pytest.raises(ValueError):
        run_bulk(url="https://example.test/{start}", field_descriptions={"id": "Identifier"},
                 options=CrawlOptions(mode="table", columns={"id": 1}, lookback_days=1),
                 fetcher=fetcher, ai_client=None, storage=storage, dataset_id=dataset.dataset_id, retry_indices=[1])
    assert fetcher.calls == []
