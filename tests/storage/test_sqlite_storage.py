"""Test SQLiteStorage bằng DB SQLite in-memory — nhanh, không đụng file thật."""
import pytest

from src.storage.sqlite_storage import SQLiteStorage


@pytest.fixture
def storage():
    store = SQLiteStorage(":memory:")
    yield store
    store.close()


def test_create_dataset_returns_dataset_with_id(storage):
    dataset = storage.create_dataset("Giá vàng SJC", ["date", "price"])

    assert dataset.dataset_id
    assert dataset.dataset_name == "Giá vàng SJC"
    assert dataset.schema_signature == ["date", "price"]
    assert storage.get_dataset(dataset.dataset_id) == dataset


def test_find_dataset_by_schema_matches_regardless_of_field_order(storage):
    created = storage.create_dataset("Giá vàng SJC", ["date", "price", "unit"])

    found = storage.find_dataset_by_schema(["unit", "price", "date"])

    assert found is not None
    assert found.dataset_id == created.dataset_id


def test_find_dataset_by_schema_returns_none_when_no_match(storage):
    storage.create_dataset("Giá vàng SJC", ["date", "price"])

    found = storage.find_dataset_by_schema(["completely", "different", "fields"])

    assert found is None


def test_list_datasets_returns_all_created(storage):
    storage.create_dataset("A", ["x"])
    storage.create_dataset("B", ["y"])

    datasets = storage.list_datasets()

    assert {d.dataset_name for d in datasets} == {"A", "B"}


def test_add_source_first_call_is_active(storage):
    dataset = storage.create_dataset("A", ["x"])

    source = storage.add_source(dataset.dataset_id, "https://example.com/a")

    assert source.active is True
    sources = storage.list_sources(dataset.dataset_id)
    assert len(sources) == 1
    assert sources[0].source_url == "https://example.com/a"


def test_add_source_does_not_deactivate_other_active_sources(storage):
    """1 dataset có thể có nhiều nguồn active cùng lúc (vd. nhiều URL cùng
    schema) — add_source() chỉ thêm, không đụng tới nguồn active khác."""
    dataset = storage.create_dataset("A", ["x"])
    storage.add_source(dataset.dataset_id, "https://a.example.com/x")

    storage.add_source(dataset.dataset_id, "https://b.example.com/x")

    active_sources = storage.list_sources(dataset.dataset_id, active_only=True)
    assert {s.source_url for s in active_sources} == {
        "https://a.example.com/x",
        "https://b.example.com/x",
    }


def test_replace_source_deactivates_old_but_keeps_history(storage):
    dataset = storage.create_dataset("A", ["x"])
    storage.add_source(dataset.dataset_id, "https://old.example.com/a")

    storage.replace_source(dataset.dataset_id, "https://old.example.com/a", "https://new.example.com/a")

    all_sources = storage.list_sources(dataset.dataset_id)
    assert len(all_sources) == 2  # cũ vẫn còn (audit), không bị xoá

    active_sources = storage.list_sources(dataset.dataset_id, active_only=True)
    assert len(active_sources) == 1
    assert active_sources[0].source_url == "https://new.example.com/a"

    old = next(s for s in all_sources if s.source_url == "https://old.example.com/a")
    assert old.active is False


def test_replace_source_does_not_affect_other_active_sources(storage):
    dataset = storage.create_dataset("A", ["x"])
    storage.add_source(dataset.dataset_id, "https://keep.example.com/a")
    storage.add_source(dataset.dataset_id, "https://old.example.com/a")

    storage.replace_source(dataset.dataset_id, "https://old.example.com/a", "https://new.example.com/a")

    active_sources = storage.list_sources(dataset.dataset_id, active_only=True)
    assert {s.source_url for s in active_sources} == {
        "https://keep.example.com/a",
        "https://new.example.com/a",
    }


