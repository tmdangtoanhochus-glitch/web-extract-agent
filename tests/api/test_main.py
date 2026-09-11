"""Test API bằng FastAPI TestClient + test double cho fetch/AI, storage
in-memory thật — không gọi mạng/AI/endpoint thật (CLAUDE.md mục 6)."""
import httpx
import pytest
from fastapi.testclient import TestClient

from src.ai.base import AIClient, ExtractionResult, FieldExtraction
from src.api.main import create_app
from src.fetch.base import FetchEngine, FetchResult, utcnow
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
            fields={
                name: FieldExtraction(value="giá trị mẫu", confidence=0.9, evidence="bằng chứng")
                for name in field_descriptions
            },
            raw_response="{}",
            success=True,
        )


@pytest.fixture
def client():
    fetcher = _FakeFetcher()
    ai_client = _FakeAIClient()
    storage = SQLiteStorage(":memory:")
    app = create_app(fetcher=fetcher, ai_client=ai_client, storage=storage)
    return TestClient(app)


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
