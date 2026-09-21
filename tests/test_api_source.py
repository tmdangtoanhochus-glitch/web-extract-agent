"""Nguồn dữ liệu là API JSON: ghép field với khóa JSON bằng code, không gọi AI."""
import json

import pytest
from fastapi.testclient import TestClient

from src.ai.base import AIClient, ExtractionResult
from src.api.main import create_app
from src.api_source import ApiSourceError, assert_public_url, extract_api_records, find_records, map_fields
from src.fetch.base import FetchEngine, FetchResult, utcnow
from src.pipeline import run_crawl_job
from src.storage.sqlite_storage import SQLiteStorage

BODY = json.dumps({"status": "ok", "data": {"items": [
    {"Tên xe": "Mazda 3", "gia": 500, "seller": {"name": "An"}, "tags": ["a", "b"]},
    {"Tên xe": "Kia K3", "gia": 450, "seller": {"name": "Bình"}, "tags": []}]}}, ensure_ascii=False)


class _Fetcher(FetchEngine):
    def __init__(self, body):
        self.body, self.calls = body, []

    def fetch(self, url):
        self.calls.append(url)
        return FetchResult(url=url, final_url=url, status_code=200, html=self.body, fetched_at=utcnow(), success=True)


class _NoAI(AIClient):
    def __init__(self):
        self.calls = 0

    def extract(self, markdown, field_descriptions, parallel=False, on_progress=None):
        self.calls += 1
        return ExtractionResult(success=False, error="AI không được gọi ở nguồn API")


def test_finds_largest_object_array_and_maps_fields_ignoring_case_and_accents():
    rows = find_records(json.loads(BODY))
    assert len(rows) == 2
    records = extract_api_records(BODY, {"ten_xe": "tên xe", "GIA": "giá", "ten_nguoi_ban": "name"})
    assert [r["ten_xe"].value for r in records] == ["Mazda 3", "Kia K3"]
    assert [r["GIA"].value for r in records] == [500, 450]
    assert records[0]["ten_nguoi_ban"].value == "An"  # khóa lồng nhau seller.name khớp phần cuối `name`
    assert records[0]["GIA"].confidence == 1.0 and records[0]["GIA"].evidence == "api:gia"


def test_nested_list_value_is_stored_as_json_text():
    records = extract_api_records(BODY, {"tags": "tags"})
    assert records[0]["tags"].value == '["a", "b"]'


def test_unmapped_field_error_lists_available_keys():
    with pytest.raises(ApiSourceError) as info:
        extract_api_records(BODY, {"mau_son": "màu sơn"})
    assert "mau_son" in str(info.value) and "gia" in str(info.value)


def test_field_can_be_mapped_through_its_description():
    assert map_fields(["price_vnd", "title"], {"gia": "price_vnd"}) == {"gia": "price_vnd"}


def test_ambiguous_tail_key_is_not_guessed():
    assert map_fields(["a.name", "b.name"], {"name": ""}) == {}


def test_non_json_and_oversized_bodies_are_rejected_with_clear_message():
    with pytest.raises(ApiSourceError, match="không phải JSON"):
        extract_api_records("<html>trang thường</html>", {"x": "x"})
    with pytest.raises(ApiSourceError, match="quá lớn"):
        extract_api_records("[" + "1," * 6_000_000 + "1]", {"x": "x"})


@pytest.mark.parametrize("url", ["http://localhost/api", "http://127.0.0.1/x", "http://10.0.0.5/x",
                                 "http://169.254.169.254/latest", "http://db.internal/x", "http://[::1]/x"])
def test_internal_addresses_are_blocked(url):
    with pytest.raises(ApiSourceError):
        assert_public_url(url)


def test_public_address_is_allowed():
    assert_public_url("https://api.example.com/v1/items")


def test_pipeline_saves_api_records_without_calling_ai_and_detects_unchanged():
    storage, ai, fetcher = SQLiteStorage(":memory:"), _NoAI(), _Fetcher(BODY)
    args = dict(url="https://api.example.com/items", field_descriptions={"ten_xe": "tên xe", "gia": "giá"},
                fetcher=fetcher, ai_client=ai, storage=storage, dataset_name="xe", api_source=True)
    first = run_crawl_job(**args)
    assert first.status == "saved" and first.record_count == 2 and ai.calls == 0
    second = run_crawl_job(**{**args, "dataset_id": first.dataset.dataset_id, "dataset_name": None})
    assert second.status == "unchanged"
    changed = _Fetcher(BODY.replace("450", "460"))
    third = run_crawl_job(**{**args, "fetcher": changed, "dataset_id": first.dataset.dataset_id, "dataset_name": None})
    assert third.status == "saved" and ai.calls == 0


def test_pipeline_reports_mapping_error_as_extract_failed():
    result = run_crawl_job(url="https://api.example.com/items", field_descriptions={"khong_co": "không có"},
                           fetcher=_Fetcher(BODY), ai_client=_NoAI(), storage=SQLiteStorage(":memory:"),
                           dataset_name="xe", api_source=True)
    assert result.status == "extract_failed" and "khong_co" in result.detail


def test_api_endpoint_crawls_json_and_blocks_internal_urls():
    ai = _NoAI()
    app = create_app(fetcher=_Fetcher(BODY), ai_client=ai, storage=SQLiteStorage(":memory:"),
                     admin_username="a", admin_password="b")
    client = TestClient(app)
    ok = client.post("/crawl", json={"url": "https://api.example.com/items", "api_source": True,
                                     "field_descriptions": {"ten_xe": "tên xe", "gia": "giá"}, "dataset_name": "xe"})
    assert ok.status_code == 200 and ok.json()["record_count"] == 2 and ai.calls == 0
    blocked = client.post("/crawl", json={"url": "http://127.0.0.1:8000/x", "api_source": True,
                                          "field_descriptions": {"gia": "giá"}, "dataset_name": "xe2"})
    assert blocked.status_code == 400
