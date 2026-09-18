"""Phản hồi/báo lỗi tự do của người dùng trên MỌI màn hình, AI_DEBUG phân loại.

Luồng (rule-based ở đây, AI chỉ ĐƯA RA nhận định — CLAUDE.md mục 1):
1. Lưu phản hồi (đã che token/cookie) vào audit_log `user_feedback`.
2. `triage_feedback` (AI_DEBUG) trả `is_bug` + `confidence` + `answer`.
3. Nếu AI kết luận KHÔNG phải lỗi với confidence >= ngưỡng -> trả lời thẳng người
   dùng (status `answered`).
4. Còn lại (là lỗi / confidence thấp / AI hỏng) -> `escalated`: gom trace (audit
   theo request_id, các lần crawl lỗi gần nhất, chẩn đoán AI) lưu cho admin.
"""
from __future__ import annotations

import re
import time
from collections import deque
from threading import Lock
from typing import Callable, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ..ai.feedback_triage import TriageResult, triage_feedback

DEFAULT_CONFIDENCE_THRESHOLD = 0.75
_RATE_LIMIT = (20, 60.0)  # tối đa 20 phản hồi / 60 giây toàn hệ thống (chặn spam tốn AI)

_SECRET_PATTERNS = [
    re.compile(r"(?i)(cookie|authorization|set-cookie|bearer|password|passwd|token|api[_-]?key)\s*[:=]\s*\S+"),
    re.compile(r"[A-Za-z0-9_\-\.]{32,}"),
]


def redact(text: str) -> str:
    """Che cookie/token/mật khẩu người dùng lỡ dán vào — không gửi cho AI, không lưu."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    screen: str = Field(min_length=1, max_length=60)
    message: str = Field(min_length=5, max_length=2000)
    request_id: Optional[UUID] = None


def create_feedback_router(
    storage,
    ai_debug_base_url: str,
    ai_debug_api_key: str,
    ai_debug_model: str,
    ai_debug_timeout_seconds: float = 30.0,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    triage_fn: Callable[..., TriageResult] = triage_feedback,
) -> APIRouter:
    router = APIRouter()
    hits: deque = deque()
    lock = Lock()

    def _rate_limited() -> bool:
        limit, window = _RATE_LIMIT
        now = time.monotonic()
        with lock:
            while hits and now - hits[0] > window:
                hits.popleft()
            if len(hits) >= limit:
                return True
            hits.append(now)
            return False

    def _build_trace(request_id: Optional[str]) -> dict:
        linked = []
        if request_id:
            linked = [
                {"event_type": e.event_type, "detail": e.detail}
                for e in storage.list_audit_log(job_id=request_id, limit=20)
            ]
        recent_failures = [
            {"job_id": e.job_id, "detail": e.detail}
            for e in storage.list_audit_log(limit=50)
            if e.event_type == "crawl_failed"
        ][:5]
        return {"linked_audit": linked, "recent_crawl_failures": recent_failures}

    @router.post("/feedback", status_code=201)
    def submit_feedback(req: FeedbackRequest) -> dict:
        if _rate_limited():
            raise HTTPException(429, "Đang nhận quá nhiều phản hồi, vui lòng thử lại sau ít phút.")
        message = redact(req.message)
        request_id = str(req.request_id) if req.request_id else None
        saved = storage.add_audit_log(
            "user_feedback", job_id=request_id,
            detail={"screen": req.screen, "message": message, "client_claim_unverified": True},
        )
        trace = _build_trace(request_id)
        triage = triage_fn(
            message=message, screen=req.screen,
            context_note="Ngữ cảnh gần nhất (không đáng tin tuyệt đối): "
            f"{len(trace['recent_crawl_failures'])} lần crawl lỗi gần đây.",
            base_url=ai_debug_base_url, api_key=ai_debug_api_key, model=ai_debug_model,
            timeout_seconds=ai_debug_timeout_seconds,
        )
        answered = (
            triage.success and triage.is_bug is False
            and triage.confidence >= confidence_threshold and bool(triage.answer)
        )
        if answered:
            storage.add_audit_log(
                "user_feedback_answered", job_id=saved.id,
                detail={"confidence": triage.confidence, "answer": triage.answer},
            )
            return {"feedback_id": saved.id, "status": "answered", "answer": triage.answer}
        storage.add_audit_log(
            "user_feedback_escalated", job_id=saved.id,
            detail={
                "screen": req.screen, "message": message,
                "ai_success": triage.success, "ai_error": triage.error,
                "ai_is_bug": triage.is_bug, "ai_confidence": triage.confidence,
                "ai_diagnosis": triage.diagnosis, "trace": trace,
            },
        )
        return {
            "feedback_id": saved.id, "status": "escalated",
            "answer": "Cảm ơn bạn. Chúng tôi đã chuyển báo lỗi cho admin để kiểm tra "
            f"(mã: {saved.id}).",
        }

    return router
