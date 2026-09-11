"""Test luồng orchestration run_crawl_job bằng test double cho fetch/AI
(CLAUDE.md mục 6) + SQLiteStorage in-memory thật (không cần mock)."""
import pytest

from src.ai.base import AIClient, ExtractionResult, FieldExtraction
from src.fetch.base import FetchEngine, FetchResult, utcnow
from src.pipeline import run_crawl_job
from src.storage.sqlite_storage import SQLiteStorage


class _FakeFetcher(FetchEngine):
    """Trả về html cố định cho 1 hoặc nhiều url, không gọi mạng thật."""

    def __init__(self, html_by_url: dict[str, str] | None = None, default_html: str | None = None):
        self._html_by_url = html_by_url or {}
        self._default_html = default_html
        self.calls: list[str] = []

    def fetch(self, url: str) -> FetchResult:
        self.calls.append(url)
        html = self._html_by_url.get(url, self._default_html)
        if html is None:
            return FetchResult(
                url=url, final_url=url, status_code=404, html=None,
                fetched_at=utcnow(), success=False, error="not_found",
            )
        return FetchResult(
            url=url, final_url=url, status_code=200, html=html,
            fetched_at=utcnow(), success=True,
        )


class _FakeAIClient(AIClient):
    """Trả về 1 ExtractionResult cố định (hoặc theo hàng đợi) cho mỗi lần gọi."""

    def __init__(self, results: list[ExtractionResult]):
        self._results = list(results)
        self.calls = 0

    def extract(self, markdown: str, field_descriptions: dict[str, str]) -> ExtractionResult:
        self.calls += 1
        return self._results.pop(0)


def _extraction(price_value=75000000, price_conf=0.9, date_value="2026-09-11", date_conf=0.8):
    return ExtractionResult(
        fields={
            "price": FieldExtraction(value=price_value, confidence=price_conf, evidence="giá x"),
            "date": FieldExtraction(value=date_value, confidence=date_conf, evidence="ngày y"),
        },
        raw_response="{}",
        success=True,
    )


def _storage():
    return SQLiteStorage(":memory:")


def test_saves_new_record_and_creates_dataset():
    fetcher = _FakeFetcher(default_html="<html><body><p>giá 75.000.000</p></body></html>")
    ai_client = _FakeAIClient([_extraction()])
    storage = _storage()

    result = run_crawl_job(
        url="https://example.com/gold",
        field_descriptions={"price": "giá vàng", "date": "ngày cập nhật"},
        dataset_name="Giá vàng SJC",
        fetcher=fetcher,
        ai_client=ai_client,
        storage=storage,
    )

    assert result.status == "saved"
    assert result.dataset.dataset_name == "Giá vàng SJC"
    assert result.record.data == {"price": 75000000, "date": "2026-09-11"}
    assert result.record.confidence == pytest.approx(0.85)  # avg(0.9, 0.8)
    assert result.record.evidence == {"price": "giá x", "date": "ngày y"}

    sources = storage.list_sources(result.dataset.dataset_id, active_only=True)
    assert len(sources) == 1
    assert sources[0].source_url == "https://example.com/gold"


def test_second_crawl_same_content_returns_unchanged_without_calling_ai_again():
    fetcher = _FakeFetcher(default_html="<html><body><p>giá 75.000.000</p></body></html>")
    ai_client = _FakeAIClient([_extraction()])
    storage = _storage()

    first = run_crawl_job(
        url="https://example.com/gold",
        field_descriptions={"price": "giá vàng", "date": "ngày cập nhật"},
        dataset_name="Giá vàng SJC",
        fetcher=fetcher,
        ai_client=ai_client,
        storage=storage,
    )
    # Re-crawl cùng URL, trỏ về đúng dataset vừa tạo (dataset_id tường minh).
    second = run_crawl_job(
        url="https://example.com/gold",
        field_descriptions={"price": "giá vàng", "date": "ngày cập nhật"},
        dataset_id=first.dataset.dataset_id,
        fetcher=fetcher,
        ai_client=ai_client,
        storage=storage,
    )

    assert first.status == "saved"
    assert second.status == "unchanged"
    assert second.record.record_id == first.record.record_id
    assert ai_client.calls == 1  # không gọi AI lại vì content_hash không đổi
    assert len(storage.list_records(first.dataset.dataset_id)) == 1


def test_second_crawl_changed_content_saves_new_record():
    url = "https://example.com/gold"
    fetcher = _FakeFetcher(
        html_by_url={url: "<html><body><p>giá 75.000.000</p></body></html>"}
    )
    ai_client = _FakeAIClient([_extraction(price_value=75000000), _extraction(price_value=80000000)])
    storage = _storage()
    field_descriptions = {"price": "giá vàng", "date": "ngày cập nhật"}

    first = run_crawl_job(
        url=url,
        field_descriptions=field_descriptions,
        dataset_name="Giá vàng SJC",
        fetcher=fetcher,
        ai_client=ai_client,
        storage=storage,
    )
    fetcher._html_by_url[url] = "<html><body><p>giá 80.000.000</p></body></html>"
    second = run_crawl_job(
        url=url,
        field_descriptions=field_descriptions,
        dataset_id=first.dataset.dataset_id,
        fetcher=fetcher,
        ai_client=ai_client,
        storage=storage,
    )

    assert first.status == "saved"
    assert second.status == "saved"
    assert second.record.record_id != first.record.record_id
    assert second.record.data["price"] == 80000000
    assert ai_client.calls == 2
    assert len(storage.list_records(first.dataset.dataset_id)) == 2


