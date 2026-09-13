"""Panel admin nội bộ — "AI gợi ý sửa lỗi" cho scheduled_jobs bị lỗi.

**MÀN NỘI BỘ, KHÔNG dành cho người dùng cuối** — tách biệt hoàn toàn khỏi
luồng crawl/dataset chính (`src/api/main.py`), route dưới prefix `/admin`.
MVP hiện tại KHÔNG có authentication (chấp nhận được cho demo/hackathon theo
yêu cầu tính năng), nhưng route KHÔNG được lộ ra UI người dùng thường — chỉ
truy cập trực tiếp qua URL admin (Streamlit: `ui/pages/9_Admin_Debug.py`).

Ràng buộc bảo mật BẮT BUỘC (xem `src/ai/debug_assistant.py`):
- AI CHỈ trả về text gợi ý (chẩn đoán + patch đề xuất + rủi ro) — route này
  KHÔNG có endpoint "áp dụng patch", KHÔNG ghi file code, KHÔNG thực thi lệnh.
- Route CHỈ đọc code liên quan (`_read_related_code_snippets`) để đưa vào
  prompt — không bao giờ mở file ở chế độ ghi.
- Mọi lần gọi tính năng (thành công hay lỗi) đều ghi vào `audit_log`.
"""
from __future__ import annotations

import dataclasses
import logging
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, HTTPException

from ..ai.debug_assistant import DebugSuggestion, extract_related_files_from_traceback, suggest_fix
from ..storage.base import StorageEngine

logger = logging.getLogger(__name__)

_MAX_RELATED_CODE_CHARS = 20_000
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _read_related_code_snippets(traceback_text: str, repo_root: Path) -> str:
    """Đọc (CHỈ ĐỌC, không ghi) nội dung các file mã nguồn xuất hiện trong
    traceback — chỉ lấy file nằm TRONG repo (chặn traceback trỏ ra ngoài, vd.
    thư viện hệ thống) để không lộ nội dung ngoài phạm vi project. Giới hạn
    tổng độ dài để prompt không phình to quá mức."""
    snippets: list[str] = []
    total_len = 0
    for raw_path, _line_no in extract_related_files_from_traceback(traceback_text):
        try:
            candidate = (repo_root / raw_path).resolve()
        except (OSError, ValueError):
            continue
        if repo_root not in candidate.parents or not candidate.is_file():
            continue
        try:
            content = candidate.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Không đọc được file liên quan %s: %s", candidate, exc)
            continue

        remaining = _MAX_RELATED_CODE_CHARS - total_len
        if remaining <= 0:
            break
        snippet = content[:remaining]
        total_len += len(snippet)
        snippets.append(f"# --- {raw_path} ---\n{snippet}")

    return "\n\n".join(snippets) if snippets else "(không xác định được file liên quan từ traceback)"


def create_admin_router(
    storage: StorageEngine,
    ai_debug_base_url: str,
    ai_debug_api_key: str,
    ai_debug_model: str,
    ai_debug_timeout_seconds: float = 30.0,
    repo_root: Path = _REPO_ROOT,
    suggest_fix_fn: Callable[..., DebugSuggestion] = suggest_fix,
) -> APIRouter:
    """`suggest_fix_fn` cho phép inject test double — không cần gọi AI thật để
    test route (CLAUDE.md mục 6)."""
    router = APIRouter(prefix="/admin", tags=["admin-debug-internal"])

    @router.get("/errors")
    def list_errors() -> list[dict]:
        jobs = [job for job in storage.list_scheduled_jobs() if job.last_status == "error"]
        return [dataclasses.asdict(job) for job in jobs]

    @router.post("/errors/{job_id}/suggest-fix")
    def suggest_fix_for_job(job_id: str) -> dict:
        job = storage.get_scheduled_job(job_id)
        if job is None or job.last_status != "error":
            raise HTTPException(status_code=404, detail="Không tìm thấy job đang ở trạng thái lỗi với job_id này")

        traceback_text = job.last_error_traceback or "(không có traceback lưu lại)"
        related_code = _read_related_code_snippets(traceback_text, repo_root)
        context_note = (
            "Lỗi runtime trong pipeline crawl/AI-extract của ứng dụng Python FastAPI "
            f"(web-extract-agent). Job: url={job.url!r}, storage_mode={job.storage_mode!r}."
        )

        suggestion = suggest_fix_fn(
            traceback_text=traceback_text,
            related_code=related_code,
            context_note=context_note,
            base_url=ai_debug_base_url,
            api_key=ai_debug_api_key,
            model=ai_debug_model,
            timeout_seconds=ai_debug_timeout_seconds,
        )

        storage.add_audit_log(
            event_type="debug_suggest_fix",
            job_id=job_id,
            detail={"ai_call_success": suggestion.success, "error": suggestion.error},
        )

        if not suggestion.success:
            raise HTTPException(status_code=502, detail=suggestion.error or "Gọi AI thất bại")
        return {"content": suggestion.content}

    return router