def test_save_record_and_list_records(storage):
    dataset = storage.create_dataset("Giá vàng", ["price"])

    record = storage.save_record(
        dataset_id=dataset.dataset_id,
        source_url="https://example.com/gold",
        data={"price": 75000000},
        content_hash="abc123",
        evidence={"price": "giá 75.000.000 đồng"},
        confidence=0.92,
    )

    assert record.record_id
    assert record.data == {"price": 75000000}
    assert record.evidence == {"price": "giá 75.000.000 đồng"}
    assert record.confidence == 0.92
    assert record.needs_review is False  # mặc định khi không truyền

    records = storage.list_records(dataset.dataset_id)
    assert len(records) == 1
    assert records[0].record_id == record.record_id


def test_save_record_persists_needs_review_flag(storage):
    dataset = storage.create_dataset("Giá vàng", ["price"])

    record = storage.save_record(
        dataset_id=dataset.dataset_id,
        source_url="https://example.com/gold",
        data={"price": 1},
        content_hash="abc123",
        confidence=0.4,
        needs_review=True,
    )

    assert record.needs_review is True
    fetched = storage.list_records(dataset.dataset_id)[0]
    assert fetched.needs_review is True


def test_get_latest_record_for_source_returns_most_recent(storage):
    dataset = storage.create_dataset("Giá vàng", ["price"])
    url = "https://example.com/gold"

    storage.save_record(dataset.dataset_id, url, {"price": 1}, content_hash="hash1")
    latest = storage.save_record(dataset.dataset_id, url, {"price": 2}, content_hash="hash2")

    result = storage.get_latest_record_for_source(dataset.dataset_id, url)

    assert result.record_id == latest.record_id
    assert result.content_hash == "hash2"


def test_get_latest_record_for_source_returns_none_when_no_records(storage):
    dataset = storage.create_dataset("Giá vàng", ["price"])

    result = storage.get_latest_record_for_source(dataset.dataset_id, "https://none.example.com")

    assert result is None


def test_list_records_respects_limit_and_offset(storage):
    dataset = storage.create_dataset("Giá vàng", ["price"])
    for i in range(5):
        storage.save_record(
            dataset.dataset_id, f"https://example.com/{i}", {"price": i}, content_hash=f"h{i}"
        )

    page1 = storage.list_records(dataset.dataset_id, limit=2, offset=0)
    page2 = storage.list_records(dataset.dataset_id, limit=2, offset=2)

    assert len(page1) == 2
    assert len(page2) == 2
    assert {r.record_id for r in page1}.isdisjoint({r.record_id for r in page2})


def test_records_are_scoped_to_their_dataset(storage):
    dataset_a = storage.create_dataset("A", ["x"])
    dataset_b = storage.create_dataset("B", ["y"])
    storage.save_record(dataset_a.dataset_id, "https://a.example.com", {"x": 1}, "ha")
    storage.save_record(dataset_b.dataset_id, "https://b.example.com", {"y": 1}, "hb")

    records_a = storage.list_records(dataset_a.dataset_id)
    records_b = storage.list_records(dataset_b.dataset_id)

    assert len(records_a) == 1
    assert len(records_b) == 1
    assert records_a[0].dataset_id == dataset_a.dataset_id
    assert records_b[0].dataset_id == dataset_b.dataset_id


def test_get_extraction_strategy_returns_none_when_not_cached(storage):
    assert storage.get_extraction_strategy("example.com", "price") is None


def test_save_and_get_extraction_strategy_round_trip(storage):
    saved = storage.save_extraction_strategy(
        "example.com", "price", "div:nth-of-type(2) > span:nth-of-type(1)", sample_value="79900000"
    )

    fetched = storage.get_extraction_strategy("example.com", "price")

    assert fetched == saved
    assert fetched.selector == "div:nth-of-type(2) > span:nth-of-type(1)"
    assert fetched.sample_value == "79900000"


def test_save_extraction_strategy_overwrites_existing_entry_for_same_domain_and_field(storage):
    storage.save_extraction_strategy("example.com", "price", "old-selector", sample_value="1")

    storage.save_extraction_strategy("example.com", "price", "new-selector", sample_value="2")

    fetched = storage.get_extraction_strategy("example.com", "price")
    assert fetched.selector == "new-selector"
    assert fetched.sample_value == "2"


