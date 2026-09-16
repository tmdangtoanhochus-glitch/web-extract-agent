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
    "form",
    "iframe",
    "svg",
    "button",
    "input",
    "select",
    "textarea",
    "template",
)

_HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")
_LIST_TAGS = ("ul", "ol")
# Tag được coi là "block" khi quyết định đệ quy xuống tiếp hay dừng lại render
# nguyên khối làm 1 dòng — nếu 1 tag còn chứa 1 trong các tag này bên dưới,
# phải đệ quy xuống thay vì gộp cả khối cha thành 1 dòng duy nhất (tránh lẫn
# nội dung của nhiều mục lặp lại nằm cạnh nhau, vd. nhiều <div class="quote">
# liên tiếp trên 1 trang).
_BLOCK_DESCENDANT_TAGS = (
    ("div", "p", "section", "article", "li", "blockquote", "pre", "figure", "figcaption", "details", "summary", "dd", "dt")
    + _HEADING_TAGS
    + _LIST_TAGS
    + ("table",)
)


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
    """Đệ quy theo cấu trúc DOM thay vì chỉ gom `find_all` phẳng theo 1 danh
    sách tag cố định (h1-h6/p/ul/ol/table) — nhiều site hiện đại (vd.
    quotes.toscrape.com) đặt nội dung chính trong `<div>`/`<span>` chứ không
    dùng `<p>`. Cách cũ: nếu trang có BẤT KỲ heading/p/list/table nào ở chỗ
    khác (dù không liên quan, vd. link "Login" trong `<p>`), toàn bộ nội dung
    div/span thật sự cần lấy bị bỏ sót hoàn toàn vì không rơi vào danh sách
    tag đó — AI nhận markdown gần như rỗng, luôn trả `None`/confidence 0."""
    lines: list[str] = []
    _walk_blocks(root, lines)
    if lines:
        return "\n\n".join(lines).strip()
    # Fallback cùng cực: không có tag nào cả (vd. text thô không bọc tag) —
    # lấy toàn bộ text thô.
    return _clean_text(root.get_text(" "))


def _walk_blocks(node: Tag, lines: list[str]) -> None:
    for child in node.find_all(True, recursive=False):
        if not isinstance(child, Tag):
            continue

        if child.name in _HEADING_TAGS:
            text = _clean_text(child.get_text(" "))
            if text:
                level = int(child.name[1])
                lines.append(f"{'#' * level} {text}")
            continue

        if child.name in _LIST_TAGS:
            list_md = _render_list(child)
            if list_md:
                lines.append(list_md)
            continue

        if child.name == "table":
            table_md = _render_table(child)
            if table_md:
                lines.append(table_md)
            continue

        if child.find(_BLOCK_DESCENDANT_TAGS) is not None:
            # Còn tag con dạng block bên trong — đệ quy xuống thay vì gộp cả
            # khối cha thành 1 dòng, giữ đúng ranh giới từng mục (vd. tách
            # riêng từng <div class="quote"> thay vì dính chung 1 dòng).
            _walk_blocks(child, lines)
            continue

        # "Khối lá": không còn tag con dạng block nào (chỉ còn text hoặc tag
        # inline như span/small/a/strong...) — lấy nguyên text làm 1 dòng.
        text = _clean_text(child.get_text(" "))
        if text:
            lines.append(text)


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
