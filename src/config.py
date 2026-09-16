"""Đọc cấu hình từ `.env` (xem `.env.example`) — KHÔNG hard-code giá trị thật
trong code, chỉ định nghĩa key + default an toàn cho dev."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    ai_base_url: str
    ai_api_key: str
    ai_model: str
    ai_timeout_seconds: float
    ai_confidence_threshold: float
    ai_debug_base_url: str
    ai_debug_api_key: str
    ai_debug_model: str
    ai_debug_timeout_seconds: float
    fetch_user_agent: str
    fetch_default_delay_seconds: float
    fetch_respect_robots_txt: bool
    db_path: str
    api_port: int
    log_level: str


def load_settings() -> Settings:
    """Load `.env` (nếu có) vào os.environ rồi đọc thành `Settings`.
    Biến môi trường hệ thống đã set trước đó không bị `.env` ghi đè
    (mặc định `override=False` của python-dotenv)."""
    load_dotenv()
    return Settings(
        ai_base_url=os.environ.get("AI_BASE_URL", ""),
        ai_api_key=os.environ.get("AI_API_KEY", ""),
        ai_model=os.environ.get("AI_MODEL", ""),
        ai_timeout_seconds=float(os.environ.get("AI_TIMEOUT_SECONDS", "30")),
        ai_confidence_threshold=float(os.environ.get("AI_CONFIDENCE_THRESHOLD", "0.7")),
        # Model "debug assistant" cho panel admin (gợi ý sửa lỗi, KHÔNG dùng
        # trong pipeline crawl/extract) — mặc định DÙNG CHUNG base_url/api_key
        # với AI_BASE_URL/AI_API_KEY (chỉ khác model), nhưng cho phép tách
        # riêng hoàn toàn nếu cần (đặt AI_DEBUG_BASE_URL/AI_DEBUG_API_KEY).
        ai_debug_base_url=os.environ.get("AI_DEBUG_BASE_URL") or os.environ.get("AI_BASE_URL", ""),
        ai_debug_api_key=os.environ.get("AI_DEBUG_API_KEY") or os.environ.get("AI_API_KEY", ""),
        ai_debug_model=os.environ.get("AI_DEBUG_MODEL") or os.environ.get("AI_MODEL", ""),
        ai_debug_timeout_seconds=float(
            os.environ.get("AI_DEBUG_TIMEOUT_SECONDS") or os.environ.get("AI_TIMEOUT_SECONDS", "30")
        ),
        fetch_user_agent=os.environ.get("FETCH_USER_AGENT", "web-extract-agent/0.1"),
        fetch_default_delay_seconds=float(os.environ.get("FETCH_DEFAULT_DELAY_SECONDS", "2")),
        fetch_respect_robots_txt=_parse_bool(os.environ.get("FETCH_RESPECT_ROBOTS_TXT", "true")),
        db_path=os.environ.get("DB_PATH", "./data/app.db"),
        api_port=int(os.environ.get("API_PORT", "8000")),
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
    )


def _parse_bool(raw: str) -> bool:
    return raw.strip().lower() in ("1", "true", "yes", "on")
