import csv
import io
from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient

from src.api.dataset_export import csv_cell, export_csv
from src.api.main import create_app
from src.storage.sqlite_storage import SQLiteStorage


def parse(content):
    return list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))


def test_exports_more_than_page_limit_and_keeps_metadata_separate():
    storage = SQLiteStorage(":memory:")
    ds = storage.create_dataset("History", ["value", "source_url"])
    for index in range(1105):
        storage.save_record(ds.dataset_id, "https://example.test", {"value": index, "source_url": "cell-value"}, str(index))
    client = TestClient(create_app(None, None, storage))
    response = client.get(f"/datasets/{ds.dataset_id}/export.csv")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    rows = parse(response.content)
    assert len(rows) == 1105 and len({r["meta.record_id"] for r in rows}) == 1105
    assert rows[0]["data.source_url"] == "cell-value" and rows[0]["meta.source_url"] == "https://example.test"
    event = storage.list_audit_log()[0]
    assert event.detail["records"] == 1105 and event.detail["complete"] is True
    assert "cell-value" not in str(event.detail)


def test_keyset_same_timestamp_and_concurrent_append_do_not_duplicate(monkeypatch):
    from src.storage import sqlite_storage
    original = datetime(2026, 9, 15, tzinfo=timezone.utc)
    monkeypatch.setattr(sqlite_storage, "utcnow", lambda: original)
    storage = SQLiteStorage(":memory:")
    ds = storage.create_dataset("History", ["value"])
    for i in range(6):
        storage.save_record(ds.dataset_id, "https://example.test", {"value": i}, str(i))
    stream = export_csv(storage, ds, original + timedelta(seconds=1), page_size=2)
    chunks = [next(stream), next(stream)]
    monkeypatch.setattr(sqlite_storage, "utcnow", lambda: original + timedelta(seconds=2))
    storage.save_record(ds.dataset_id, "https://example.test", {"value": "new"}, "new")
    chunks.extend(stream)
    rows = parse(b"".join(chunks))
    assert len(rows) == 6 and len({row["meta.record_id"] for row in rows}) == 6
    assert "new" not in {row["data.value"] for row in rows}


def test_date_filter_inclusive_utc_and_missing_as_of():
    storage = SQLiteStorage(":memory:")
    ds = storage.create_dataset("History", ["value"])
    for i, timestamp in enumerate([None, datetime(2026, 9, 14, tzinfo=timezone.utc),
        datetime(2026, 9, 15, tzinfo=timezone.utc), datetime(2026, 9, 16, 23, 59, tzinfo=timezone.utc),
        datetime(2026, 9, 17, 1, tzinfo=timezone(timedelta(hours=7)))]):
        storage.save_record(ds.dataset_id, "https://example.test", {"value": i}, str(i), as_of=timestamp)
    client = TestClient(create_app(None, None, storage))
    path = f"/datasets/{ds.dataset_id}/export.csv"
    response = client.get(path + "?date_basis=as_of&start=2026-09-15&end=2026-09-16")
    assert {row["data.value"] for row in parse(response.content)} == {"2", "3", "4"}
    assert client.get(path + "?start=2026-09-16&end=2026-09-15").status_code == 400
    assert client.get(path + "?date_basis=arbitrary").status_code == 422
    assert client.get("/datasets/missing/export.csv").status_code == 404


def test_csv_quotes_unicode_newlines_json_and_formula_text():
    storage = SQLiteStorage(":memory:")
    ds = storage.create_dataset("History", ["value"])
    values = ['Tiếng Việt, "quoted"\nnext line', '=SUM(1,2)', ' \t@SUM(1)', -25, {"nested": [1, 2]}]
    for i, value in enumerate(values):
        storage.save_record(ds.dataset_id, "https://example.test", {"value": value}, str(i))
    content = b"".join(export_csv(storage, ds, datetime.now(timezone.utc)))
    result = {row["data.value"] for row in parse(content)}
    assert values[0] in result and "'=SUM(1,2)" in result and "' \t@SUM(1)" in result
    assert "-25" in result and '{"nested": [1, 2]}' in result
    assert csv_cell(None) == "" and csv_cell("-25") == "'-25"


def test_empty_export_has_header_and_no_data():
    storage = SQLiteStorage(":memory:")
    ds = storage.create_dataset("Empty", ["value"])
    content = b"".join(export_csv(storage, ds, datetime.now(timezone.utc)))
    assert parse(content) == [] and b"data.value" in content


def test_interrupted_stream_is_not_a_completed_export():
    storage = SQLiteStorage(":memory:")
    ds = storage.create_dataset("History", ["value"])
    for i in range(3):
        storage.save_record(ds.dataset_id, "https://example.test", {"value": i}, str(i))
    stream = export_csv(storage, ds, datetime.now(timezone.utc), page_size=1)
    next(stream)
    next(stream)
    stream.close()
    assert storage.list_audit_log()[0].detail["complete"] is False


def test_export_includes_records_exactly_at_cutoff(monkeypatch):
    from src.storage import sqlite_storage
    timestamp = datetime(2026, 9, 16, tzinfo=timezone.utc)
    monkeypatch.setattr(sqlite_storage, "utcnow", lambda: timestamp)
    storage = SQLiteStorage(":memory:")
    ds = storage.create_dataset("History", ["value"])
    storage.save_record(ds.dataset_id, "https://example.test", {"value": "same-time"}, "1")
    rows = parse(b"".join(export_csv(storage, ds, timestamp)))
    assert len(rows) == 1 and rows[0]["data.value"] == "same-time"
