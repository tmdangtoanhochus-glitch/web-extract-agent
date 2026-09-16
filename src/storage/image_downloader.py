"""Tải file ảnh tài sản (vd. ảnh bất động sản) về local — bước RULE-BASED
chạy SAU khi AI/structured data đã trích được URL ảnh dưới dạng field bình
thường (CLAUDE.md mục 1: AI chỉ trích xuất giá trị, KHÔNG tự quyết định
nghiệp vụ "tải file về"). Người dùng khai báo tường minh field nào là ảnh cần
tải (`image_fields`, xem `pipeline.py`) — code KHÔNG tự đoán field nào là ảnh
theo đuôi URL, tránh hành vi ngầm định không rõ ràng.

An toàn: chỉ nhận URL http(s), bắt buộc Content-Type trả về đúng `image/*`,
giới hạn dung lượng — tránh tải nhầm file lớn/không phải ảnh do trang nguồn
trả sai hoặc field value không thực sự là URL ảnh.
"""
from __future__ import annotations

import mimetypes
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

from .file_writer import resolve_export_path

IMAGES_ROOT = Path("data/images")

_MAX_IMAGE_BYTES = 15 * 1024 * 1024  # 15MB — chặn tải nhầm file lớn ngoài dự tính
_ALLOWED_CONTENT_TYPE_PREFIX = "image/"
_URL_PATTERN = re.compile(r"^https?://", re.IGNORECASE)


@dataclass(frozen=True)
class ImageDownloadResult:
    success: bool
    local_path: Optional[str] = None  # đường dẫn tương đối trong images_root
    error: Optional[str] = None


def download_image(
    url: str,
    record_key: str,
    field_name: str,
    images_root: Path = IMAGES_ROOT,
    timeout_seconds: float = 20.0,
    client: Optional[httpx.Client] = None,
) -> ImageDownloadResult:
    """Tải 1 ảnh từ `url` về `images_root`. Lỗi KHÔNG raise — trả về
    `success=False` để tầng gọi (`pipeline.py`) tự quyết định (giữ nguyên giá
    trị URL gốc, ghi log cảnh báo, KHÔNG chặn cả record chỉ vì 1 ảnh tải lỗi
    — nhất quán với cách `ai_extract()` xử lý lỗi từng field)."""
    if not isinstance(url, str) or not _URL_PATTERN.match(url):
        return ImageDownloadResult(success=False, error=f"URL ảnh không hợp lệ (phải http/https): {url!r}")

    owns_client = client is None
    http_client = client or httpx.Client(timeout=timeout_seconds, follow_redirects=True)
    try:
        response = http_client.get(url)
        response.raise_for_status()

        content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
        if not content_type.startswith(_ALLOWED_CONTENT_TYPE_PREFIX):
            return ImageDownloadResult(
                success=False, error=f"Content-Type không phải ảnh: {content_type or '(không có)'}"
            )

        content = response.content
        if len(content) > _MAX_IMAGE_BYTES:
            return ImageDownloadResult(
                success=False, error=f"Ảnh vượt quá giới hạn {_MAX_IMAGE_BYTES} bytes"
            )

        ext = mimetypes.guess_extension(content_type) or ".jpg"
        if ext == ".jpe":
            ext = ".jpg"
        filename = f"{_safe_slug(record_key)}_{_safe_slug(field_name)}_{uuid.uuid4().hex[:8]}{ext}"

        images_root.mkdir(parents=True, exist_ok=True)
        dest_path = resolve_export_path(filename, exports_root=images_root)
        dest_path.write_bytes(content)

        return ImageDownloadResult(
            success=True, local_path=str(dest_path.relative_to(images_root.resolve()))
        )
    except httpx.HTTPError as exc:
        return ImageDownloadResult(success=False, error=f"Lỗi tải ảnh: {exc}")
    finally:
        if owns_client:
            http_client.close()


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-")
    return slug or "x"
