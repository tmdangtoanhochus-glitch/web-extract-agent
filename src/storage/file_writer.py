"""Ghi kết quả crawl ra file — hỗ trợ .json, .csv, .xlsx theo phần mở rộng.

Người dùng chọn file_path khi tạo job — hệ thống tự nhận định dạng từ extension:
- .json (mặc định): JSON array, đọc/sửa/ghi lại bằng json.load/json.dump
- .csv: CSV với UTF-8 BOM (Excel mở đúng tiếng Việt)
- .xlsx: Excel qua pandas + openpyxl

An toàn: mọi file_path phải resolve vào bên trong EXPORTS_ROOT (mặc định
data/exports/) — chặn đường dẫn tuyệt đối và path traversal (..).
"""
from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

EXPORTS_ROOT = Path("data/exports")

WriteMode = Literal["append", "new_file", "overwrite_row"]
_VALID_WRITE_MODES = ("append", "new_file", "overwrite_row")


class InvalidFilePathError(ValueError):
    pass


class InvalidKeyFieldError(ValueError):
    pass


@dataclass(frozen=True)
class FileWriteResult:
    file_path: str
    write_mode: str
    record_count: int


def resolve_export_path(file_path: str, exports_root: Path = EXPORTS_ROOT) -> Path:
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


def _get_format(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".xlsx":
        return "xlsx"
    if suffix == ".csv":
        return "csv"
    if suffix == ".parquet":
        return "parquet"
    return "json"


def _read_records(path: Path) -> list[dict[str, Any]]:
    fmt = _get_format(path)
    if not path.exists():
        return []
    if fmt == "json":
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            return []
        data = json.loads(text)
        if not isinstance(data, list):
            return []
        return data
    if fmt == "csv":
        text = path.read_text(encoding="utf-8-sig")
        if not text.strip():
            return []
        reader = csv.DictReader(io.StringIO(text))
        return [dict(row) for row in reader]
    if fmt == "xlsx":
        import pandas as pd
        df = pd.read_excel(path, engine="openpyxl")
        return df.to_dict("records")
    if fmt == "parquet":
        import pandas as pd
        df = pd.read_parquet(path, engine="pyarrow")
        return df.to_dict("records")
    return []


def _write_records(path: Path, records: list[dict[str, Any]]) -> None:
    fmt = _get_format(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    elif fmt == "csv":
        buffer = io.StringIO()
        if records:
            fieldnames = list(records[0].keys())
            writer = csv.DictWriter(buffer, fieldnames=fieldnames)
            writer.writeheader()
            for r in records:
                writer.writerow(r)
        path.write_text("\ufeff" + buffer.getvalue(), encoding="utf-8")
    elif fmt == "xlsx":
        import pandas as pd
        df = pd.DataFrame(records) if records else pd.DataFrame()
        df.to_excel(path, index=False, engine="openpyxl")
    elif fmt == "parquet":
        import pandas as pd
        df = pd.DataFrame(records) if records else pd.DataFrame()
        df.to_parquet(path, index=False, engine="pyarrow")


def _unique_new_file_path(path: Path) -> Path:
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
            f"key_field {key_field!r} không nằm trong field_descriptions: {field_names}"
        )


def write_record(
    file_path: str,
    record: dict[str, Any],
    write_mode: str,
    key_field: Optional[str] = None,
    field_names: Optional[list[str]] = None,
    exports_root: Path = EXPORTS_ROOT,
) -> FileWriteResult:
    if write_mode not in _VALID_WRITE_MODES:
        raise ValueError(f"write_mode không hợp lệ: {write_mode!r}")
    _validate_key_field(write_mode, key_field, field_names)

    exports_root_resolved = exports_root.resolve()
    resolved_path = resolve_export_path(file_path, exports_root)

    if write_mode == "new_file":
        target_path = _unique_new_file_path(resolved_path)
        _write_records(target_path, [record])
        return FileWriteResult(
            file_path=str(target_path.relative_to(exports_root_resolved)),
            write_mode=write_mode,
            record_count=1,
        )

    records = _read_records(resolved_path)

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

    _write_records(resolved_path, records)
    return FileWriteResult(
        file_path=str(resolved_path.relative_to(exports_root_resolved)),
        write_mode=write_mode,
        record_count=len(records),
    )
