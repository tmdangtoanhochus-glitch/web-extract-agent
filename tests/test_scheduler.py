"""Test CrawlScheduler bằng APScheduler THẬT (BackgroundScheduler) chạy
interval rất ngắn — verify wiring thật sự chạy được `run_crawl_job()`, không
chỉ mock lệnh gọi (CLAUDE.md mục 6 vẫn dùng test double cho fetch/AI, nhưng
bản thân scheduler engine test thật để bắt lỗi wiring)."""
import json
import time

import pytest
from apscheduler.schedulers.background import BackgroundScheduler

from src.ai.base import AIClient, ExtractionResult, FieldExtraction
from src.fetch.base import FetchEngine, FetchResult, utcnow
from src.scheduler import CrawlScheduler
from src.storage.sqlite_storage import SQLiteStorage


class _FakeFetcher(FetchEngine):
    def __init__(self, html: str = "<html><body><p>giá 75.000.000</p></body></html>"):
        self._html = html
        self.calls = 0

    def fetch(self, url: str) -> FetchResult:
        self.calls += 1
        return FetchResult(
            url=url, final_url=url, status_code=200, html=self._html,
            fetched_at=utcnow(), success=True,
        )


class _FakeAIClient(AIClient):
    def __init__(self):
        self.calls = 0

    def extract(self, markdown: str, field_descriptions: dict[str, str], parallel: bool = False, on_progress=None) -> ExtractionResult:
        self.calls += 1
        return ExtractionResult(
            records=[{name: FieldExtraction(value="v", confidence=0.9, evidence="e") for name in field_descriptions}],
            success=True,
        )


class _RaisingAIClient(AIClient):
    def extract(self, markdown: str, field_descriptions: dict[str, str], parallel: bool = False, on_progress=None) -> ExtractionResult:
        raise RuntimeError("boom - lỗi không mong đợi")


def _wait_until(predicate, timeout: float = 3.0, interval: float = 0.05) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


@pytest.fixture
def storage():
    store = SQLiteStorage(":memory:")
    yield store
    store.close()


def _make_scheduler(fetcher, ai_client, storage, confidence_threshold: float = 0.7) -> CrawlScheduler:
    return CrawlScheduler(
        fetcher=fetcher, ai_client=ai_client, storage=storage, scheduler=BackgroundScheduler(),
        confidence_threshold=confidence_threshold,
    )


def test_add_job_persists_job_in_storage(storage):
    dataset = storage.create_dataset("Giá vàng", ["price"])
    fetcher, ai_client = _FakeFetcher(), _FakeAIClient()
    scheduler = _make_scheduler(fetcher, ai_client, storage)

    job = scheduler.add_job(
        dataset_id=dataset.dataset_id,
        url="https://example.com/gold",
        field_descriptions={"price": "giá bán"},
        trigger_type="interval",
        trigger_args={"seconds": 3600},
    )

    assert storage.get_scheduled_job(job.job_id) is not None
    scheduler.shutdown()


def test_job_actually_executes_on_schedule_and_saves_record(storage):
    dataset = storage.create_dataset("Giá vàng", ["price"])
    fetcher, ai_client = _FakeFetcher(), _FakeAIClient()
    scheduler = _make_scheduler(fetcher, ai_client, storage)
    scheduler.start()

    job = scheduler.add_job(
        dataset_id=dataset.dataset_id,
        url="https://example.com/gold",
        field_descriptions={"price": "giá bán"},
        trigger_type="interval",
        trigger_args={"seconds": 0.2},
    )

    try:
        assert _wait_until(lambda: ai_client.calls >= 1, timeout=6.0)
        assert _wait_until(
            lambda: storage.get_scheduled_job(job.job_id).last_status == "saved", timeout=6.0
        )
        records = storage.list_records(dataset.dataset_id)
        assert len(records) >= 1
    finally:
        scheduler.shutdown()