def test_extraction_strategies_are_scoped_by_domain_and_field_independently(storage):
    storage.save_extraction_strategy("a.example.com", "price", "selector-a")
    storage.save_extraction_strategy("b.example.com", "price", "selector-b")
    storage.save_extraction_strategy("a.example.com", "title", "selector-title")

    assert storage.get_extraction_strategy("a.example.com", "price").selector == "selector-a"
    assert storage.get_extraction_strategy("b.example.com", "price").selector == "selector-b"
    assert storage.get_extraction_strategy("a.example.com", "title").selector == "selector-title"


def test_create_scheduled_job_returns_job_with_id_and_defaults(storage):
    dataset = storage.create_dataset("Giá vàng", ["price"])

    job = storage.create_scheduled_job(
        dataset_id=dataset.dataset_id,
        url="https://example.com/gold",
        field_descriptions={"price": "giá bán"},
        trigger_type="interval",
        trigger_args={"hours": 1},
    )

    assert job.job_id
    assert job.dataset_id == dataset.dataset_id
    assert job.trigger_type == "interval"
    assert job.trigger_args == {"hours": 1}
    assert job.enabled is True
    assert job.last_run_at is None
    assert job.last_status is None
    assert storage.get_scheduled_job(job.job_id) == job


def test_get_scheduled_job_returns_none_when_missing(storage):
    assert storage.get_scheduled_job("does-not-exist") is None


def test_list_scheduled_jobs_returns_all_by_default(storage):
    dataset = storage.create_dataset("A", ["x"])
    storage.create_scheduled_job(dataset.dataset_id, "https://a.example.com", {"x": "x"}, "interval", {"hours": 1})
    storage.create_scheduled_job(dataset.dataset_id, "https://b.example.com", {"x": "x"}, "cron", {"hour": 8})

    jobs = storage.list_scheduled_jobs()

    assert {j.url for j in jobs} == {"https://a.example.com", "https://b.example.com"}


def test_update_scheduled_job_run_records_status_and_timestamp(storage):
    dataset = storage.create_dataset("A", ["x"])
    job = storage.create_scheduled_job(dataset.dataset_id, "https://a.example.com", {"x": "x"}, "interval", {"hours": 1})

    storage.update_scheduled_job_run(job.job_id, status="saved")

    updated = storage.get_scheduled_job(job.job_id)
    assert updated.last_status == "saved"
    assert updated.last_run_at is not None


def test_delete_scheduled_job_removes_it(storage):
    dataset = storage.create_dataset("A", ["x"])
    job = storage.create_scheduled_job(dataset.dataset_id, "https://a.example.com", {"x": "x"}, "interval", {"hours": 1})

    storage.delete_scheduled_job(job.job_id)

    assert storage.get_scheduled_job(job.job_id) is None


def test_update_scheduled_job_run_records_traceback(storage):
    dataset = storage.create_dataset("A", ["x"])
    job = storage.create_scheduled_job(dataset.dataset_id, "https://a.example.com", {"x": "x"}, "interval", {"hours": 1})

    storage.update_scheduled_job_run(job.job_id, status="error", traceback_text="Traceback...\nRuntimeError: boom")

    updated = storage.get_scheduled_job(job.job_id)
    assert updated.last_status == "error"
    assert "RuntimeError: boom" in updated.last_error_traceback


def test_create_scheduled_job_with_file_storage_mode_has_no_dataset_id(storage):
    job = storage.create_scheduled_job(
        dataset_id=None,
        url="https://example.com/gold",
        field_descriptions={"price": "giá bán"},
        trigger_type="interval",
        trigger_args={"hours": 1},
        storage_mode="file",
        file_path="gold.json",
        write_mode="append",
    )

    assert job.dataset_id is None
    assert job.storage_mode == "file"
    assert job.file_path == "gold.json"
    assert job.write_mode == "append"
    fetched = storage.get_scheduled_job(job.job_id)
    assert fetched == job


def test_scheduled_job_defaults_to_db_storage_mode(storage):
    dataset = storage.create_dataset("A", ["x"])
    job = storage.create_scheduled_job(dataset.dataset_id, "https://a.example.com", {"x": "x"}, "interval", {"hours": 1})

    assert job.storage_mode == "db"
    assert job.file_path is None


