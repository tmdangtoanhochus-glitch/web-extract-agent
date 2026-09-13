"""Ghi kết quả crawl ra file JSON — lựa chọn "Lưu ra file" NGANG HÀNG với lưu
DB (KHÔNG phải ghi kép, người dùng chọn 1 trong 2 khi tạo job).

Cố tình KHÔNG implement chung interface `StorageEngine` (`src/storage/base.py`)
— luồng file đơn giản hơn có chủ đích: KHÔNG dedup theo content_hash, KHÔNG
schema-match, KHÔNG tạo `dataset_id`, chỉ ghi thẳng theo cấu hình người dùng
chọn khi tạo job.

File luôn là 1 JSON array (không dùng JSONL) — để `overwrite_row` đọc/sửa/ghi
lại toàn file dễ dàng bằng `json.load`/`json.dump` thường, không cần xử lý
từng dòng.

An toàn: mọi `file_path` phải resolve vào bên trong `EXPORTS_ROOT` (mặc định
`data/exports/`) — chặn đường dẫn tuyệt đối và path traversal (`..`).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

EXPORTS_ROOT = Path("data/exports")

WriteMode = Literal["append", "new_file", "overwrite_row"]
_VALID_WRITE_MODES = ("append", "new_file", "overwrite_row")


class InvalidFilePathError(ValueError):
    """`file_path` không hợp lệ (rỗng, tuyệt đối, chứa '..', hoặc thoát khỏi
    `EXPORTS_ROOT` sau khi resolve)."""


class InvalidKeyFieldError(ValueError):
    """`key_field` thiếu (bắt buộc khi `write_mode="overwrite_row"`) hoặc
    không nằm trong danh sách field đã khai báo của job."""


@dataclass(frozen=True)
class FileWriteResult:
    file_path: str  # đường dẫn tương đối (trong EXPORTS_ROOT) THỰC SỰ đã ghi
    write_mode: str
    record_count: int  # tổng số record trong file sau khi ghi


def resolve_export_path(file_path: str, exports_root: Path = EXPORTS_ROOT) -> Path:
    """Validate + resolve `file_path` (tương đối) vào bên trong `exports_root`.

    Raise `InvalidFilePathError` nếu path rỗng, tuyệt đối, chứa `..`, hoặc sau
    khi resolve thực sự nằm ngoài `exports_root` (path traversal)."""
    if not file_path or not file_path.strip():
        raise InvalidFilePathError("file_path không được rỗng")

    candidate = Path(file_path)
    if candidate.is_absolute():
        raise InvalidFilePathError(f"file_path phải là đường dẫn tương đối: {file_path!r}")
    if ".." in candidate.parts:
        raise InvalidFilePathError(f"file_path không được chứa '..': {file_path!r}")

    exports_root_resolved = exports_root.resolve()
    full_path = (exports_root_resolved / candidate).resolve()
    if full_path != exports_root_resolved and exports_root_resolved not in full_path.parents:
        raise InvalidFilePathError(f"file_path phải nằm trong {exports_root}: {file_path!r}")
    return full_path


def _read_json_array(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return []
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError(f"File {path} không phải JSON array hợp lệ")
    return data


def _write_json_array(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def _unique_new_file_path(path: Path) -> Path:
    """`new_file`: không ghi đè, không báo lỗi — tự thêm hậu tố timestamp vào
    TÊN FILE nếu path đã tồn tại (vd. `ten-file_20260913_143022.json`)."""
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    candidate = path.with_name(f"{stem}_{timestamp}{suffix}")
    counter = 1
    while candidate.exists():
        candidate = path.with_name(f"{stem}_{timestamp}_{counter}{suffix}")
        counter += 1
    return candidate


def _validate_key_field(
    write_mode: str, key_field: Optional[str], field_names: Optional[list[str]]
) -> None:
    if write_mode != "overwrite_row":
        return
    if not key_field:
        raise InvalidKeyFieldError("write_mode='overwrite_row' cần key_field")
    if field_names is not None and key_field not in field_names:
        raise InvalidKeyFieldError(
            f"key_field {key_field!r} không nằm trong field_descriptions đã khai báo: {field_names}"
        )


def write_record(
    file_path: str,
    record: dict[str, Any],
    write_mode: str,
    key_field: Optional[str] = None,
    field_names: Optional[list[str]] = None,
    exports_root: Path = EXPORTS_ROOT,
) -> FileWriteResult:
    """Ghi 1 record vào file JSON array theo `write_mode` (mục 3 yêu cầu):

    - `append`: đọc file cũ (nếu có, không thì mảng rỗng), thêm record vào
      cuối, ghi lại cả file. Tạo file mới nếu chưa tồn tại.
    - `new_file`: LUÔN ghi ra 1 file mới (chỉ chứa `record` này) — nếu tên
      file đã tồn tại thì tự thêm hậu tố timestamp, không ghi đè/không lỗi.
    - `overwrite_row`: cần `key_field` (validate nằm trong `field_names` nếu
      có truyền) — tìm phần tử có `record[key_field]` trùng, thay thế; không
      tìm thấy thì coi như `append`.
    """
    if write_mode not in _VALID_WRITE_MODES:
        raise ValueError(f"write_mode không hợp lệ: {write_mode!r} — phải là 1 trong {_VALID_WRITE_MODES}")
    _validate_key_field(write_mode, key_field, field_names)

    exports_root_resolved = exports_root.resolve()
    resolved_path = resolve_export_path(file_path, exports_root)

    if write_mode == "new_file":
        target_path = _unique_new_file_path(resolved_path)
        _write_json_array(target_path, [record])
        return FileWriteResult(
            file_path=str(target_path.relative_to(exports_root_resolved)),
            write_mode=write_mode,
            record_count=1,
        )

    records = _read_json_array(resolved_path)

    if write_mode == "append":
        records.append(record)
    else:  # overwrite_row
        assert key_field is not None
        key_value = record.get(key_field)
        for idx, existing in enumerate(records):
            if existing.get(key_field) == key_value:
                records[idx] = record
                break
        else:
            records.append(record)

    _write_json_array(resolved_path, records)
    return FileWriteResult(
        file_path=str(resolved_path.relative_to(exports_root_resolved)),
        write_mode=write_mode,
        record_count=len(records),
    )
