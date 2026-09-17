"""AI "gợi ý sửa lỗi" cho panel admin nội bộ — TÁCH BIỆT HOÀN TOÀN khỏi
`AIClient` (`src/ai/base.py`) dùng trong pipeline crawl/extract (CLAUDE.md mục
1: AI trong pipeline CHỈ trích xuất, không tự quyết định nghiệp vụ). Đây là 1
công cụ hỗ trợ đọc/hiểu lỗi cho người vận hành (admin/dev) — ràng buộc bảo mật
BẮT BUỘC:
- KHÔNG tự động ghi/sửa file code trong project (module này chỉ ĐỌC file khi
  người gọi truyền `related_code` vào, tự nó không mở/ghi file nào cả).
- KHÔNG có quyền thực thi lệnh hệ thống hay gọi API ghi dữ liệu — chỉ gọi HTTP
  POST tới endpoint chat completions để LẤY VỀ text gợi ý.
- Kết quả trả về CHỈ là text thuần — tầng gọi (route admin) chỉ hiển thị lên
  UI để người dùng tự đọc/copy/áp dụng thủ công, KHÔNG có cơ chế "áp dụng".

Format request/response giống `src/ai/greennode_client.py` (endpoint OpenAI-
compatible đã xác nhận qua docs.greennode.ai) nhưng KHÔNG dùng chung class với
`GreenNodeChatClient` — prompt ở đây là hội thoại tự do (chẩn đoán + patch đề
xuất + rủi ro), không phải JSON có cấu trúc theo field_descriptions.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "Bạn là trợ lý gỡ lỗi cho 1 ứng dụng Python FastAPI (pipeline crawl dữ liệu web "
    "+ trích xuất dữ liệu bằng AI). Bạn CHỈ đọc traceback và đoạn code liên quan để "
    "CHẨN ĐOÁN nguyên nhân và GỢI Ý bản vá — bạn KHÔNG có khả năng chỉnh sửa file hay "
    "chạy lệnh gì cả, người vận hành sẽ tự đọc và áp dụng thủ công bên ngoài.\n\n"
    "Trả lời CHÍNH XÁC theo 3 phần sau, có tiêu đề rõ ràng:\n"
    "1. Chẩn đoán: nguyên nhân lỗi, ngắn gọn.\n"
    "2. Bản vá đề xuất: dạng diff (```diff ... ```) hoặc đoạn code cụ thể.\n"
    "3. Rủi ro/lưu ý: cần chú ý gì nếu áp dụng bản vá này."
)


@dataclass(frozen=True)
class DebugSuggestion:
    content: str
    success: bool = True
    error: Optional[str] = None


def suggest_fix(
    traceback_text: str,
    related_code: str,
    context_note: str,
    base_url: str,
    api_key: str,
    model: str,
    timeout_seconds: float = 30.0,
    client: Optional[httpx.Client] = None,
) -> DebugSuggestion:
    """Gọi AI (endpoint OpenAI-compatible qua GreenNode MaaS) với traceback +
    code liên quan, trả về gợi ý dạng TEXT THUẦN — không thực thi/ghi gì cả.
    KHÔNG raise cho lỗi mạng/response không hợp lệ, giống quy ước
    `AIClient.extract()` — trả `DebugSuggestion(success=False, error=...)`."""
    user_prompt = (
        f"Bối cảnh: {context_note}\n\n"
        f"Traceback đầy đủ:\n```\n{traceback_text}\n```\n\n"
        f"Code liên quan:\n```python\n{related_code}\n```"
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
    }

    owns_client = client is None
    http_client = client or httpx.Client(base_url=base_url, timeout=timeout_seconds)
    try:
        response = http_client.post(
            "/chat/completions", json=payload, headers={"Authorization": f"Bearer {api_key}"}
        )
        response.raise_for_status()
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        return DebugSuggestion(content=content, success=True)
    except httpx.HTTPError as exc:
        logger.warning("Gọi AI debug-assistant lỗi mạng/HTTP: %s", exc)
        return DebugSuggestion(content="", success=False, error=str(exc))
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        logger.warning("Response AI debug-assistant không hợp lệ: %s", exc)
        return DebugSuggestion(content="", success=False, error=f"invalid_ai_response: {exc}")
    finally:
        if owns_client:
            http_client.close()


_TRACEBACK_FILE_LINE_RE = re.compile(r'File "([^"]+)", line (\d+)')


def extract_related_files_from_traceback(traceback_text: str) -> list[tuple[str, int]]:
    """Parse traceback lấy ra (đường dẫn file, số dòng) — CHỈ đọc text, không
    mở file nào ở đây. Trùng lặp được loại bỏ, giữ nguyên thứ tự xuất hiện."""
    seen: dict[str, int] = {}
    for path, line_no in _TRACEBACK_FILE_LINE_RE.findall(traceback_text):
        seen.setdefault(path, int(line_no))
    return list(seen.items())
