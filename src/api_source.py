"""Nguồn dữ liệu là API JSON: người dùng dán link API vào ô URL và tick "Nguồn là API".

Không gọi AI: tìm mảng bản ghi trong JSON rồi ghép tên field người dùng khai báo với khóa JSON.
Mỗi giá trị lấy trực tiếp từ JSON nên confidence = 1.0 và evidence là đường dẫn khóa.
"""
from __future__ import annotations

import ipaddress
import json
import re
import unicodedata
from typing import Any, Optional
from urllib.parse import urlsplit

from .ai.base import FieldExtraction

MAX_BODY_CHARS = 10_000_000
_BLOCKED_HOST_SUFFIXES = (".local", ".internal", ".localhost")


class ApiSourceError(ValueError):
    """Lỗi nguồn API mà người dùng sửa được (không phải JSON, không có mảng bản ghi, field không ghép được)."""


def assert_public_url(url: str) -> None:
    """Chặn địa chỉ nội bộ/loopback dạng chữ số hoặc tên máy chủ nội bộ (không phân giải DNS)."""
    host = (urlsplit(url).hostname or "").lower()
    if not host or host == "localhost" or host.endswith(_BLOCKED_HOST_SUFFIXES):
        raise ApiSourceError("Nguồn API không được trỏ tới địa chỉ nội bộ")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return
    if not address.is_global:
        raise ApiSourceError("Nguồn API không được trỏ tới địa chỉ IP nội bộ")


def _normalize(text: Any) -> str:
    decomposed = unicodedata.normalize("NFD", str(text).replace("đ", "d").replace("Đ", "D"))
    plain = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]", "", plain.lower())


def parse_json(body: str) -> Any:
    if len(body) > MAX_BODY_CHARS:
        raise ApiSourceError("Phản hồi API quá lớn (tối đa 10 triệu ký tự)")
    try:
        return json.loads(body)
    except ValueError:
        raise ApiSourceError("Phản hồi không phải JSON; bỏ tick 'Nguồn là API' nếu đây là trang web thường") from None


def find_records(data: Any) -> list[dict]:
    """Mảng object lớn nhất trong JSON (ưu tiên nông hơn khi bằng nhau). Object đơn = 1 bản ghi."""
    best: tuple[int, int, list[dict]] = (0, 0, [])

    def walk(node: Any, depth: int) -> None:
        nonlocal best
        if isinstance(node, list):
            rows = [item for item in node if isinstance(item, dict)]
            if rows and (len(rows), -depth) > (best[0], -best[1]):
                best = (len(rows), depth, rows)
            for item in node[:50]:
                walk(item, depth + 1)
        elif isinstance(node, dict):
            for value in node.values():
                walk(value, depth + 1)

    walk(data, 0)
    if best[2]:
        return best[2]
    if isinstance(data, dict) and data:
        return [data]
    raise ApiSourceError("Không tìm thấy mảng bản ghi nào trong JSON")


def _flatten(record: dict, prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in record.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, path + "."))
        else:
            flat[path] = value
    return flat


def _cell(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return value


def map_fields(keys: list[str], field_descriptions: dict[str, str]) -> dict[str, str]:
    """Tên field -> khóa JSON: khớp theo tên rồi theo mô tả (bỏ dấu, hoa/thường, ký tự phân cách).
    Khóa lồng nhau dùng dạng `a.b`; tên chỉ khớp phần cuối `b` khi không mơ hồ."""
    by_full = {_normalize(key): key for key in keys}
    tails: dict[str, list[str]] = {}
    for key in keys:
        tails.setdefault(_normalize(key.rsplit(".", 1)[-1]), []).append(key)
    mapping: dict[str, str] = {}
    for name, description in field_descriptions.items():
        for candidate in (name, description):
            norm = _normalize(candidate)
            if not norm:
                continue
            if norm in by_full:
                mapping[name] = by_full[norm]
                break
            if len(tails.get(norm, [])) == 1:
                mapping[name] = tails[norm][0]
                break
    return mapping


def extract_api_records(body: str, field_descriptions: dict[str, str]) -> list[dict[str, FieldExtraction]]:
    """JSON -> danh sách bản ghi theo field người dùng khai báo; báo rõ field nào không ghép được."""
    records = [_flatten(r) for r in find_records(parse_json(body))]
    keys = list(dict.fromkeys(k for r in records for k in r))
    mapping = map_fields(keys, field_descriptions)
    missing = [name for name in field_descriptions if name not in mapping]
    if missing:
        shown = ", ".join(keys[:30]) + (" …" if len(keys) > 30 else "")
        raise ApiSourceError(
            f"Không ghép được field {', '.join(missing)} với khóa JSON. "
            f"Đặt tên field (hoặc ghi khóa vào mô tả) trùng một trong: {shown}"
        )
    return [
        {name: FieldExtraction(value=_cell(record.get(key)), confidence=1.0, evidence=f"api:{key}")
         for name, key in mapping.items()}
        for record in records
    ]