# ---- audit_log --------------------------------------------------------------
def test_add_audit_log_returns_entry_with_id_and_timestamp(storage):
    entry = storage.add_audit_log("debug_suggest_fix", job_id="job-1", detail={"ai_call_success": True})

    assert entry.id
    assert entry.event_type == "debug_suggest_fix"
    assert entry.job_id == "job-1"
    assert entry.detail == {"ai_call_success": True}


def test_list_audit_log_returns_entries_newest_first(storage):
    storage.add_audit_log("event_a", job_id="job-1")
    storage.add_audit_log("event_b", job_id="job-1")

    entries = storage.list_audit_log(job_id="job-1")

    assert [e.event_type for e in entries] == ["event_b", "event_a"]


def test_list_audit_log_filters_by_job_id(storage):
    storage.add_audit_log("event_a", job_id="job-1")
    storage.add_audit_log("event_b", job_id="job-2")

    entries = storage.list_audit_log(job_id="job-1")

    assert len(entries) == 1
    assert entries[0].job_id == "job-1"


def test_list_audit_log_without_job_id_returns_all(storage):
    storage.add_audit_log("event_a", job_id="job-1")
    storage.add_audit_log("event_b", job_id="job-2")

    entries = storage.list_audit_log()

    assert len(entries) == 2


def test_migrates_pre_existing_scheduled_jobs_table_missing_new_columns(tmp_path):
    """DB cục bộ tạo TRƯỚC khi có tính năng file/admin chỉ có schema cũ của
    scheduled_jobs (không có storage_mode/file_path/.../last_error_traceback)
    — SQLiteStorage phải tự thêm cột thiếu khi mở lại, không lỗi/mất dữ liệu cũ."""
    import sqlite3

    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE datasets (
            dataset_id TEXT PRIMARY KEY, dataset_name TEXT NOT NULL,
            schema_signature TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE scheduled_jobs (
            job_id TEXT PRIMARY KEY,
            dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id),
            url TEXT NOT NULL,
            field_descriptions TEXT NOT NULL,
            trigger_type TEXT NOT NULL,
            trigger_args TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            last_run_at TEXT,
            last_status TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO datasets VALUES ('ds1', 'Test', '[\"price\"]', '2026-01-01T00:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO scheduled_jobs "
        "(job_id, dataset_id, url, field_descriptions, trigger_type, trigger_args, enabled, created_at) "
        "VALUES ('job1', 'ds1', 'https://old.example.com', '{}', 'interval', '{}', 1, '2026-01-01T00:00:00+00:00')"
    )
    conn.commit()
    conn.close()

    storage = SQLiteStorage(str(db_path))
    try:
        job = storage.get_scheduled_job("job1")
        assert job is not None
        assert job.storage_mode == "db"  # cột mới, giá trị mặc định áp cho dòng cũ
        assert job.file_path is None
        assert job.last_error_traceback is None
    finally:
        storage.close()


def test_migrates_pre_existing_records_table_missing_needs_review_column(tmp_path):
    """DB cục bộ tạo TRƯỚC khi có tính năng needs_review chỉ có schema cũ của
    `records` (không có cột `needs_review`) — SQLiteStorage phải tự thêm cột
    thiếu khi mở lại, record cũ mặc định needs_review=False."""
    import sqlite3

    db_path = tmp_path / "legacy_records.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE datasets (
            dataset_id TEXT PRIMARY KEY, dataset_name TEXT NOT NULL,
            schema_signature TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE records (
            record_id TEXT PRIMARY KEY,
            dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id),
            source_url TEXT NOT NULL,
            data TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            evidence TEXT,
            confidence REAL,
            crawled_at TEXT NOT NULL,
            as_of TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO datasets VALUES ('ds1', 'Test', '[\"price\"]', '2026-01-01T00:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO records (record_id, dataset_id, source_url, data, content_hash, crawled_at) "
        "VALUES ('rec1', 'ds1', 'https://old.example.com', '{}', 'hash1', '2026-01-01T00:00:00+00:00')"
    )
    conn.commit()
    conn.close()

    storage = SQLiteStorage(str(db_path))
    try:
        records = storage.list_records("ds1")
        assert len(records) == 1
        assert records[0].needs_review is False
    finally:
        storage.close()