def test_fetch_failure_returns_fetch_failed_and_does_not_call_ai():
    fetcher = _FakeFetcher()  # không có html cho url nào -> 404
    ai_client = _FakeAIClient([_extraction()])
    storage = _storage()

    result = run_crawl_job(
        url="https://example.com/missing",
        field_descriptions={"price": "giá"},
        dataset_name="X",
        fetcher=fetcher,
        ai_client=ai_client,
        storage=storage,
    )

    assert result.status == "fetch_failed"
    assert result.detail == "not_found"
    assert ai_client.calls == 0
    # Dataset vẫn được tạo (schema đã xác định từ field_descriptions của
    # caller, không phụ thuộc kết quả fetch) — chỉ chưa có record nào.
    assert result.dataset is not None
    assert storage.list_records(result.dataset.dataset_id) == []


def test_extract_failure_returns_extract_failed_but_dataset_and_source_already_created():
    fetcher = _FakeFetcher(default_html="<html><body><p>abc</p></body></html>")
    ai_client = _FakeAIClient([ExtractionResult(success=False, error="ai_timeout")])
    storage = _storage()

    result = run_crawl_job(
        url="https://example.com/x",
        field_descriptions={"price": "giá"},
        dataset_name="X",
        fetcher=fetcher,
        ai_client=ai_client,
        storage=storage,
    )

    assert result.status == "extract_failed"
    assert result.detail == "ai_timeout"
    assert result.dataset is not None
    assert storage.list_records(result.dataset.dataset_id) == []


def test_new_url_with_matching_schema_does_not_auto_merge_into_existing_dataset():
    """CLAUDE.md mục 4: KHÔNG tự động gộp chỉ vì field giống nhau — URL mới
    luôn tạo dataset riêng trừ khi caller truyền dataset_id tường minh."""
    fetcher = _FakeFetcher(default_html="<html><body><p>abc</p></body></html>")
    ai_client = _FakeAIClient([_extraction(), _extraction()])
    storage = _storage()
    field_descriptions = {"price": "giá vàng", "date": "ngày cập nhật"}

    first = run_crawl_job(
        url="https://a.example.com/gold",
        field_descriptions=field_descriptions,
        dataset_name="Giá vàng",
        fetcher=fetcher,
        ai_client=ai_client,
        storage=storage,
    )
    second = run_crawl_job(
        url="https://b.example.com/gold",
        field_descriptions=field_descriptions,
        dataset_name="Giá vàng (nguồn khác, không liên quan)",
        fetcher=fetcher,
        ai_client=ai_client,
        storage=storage,
    )

    assert first.dataset.dataset_id != second.dataset.dataset_id


def test_explicit_dataset_id_adds_url_as_source_of_that_dataset():
    fetcher = _FakeFetcher(default_html="<html><body><p>abc</p></body></html>")
    ai_client = _FakeAIClient([_extraction(), _extraction()])
    storage = _storage()
    field_descriptions = {"price": "giá vàng", "date": "ngày cập nhật"}

    first = run_crawl_job(
        url="https://a.example.com/gold",
        field_descriptions=field_descriptions,
        dataset_name="Giá vàng",
        fetcher=fetcher,
        ai_client=ai_client,
        storage=storage,
    )
    second = run_crawl_job(
        url="https://b.example.com/gold",
        field_descriptions=field_descriptions,
        dataset_id=first.dataset.dataset_id,
        fetcher=fetcher,
        ai_client=ai_client,
        storage=storage,
    )

    assert second.status == "saved"
    assert second.dataset.dataset_id == first.dataset.dataset_id
    sources = storage.list_sources(first.dataset.dataset_id, active_only=True)
    assert {s.source_url for s in sources} == {
        "https://a.example.com/gold",
        "https://b.example.com/gold",
    }


def test_unknown_dataset_id_returns_dataset_not_found():
    fetcher = _FakeFetcher(default_html="<html><body><p>abc</p></body></html>")
    ai_client = _FakeAIClient([_extraction()])
    storage = _storage()

    result = run_crawl_job(
        url="https://example.com/x",
        field_descriptions={"price": "giá"},
        dataset_id="does-not-exist",
        fetcher=fetcher,
        ai_client=ai_client,
        storage=storage,
    )

    assert result.status == "dataset_not_found"
    assert ai_client.calls == 0
    assert fetcher.calls == []


def test_dataset_id_with_mismatched_schema_returns_schema_mismatch():
    fetcher = _FakeFetcher(default_html="<html><body><p>abc</p></body></html>")
    ai_client = _FakeAIClient([_extraction()])
    storage = _storage()

    created = run_crawl_job(
        url="https://a.example.com/gold",
        field_descriptions={"price": "giá vàng", "date": "ngày cập nhật"},
        dataset_name="Giá vàng",
        fetcher=fetcher,
        ai_client=ai_client,
        storage=storage,
    )

    result = run_crawl_job(
        url="https://b.example.com/other",
        field_descriptions={"name": "tên", "quantity": "số lượng"},
        dataset_id=created.dataset.dataset_id,
        fetcher=fetcher,
        ai_client=ai_client,
        storage=storage,
    )

    assert result.status == "schema_mismatch"
    assert ai_client.calls == 1  # chỉ gọi lần crawl đầu, lần 2 bị chặn trước khi fetch/extract
