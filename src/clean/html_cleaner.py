"""Làm sạch HTML thô thành text dạng Markdown đơn giản, TRƯỚC khi đưa cho AI
(CLAUDE.md mục 2) — bỏ script/style/nav/footer..., giữ lại bảng/list dạng Markdown.

Bước này KHÔNG tìm structured data (JSON-LD/Open Graph) — việc đó để làm ở module
riêng khi bắt đầu nối AI client.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from bs4 import BeautifulSoup
from bs4.element import Tag

# Các tag không mang nội dung chính, luôn bỏ trước khi trích text.
_TAGS_TO_STRIP = (
    "script",
    "style",
    "noscript",
    "nav",
    "footer",
    "header",
    "aside",
    "iframe",
    "svg",
    "button",
    "input",
    "select",
    "textarea",
    "template",
)

_RENDERABLE_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6", "p", "ul", "ol", "table", "div", "span")


@dataclass(frozen=True)
class CleanedDocument:
    """Kết quả làm sạch 1 trang HTML."""

    title: Optional[str]
    markdown: str
    original_length: int
    cleaned_length: int


def clean_html(html: str) -> CleanedDocument:
    soup = BeautifulSoup(html, "html.parser")

    title = None
    if soup.title and soup.title.string:
        title = soup.title.string.strip() or None

    for tag_name in _TAGS_TO_STRIP:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    body = soup.body or soup
    markdown = _render_markdown(body)

    return CleanedDocument(
        title=title,
        markdown=markdown,
        original_length=len(html),
        cleaned_length=len(markdown),
    )


def _render_markdown(root: Tag) -> str:
    """Lấy nội dung theo `_RENDERABLE_TAGS` (bao gồm `div`/`span` — nhiều site
    hiện đại, vd. quotes.toscrape.com, đặt nội dung chính trong div/span chứ
    không dùng `<p>`). Trước đây chỉ nhận h1-h6/p/ul/ol/table: nếu trang có
    BẤT KỲ heading/p nào khác không liên quan (vd. link "Login"), toàn bộ nội
    dung div/span thật sự cần lấy bị bỏ sót hoàn toàn — AI nhận markdown gần
    như rỗng, luôn trả `None`/confidence 0 (xem docs/kien_audit/02)."""
    lines: list[str] = []

    for element in root.find_all(_RENDERABLE_TAGS, recursive=True):
        # Bỏ qua các element nằm lồng trong element đã render rồi (p, ul, ol,
        # table) — tránh lặp nội dung (vd. <span> trong <p> đã xử lý).
        if _has_ancestor_in(element, ("p", "ul", "ol", "table")):
            continue

        if element.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(element.name[1])
            text = _clean_text(element.get_text(" "))
            if text:
                lines.append(f"{'#' * level} {text}")
        elif element.name == "p":
            text = _clean_text(element.get_text(" "))
            if text:
                lines.append(text)
        elif element.name in ("ul", "ol"):
            list_md = _render_list(element)
            if list_md:
                lines.append(list_md)
        elif element.name == "table":
            table_md = _render_table(element)
            if table_md:
                lines.append(table_md)
        elif element.name in ("div", "span"):
            # Chỉ render "leaf" div/span — không chứa element renderable con
            # (h1-h6, p, ul, ol, table, div, span). Container div/span bị skip
            # để tránh trùng lặp — các element con sẽ được render riêng.
            if element.find(_RENDERABLE_TAGS, recursive=True):
                continue
            text = _clean_text(element.get_text(" "))
            if text:
                lines.append(text)

    if lines:
        return "\n\n".join(lines).strip()

    # Fallback: không có tag cấu trúc quen thuộc nào — lấy toàn bộ text thô.
    return _clean_text(root.get_text("\n"))


def _has_ancestor_in(element: Tag, tag_names: tuple[str, ...]) -> bool:
    for parent in element.parents:
        if getattr(parent, "name", None) in tag_names:
            return True
    return False


def _render_list(list_tag: Tag) -> str:
    items = []
    ordered = list_tag.name == "ol"
    for index, li in enumerate(list_tag.find_all("li", recursive=False), start=1):
        text = _clean_text(li.get_text(" "))
        if not text:
            continue
        prefix = f"{index}." if ordered else "-"
        items.append(f"{prefix} {text}")
    return "\n".join(items)


def _render_table(table_tag: Tag) -> str:
    rows = []
    for tr in table_tag.find_all("tr"):
        cells = tr.find_all(["th", "td"])
        if not cells:
            continue
        row_text = [_clean_text(cell.get_text(" ")) for cell in cells]
        rows.append(row_text)

    if not rows:
        return ""

    header, *body_rows = rows
    lines = ["| " + " | ".join(header) + " |"]
    lines.append("| " + " | ".join("---" for _ in header) + " |")
    for row in body_rows:
        # Đệm/cắt cho khớp số cột với header để bảng Markdown hợp lệ.
        padded = (row + [""] * len(header))[: len(header)]
        lines.append("| " + " | ".join(padded) + " |")
    return "\n".join(lines)


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
