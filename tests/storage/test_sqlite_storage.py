"""Test SQLiteStorage bằng DB SQLite in-memory — nhanh, không đụng file thật.

Test hành vi chung của interface `StorageEngine` nằm ở `storage_contract.py`
(dùng chung với `test_postgres_storage.py`, import qua `*` bên dưới) — file
này chỉ giữ lại fixture `storage` riêng cho SQLite + các test đặc thù
implementation này (migration cột cho DB cũ, xem cuối file)."""
import pytest

from src.storage.sqlite_storage import SQLiteStorage
from storage_contract import *  # noqa: F401,F403 — test hành vi chung StorageEngine


@pytest.fixture
def storage():
    store = SQLiteStorage(":memory:")
    yield store
    store.close()


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
