"""Trích xuất structured data có sẵn (JSON-LD, Open Graph) từ HTML THÔ — chạy
TRƯỚC khi gọi AI (CLAUDE.md mục 2): ưu tiên dùng trực tiếp nếu trang đã tự khai
báo, chỉ fallback sang AI cho field không tìm thấy — giảm gọi AI (rẻ hơn,
không suy diễn, kiểm soát được).

Chạy trên HTML gốc (trước `clean_html()`), vì `clean_html()` bỏ hết thẻ
`<script>` — JSON-LD nằm trong `<script type="application/ld+json">` sẽ mất
nếu chạy sau bước làm sạch.

Đây là bước rule-based thuần túy: chỉ đọc thẻ có sẵn, KHÔNG suy luận ngữ nghĩa.
Việc khớp với field người dùng đặt tên dựa trên bảng đồng nghĩa cố định
(`_FIELD_SYNONYMS`) theo TÊN field (không theo mô tả tự nhiên — đó là việc của
AI) — tên field nào không có trong bảng, hoặc structured data không có giá trị
tương ứng, luôn rơi xuống AI ở tầng gọi (`pipeline.py`), không cố đoán bừa.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Optional

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StructuredValue:
    """1 giá trị match được, kèm nguồn gốc để làm evidence (audit lại được)."""

    value: Any
    source: str  # vd. "og:title" hoặc "jsonld.offers.price"


@dataclass(frozen=True)
class StructuredData:
    """Toàn bộ structured data tìm thấy trên trang, đã flatten thành 1 dict
    phẳng key -> value (khoá dạng "og:<prop>" hoặc "jsonld.<path.lồng.nhau>")."""

    values: dict[str, Any]

    def get(self, key: str) -> Optional[Any]:
        return self.values.get(key)


def extract_structured_data(html: str) -> StructuredData:
    soup = BeautifulSoup(html, "html.parser")
    values: dict[str, Any] = {}
    values.update(_extract_open_graph(soup))
    # JSON-LD ghi đè cùng khoá nếu trùng — ưu tiên JSON-LD vì thường đầy đủ/có
    # cấu trúc (schema.org) hơn Open Graph (vốn chỉ để chia sẻ mạng xã hội).
    values.update(_extract_json_ld(soup))
    return StructuredData(values=values)


def _extract_open_graph(soup: BeautifulSoup) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for tag in soup.find_all("meta"):
        prop = tag.get("property")
        content = tag.get("content")
        if prop and content and prop.startswith("og:") and content.strip():
            values[prop] = content.strip()
    return values


def _extract_json_ld(soup: BeautifulSoup) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for tag in soup.find_all("script", type="application/ld+json"):
        raw = tag.string or tag.get_text()
        if not raw or not raw.strip():
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            logger.debug("Bỏ qua JSON-LD không parse được: %r", raw[:200])
            continue

        for obj in _iter_json_ld_objects(parsed):
            flat = _flatten(obj, prefix="jsonld")
            values.update(flat)
    return values


def _iter_json_ld_objects(parsed: Any):
    """1 trang có thể có nhiều <script ld+json>, mỗi cái có thể là 1 object,
    1 list object, hoặc dùng `@graph` chứa nhiều object lồng nhau."""
    if isinstance(parsed, list):
        for item in parsed:
            yield from _iter_json_ld_objects(item)
    elif isinstance(parsed, dict):
        if isinstance(parsed.get("@graph"), list):
            for item in parsed["@graph"]:
                yield from _iter_json_ld_objects(item)
        else:
            yield parsed


def _flatten(obj: Any, prefix: str, _depth: int = 0) -> dict[str, Any]:
    """Flatten dict lồng nhau thành key "prefix.a.b". List lấy phần tử đầu
    tiên (đủ dùng cho field đơn trị phổ biến như offers/author/brand). Giới
    hạn độ sâu để tránh JSON-LD lồng bất thường/vòng lặp."""
    flat: dict[str, Any] = {}
    if _depth > 6:
        return flat
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key.startswith("@"):
                continue
            flat.update(_flatten(value, f"{prefix}.{key}", _depth + 1))
    elif isinstance(obj, list):
        if obj:
            flat.update(_flatten(obj[0], prefix, _depth + 1))
    elif obj not in (None, ""):
        flat[prefix] = obj
    return flat


# Bảng đồng nghĩa cố định: tên field (đã chuẩn hoá) -> danh sách khoá structured
# data cần thử, theo thứ tự ưu tiên. CHỈ thêm khi có ý nghĩa rõ ràng, phổ biến
# theo chuẩn Open Graph / schema.org — không đoán field nghiệp vụ tuỳ ý.
_FIELD_SYNONYMS: dict[str, tuple[str, ...]] = {
    "title": ("og:title", "jsonld.name", "jsonld.headline"),
    "name": ("jsonld.name", "og:title"),
    "description": ("og:description", "jsonld.description"),
    "image": ("og:image", "jsonld.image"),
    "url": ("og:url", "jsonld.url"),
    "site_name": ("og:site_name",),
    "price": ("jsonld.offers.price", "jsonld.price"),
    "price_currency": ("jsonld.offers.priceCurrency",),
    "currency": ("jsonld.offers.priceCurrency",),
    "availability": ("jsonld.offers.availability",),
    "author": ("jsonld.author.name",),
    "brand": ("jsonld.brand.name",),
    "sku": ("jsonld.sku",),
    "rating": ("jsonld.aggregateRating.ratingValue",),
    "rating_value": ("jsonld.aggregateRating.ratingValue",),
    "review_count": ("jsonld.aggregateRating.reviewCount",),
    "date_published": ("jsonld.datePublished",),
    "published_at": ("jsonld.datePublished",),
    "date_modified": ("jsonld.dateModified",),
}


def _normalize_field_name(name: str) -> str:
    """Bỏ dấu, thường hoá, thay khoảng trắng/dấu nối bằng "_" — để "Tên sản
    phẩm", "ten-san-pham", "TEN_SAN_PHAM" cùng chuẩn hoá về 1 dạng tra bảng."""
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    normalized = normalized.strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    return normalized


def match_field(field_name: str, structured: StructuredData) -> Optional[StructuredValue]:
    """Rule-based match tên field với bảng đồng nghĩa cố định. Field không có
    trong bảng, hoặc structured data không có giá trị tương ứng, trả `None`
    để tầng gọi (`pipeline.py`) fallback sang AI cho đúng field đó."""
    normalized = _normalize_field_name(field_name)
    for key in _FIELD_SYNONYMS.get(normalized, ()):
        value = structured.get(key)
        if value not in (None, ""):
            return StructuredValue(value=value, source=key)
    return None