def test_job_applies_confidence_threshold_to_flag_needs_review(storage):
    """`CrawlScheduler` phải truyền confidence_threshold xuống pipeline —
    record của job lịch cũng được gắn needs_review đúng như crawl thủ công."""
    dataset = storage.create_dataset("Giá vàng", ["price"])
    fetcher, ai_client = _FakeFetcher(), _FakeAIClient()  # AI trả confidence cố định 0.9
    scheduler = _make_scheduler(fetcher, ai_client, storage, confidence_threshold=0.95)
    scheduler.start()

    job = scheduler.add_job(
        dataset_id=dataset.dataset_id,
        url="https://example.com/gold",
        field_descriptions={"price": "giá bán"},
        trigger_type="interval",
        trigger_args={"seconds": 0.2},
    )

    try:
        assert _wait_until(
            lambda: storage.get_scheduled_job(job.job_id).last_status == "saved", timeout=6.0
        )
        records = storage.list_records(dataset.dataset_id)
        assert len(records) >= 1
        assert records[0].needs_review is True  # 0.9 < 0.95
    finally:
        scheduler.shutdown()


def test_remove_job_deletes_from_storage_and_stops_future_runs(storage):
    dataset = storage.create_dataset("Giá vàng", ["price"])
    fetcher, ai_client = _FakeFetcher(), _FakeAIClient()
    scheduler = _make_scheduler(fetcher, ai_client, storage)
    scheduler.start()

    job = scheduler.add_job(
        dataset_id=dataset.dataset_id,
        url="https://example.com/gold",
        field_descriptions={"price": "giá bán"},
        trigger_type="interval",
        trigger_args={"seconds": 0.2},
    )
    assert _wait_until(lambda: ai_client.calls >= 1, timeout=6.0)

    scheduler.remove_job(job.job_id)
    calls_at_removal = ai_client.calls
    time.sleep(0.5)

    assert storage.get_scheduled_job(job.job_id) is None
    assert ai_client.calls == calls_at_removal  # không còn chạy thêm sau khi remove
    scheduler.shutdown()


def test_run_job_logs_error_status_without_crashing_when_ai_client_raises(storage):
    dataset = storage.create_dataset("Giá vàng", ["price"])
    fetcher = _FakeFetcher()
    scheduler = _make_scheduler(fetcher, _RaisingAIClient(), storage)
    scheduler.start()

    job = scheduler.add_job(
        dataset_id=dataset.dataset_id,
        url="https://example.com/gold",
        field_descriptions={"price": "giá bán"},
        trigger_type="interval",
        trigger_args={"seconds": 0.2},
    )

    try:
        assert _wait_until(
            lambda: (storage.get_scheduled_job(job.job_id).last_status == "error"), timeout=6.0
        )
    finally:
        scheduler.shutdown()


def test_run_job_skips_gracefully_when_job_already_deleted(storage):
    dataset = storage.create_dataset("Giá vàng", ["price"])
    fetcher, ai_client = _FakeFetcher(), _FakeAIClient()
    scheduler = _make_scheduler(fetcher, ai_client, storage)

    job = storage.create_scheduled_job(
        dataset.dataset_id, "https://example.com/gold", {"price": "giá bán"}, "interval", {"hours": 1}
    )
    storage.delete_scheduled_job(job.job_id)

    scheduler._run_job(job.job_id)  # không raise dù job đã bị xoá khỏi storage

    assert ai_client.calls == 0


