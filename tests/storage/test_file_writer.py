"""Test file_writer.py — luồng "Lưu ra file" độc lập với DB, không cần test
tích hợp với StorageEngine (đúng yêu cầu: luồng riêng, không đi qua các bước
kiểm tra như luồng DB). Dùng `tmp_path` làm exports_root để không đụng
`data/exports/` thật."""
import json

import pytest

from src.storage.file_writer import (
    InvalidFilePathError,
    InvalidKeyFieldError,
    resolve_export_path,
    write_record,
)


def _read(path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


# ---- resolve_export_path / path traversal ---------------------------------
def test_resolve_export_path_accepts_simple_relative_path(tmp_path):
    resolved = resolve_export_path("gold.json", exports_root=tmp_path)
    assert resolved == (tmp_path / "gold.json").resolve()


def test_resolve_export_path_accepts_nested_relative_path(tmp_path):
    resolved = resolve_export_path("sub/dir/gold.json", exports_root=tmp_path)
    assert resolved == (tmp_path / "sub" / "dir" / "gold.json").resolve()


def test_resolve_export_path_rejects_empty_path(tmp_path):
    with pytest.raises(InvalidFilePathError):
        resolve_export_path("", exports_root=tmp_path)


def test_resolve_export_path_rejects_absolute_path(tmp_path):
    with pytest.raises(InvalidFilePathError):
        resolve_export_path("/etc/passwd", exports_root=tmp_path)


def test_resolve_export_path_rejects_parent_traversal(tmp_path):
    with pytest.raises(InvalidFilePathError):
        resolve_export_path("../../etc/passwd", exports_root=tmp_path)


def test_resolve_export_path_rejects_traversal_in_middle_of_path(tmp_path):
    with pytest.raises(InvalidFilePathError):
        resolve_export_path("sub/../../escape.json", exports_root=tmp_path)


# ---- write_mode="append" ---------------------------------------------------
def test_append_creates_file_when_missing(tmp_path):
    result = write_record("gold.json", {"price": 1}, "append", exports_root=tmp_path)

    assert result.record_count == 1
    assert _read(tmp_path / "gold.json") == [{"price": 1}]


def test_append_adds_to_existing_file(tmp_path):
    write_record("gold.json", {"price": 1}, "append", exports_root=tmp_path)
    result = write_record("gold.json", {"price": 2}, "append", exports_root=tmp_path)

    assert result.record_count == 2
    assert _read(tmp_path / "gold.json") == [{"price": 1}, {"price": 2}]


def test_append_creates_parent_directories(tmp_path):
    write_record("a/b/gold.json", {"price": 1}, "append", exports_root=tmp_path)

    assert (tmp_path / "a" / "b" / "gold.json").exists()


# ---- write_mode="new_file" --------------------------------------------------
def test_new_file_creates_file_with_single_record(tmp_path):
    result = write_record("gold.json", {"price": 1}, "new_file", exports_root=tmp_path)

    assert result.file_path == "gold.json"
    assert _read(tmp_path / "gold.json") == [{"price": 1}]


def test_new_file_does_not_overwrite_existing_adds_timestamp_suffix(tmp_path):
    write_record("gold.json", {"price": 1}, "new_file", exports_root=tmp_path)

    result = write_record("gold.json", {"price": 2}, "new_file", exports_root=tmp_path)

    assert result.file_path != "gold.json"
    assert result.file_path.startswith("gold_")
    assert result.file_path.endswith(".json")
    # File cũ vẫn nguyên vẹn, không bị ghi đè.
    assert _read(tmp_path / "gold.json") == [{"price": 1}]
    assert _read(tmp_path / result.file_path) == [{"price": 2}]


# ---- write_mode="overwrite_row" --------------------------------------------
def test_overwrite_row_replaces_matching_record(tmp_path):
    write_record("gold.json", {"sku": "A", "price": 1}, "append", exports_root=tmp_path)
    write_record("gold.json", {"sku": "B", "price": 2}, "append", exports_root=tmp_path)

    result = write_record(
        "gold.json", {"sku": "A", "price": 999}, "overwrite_row", key_field="sku", exports_root=tmp_path
    )

    assert result.record_count == 2
    assert _read(tmp_path / "gold.json") == [{"sku": "A", "price": 999}, {"sku": "B", "price": 2}]


def test_overwrite_row_appends_when_key_not_found(tmp_path):
    write_record("gold.json", {"sku": "A", "price": 1}, "append", exports_root=tmp_path)

    result = write_record(
        "gold.json", {"sku": "C", "price": 3}, "overwrite_row", key_field="sku", exports_root=tmp_path
    )

    assert result.record_count == 2
    assert _read(tmp_path / "gold.json")[-1] == {"sku": "C", "price": 3}


def test_overwrite_row_creates_file_when_missing(tmp_path):
    result = write_record(
        "gold.json", {"sku": "A", "price": 1}, "overwrite_row", key_field="sku", exports_root=tmp_path
    )

    assert result.record_count == 1


def test_overwrite_row_without_key_field_raises():
    with pytest.raises(InvalidKeyFieldError):
        write_record("gold.json", {"price": 1}, "overwrite_row", key_field=None)


def test_overwrite_row_with_key_field_not_in_declared_fields_raises():
    with pytest.raises(InvalidKeyFieldError):
        write_record(
            "gold.json",
            {"price": 1},
            "overwrite_row",
            key_field="not_declared",
            field_names=["price", "date"],
        )


def test_overwrite_row_with_key_field_in_declared_fields_succeeds(tmp_path):
    result = write_record(
        "gold.json",
        {"price": 1, "date": "2026-09-13"},
        "overwrite_row",
        key_field="price",
        field_names=["price", "date"],
        exports_root=tmp_path,
    )

    assert result.record_count == 1


# ---- misc -------------------------------------------------------------------
def test_invalid_write_mode_raises_value_error(tmp_path):
    with pytest.raises(ValueError):
        write_record("gold.json", {"price": 1}, "not_a_real_mode", exports_root=tmp_path)


def test_write_record_rejects_path_traversal(tmp_path):
    with pytest.raises(InvalidFilePathError):
        write_record("../escape.json", {"price": 1}, "append", exports_root=tmp_path)
