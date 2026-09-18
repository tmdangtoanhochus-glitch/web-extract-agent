"""Tìm & áp dụng CSS selector trỏ tới giá trị 1 field trong HTML — dùng để
cache "chiến lược" extract theo domain (CLAUDE.md mục 5): lần đầu AI tìm ra
giá trị, suy ra selector trỏ tới đúng vị trí đó rồi lưu lại (qua
`StorageEngine.save_extraction_strategy`); lần cào sau áp lại selector bằng
rule-based (BeautifulSoup) — không cần gọi AI nếu vẫn khớp.

Selector sinh ra là selector VỊ TRÍ (dùng `:nth-of-type`), KHÔNG dựa vào
class/id — id/class thường không ổn định giữa các lần render (đặc biệt site
dùng framework sinh class dạng hash), trong khi vị trí trong DOM thường ổn
định qua các lần cào cùng 1 trang (nội dung đổi nhưng cấu trúc không đổi). Khi
site đổi CẤU TRÚC thật, selector sẽ không còn khớp (hoặc khớp sai vị trí) →
`apply_selector` trả `None` → tầng gọi (`pipeline.py`) tự fallback sang AI,
đúng yêu cầu "chỉ gọi AI lại khi cache fail".
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

from bs4 import BeautifulSoup
from bs4.element import Tag

logger = logging.getLogger(__name__)


def find_selector(html: str, value: Any) -> Optional[str]:
    """Tìm selector trỏ tới element CỤ THỂ NHẤT (text ngắn nhất trong số các
    element chứa `value`) — ưu tiên element lá thay vì 1 ancestor lớn cũng vô
    tình chứa cùng text. Trả `None` nếu không tìm thấy element nào chứa giá
    trị này (vd. AI diễn giải lại giá trị thay vì trích nguyên văn từ trang)
    — khi đó đơn giản là không cache được, không phải lỗi."""
    target = _normalize(str(value))
    if not target:
        return None

    soup = BeautifulSoup(html, "html.parser")
    candidates = [tag for tag in soup.find_all(True) if target in _normalize(tag.get_text(" "))]
    if not candidates:
        return None

    best = min(candidates, key=lambda t: len(t.get_text()))
    return _build_selector(best)


def apply_selector(html: str, selector: str) -> Optional[str]:
    """Áp lại selector đã cache — trả text (đã strip) nếu tìm thấy element
    khớp và có nội dung, `None` nếu selector không còn khớp hoặc rỗng (coi là
    cache fail, để tầng gọi fallback sang AI)."""
    soup = BeautifulSoup(html, "html.parser")
    try:
        element = soup.select_one(selector)
    except Exception:
        # Selector cache cũ có thể không còn hợp lệ nếu logic sinh selector đổi
        # giữa các version — không để lỗi parse selector làm crash pipeline.
        logger.warning("Selector cache không hợp lệ để áp dụng: %r", selector)
        return None

    if element is None:
        return None
    text = _normalize(element.get_text(" "))
    return text or None


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _build_selector(element: Tag) -> str:
    """Xây selector dạng đường dẫn tuyệt đối từ gốc, mỗi bước dùng
    `tag:nth-of-type(n)` — luôn xác định duy nhất 1 element trong đúng cây
    HTML đó (miễn cấu trúc DOM không đổi giữa các lần cào).

    LƯU Ý: `BeautifulSoup` (đối tượng document gốc) tự nó cũng là 1 `Tag`
    (name="[document]") — phải dừng lại TRƯỚC nó, không đưa vào selector
    (soupsieve không parse được "[document]" như 1 tag name)."""
    parts: list[str] = []
    node: Optional[Tag] = element
    while isinstance(node, Tag) and node.name and node.name != "[document]":
        parent = node.parent
        if not isinstance(parent, Tag) or parent.name == "[document]":
            parts.append(node.name)
            break
        siblings_same_tag = parent.find_all(node.name, recursive=False)
        index = siblings_same_tag.index(node) + 1
        parts.append(f"{node.name}:nth-of-type({index})")
        node = parent
    parts.reverse()
    return " > ".join(parts)