def test_file_mode_job_executes_and_writes_file_without_creating_dataset(storage):
    """Job storage_mode="file" không cần dataset_id — thực thi qua
    run_file_crawl_job(), không phải run_crawl_job(). `CrawlScheduler` gọi
    `run_file_crawl_job()` với `exports_root` mặc định (`data/exports/`,
    xem `src/storage/file_writer.py`) nên test này dùng đúng path tương đối
    thật dưới thư mục đó (đã gitignore) rồi tự dọn lại sau khi test xong."""
    from src.storage.file_writer import EXPORTS_ROOT

    file_path = "scheduler_test_gold.json"
    full_path = EXPORTS_ROOT / file_path

    fetcher, ai_client = _FakeFetcher(), _FakeAIClient()
    scheduler = _make_scheduler(fetcher, ai_client, storage)
    scheduler.start()

    job = scheduler.add_job(
        dataset_id=None,
        url="https://example.com/gold",
        field_descriptions={"price": "giá bán"},
        trigger_type="interval",
        trigger_args={"seconds": 0.2},
        storage_mode="file",
        file_path=file_path,
        write_mode="append",
    )

    try:
        assert _wait_until(lambda: ai_client.calls >= 1, timeout=6.0)
        assert _wait_until(
            lambda: storage.get_scheduled_job(job.job_id).last_status == "saved", timeout=6.0
        )
        assert storage.list_datasets() == []  # luồng file KHÔNG tạo dataset
        assert full_path.exists()
        written = json.loads(full_path.read_text(encoding="utf-8"))
        assert len(written) >= 1
    finally:
        scheduler.shutdown()
        full_path.unlink(missing_ok=True)


def test_run_job_records_traceback_on_unexpected_error(storage):
    dataset = storage.create_dataset("Giá vàng", ["price"])
    fetcher = _FakeFetcher()
    scheduler = _make_scheduler(fetcher, _RaisingAIClient(), storage)
    scheduler.start()

    job = scheduler.add_job(
        dataset_id=dataset.dataset_id,
        url="https://example.com/gold",
        field_descriptions={"price": "giá bán"},
        trigger_type="interval",
        trigger_args={"seconds": 0.2},
    )

    try:
        assert _wait_until(
            lambda: (storage.get_scheduled_job(job.job_id).last_error_traceback is not None), timeout=6.0
        )
        traceback_text = storage.get_scheduled_job(job.job_id).last_error_traceback
        assert "RuntimeError" in traceback_text
        assert "boom - lỗi không mong đợi" in traceback_text
    finally:
        scheduler.shutdown()


def test_run_job_clears_traceback_on_next_successful_run(storage):
    """1 job trước đó lỗi (có traceback lưu lại), sau khi sửa để chạy thành
    công thì traceback cũ không còn được hiển thị như lỗi hiện tại."""
    dataset = storage.create_dataset("Giá vàng", ["price"])
    job = storage.create_scheduled_job(
        dataset.dataset_id, "https://example.com/gold", {"price": "giá bán"}, "interval", {"hours": 1}
    )
    storage.update_scheduled_job_run(job.job_id, status="error", traceback_text="lỗi cũ")

    fetcher, ai_client = _FakeFetcher(), _FakeAIClient()
    scheduler = _make_scheduler(fetcher, ai_client, storage)
    scheduler._run_job(job.job_id)

    updated = storage.get_scheduled_job(job.job_id)
    assert updated.last_status == "saved"
    assert updated.last_error_traceback is None


def test_start_reloads_persisted_enabled_jobs_after_restart(storage):
    """Mô phỏng restart app: 1 CrawlScheduler khác (process mới, storage cũ)
    gọi start() phải tự đăng ký lại job đã lưu, không cần add_job() lại."""
    dataset = storage.create_dataset("Giá vàng", ["price"])
    storage.create_scheduled_job(
        dataset.dataset_id, "https://example.com/gold", {"price": "giá bán"}, "interval", {"hours": 1}
    )

    fetcher, ai_client = _FakeFetcher(), _FakeAIClient()
    restarted_scheduler = _make_scheduler(fetcher, ai_client, storage)
    restarted_scheduler.start()

    try:
        jobs = storage.list_scheduled_jobs()
        assert restarted_scheduler._scheduler.get_job(jobs[0].job_id) is not None
    finally:
        restarted_scheduler.shutdown()
