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

    records = storage.list_records(dataset.dataset_id)
    assert len(records) == 1
    assert records[0].record_id == record.record_id


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
