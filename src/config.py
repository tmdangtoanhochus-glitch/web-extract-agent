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
    db_backend: str
    db_path: str
    database_url: str
    api_port: int
    log_level: str
    admin_username: str
    admin_password: str
    runner_enabled: bool = False
    runner_ai_enabled: bool = False
    runner_ai_model: str = ""  # trống = dùng chung ai_model
    runner_db_path: str = "./data/runner.db"
    runner_database_url: str = ""
    runner_data_root: str = "./data/runner"


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
        # DB_BACKEND "sqlite" (mặc định, dev/MVP) hay "postgres" (production,
        # vd. GreenNode) — DATABASE_URL chỉ bắt buộc khi chọn "postgres" (xem
        # `_build_default_app()` trong `src/api/main.py`).
        db_backend=os.environ.get("DB_BACKEND", "sqlite"),
        db_path=os.environ.get("DB_PATH", "./data/app.db"),
        database_url=os.environ.get("DATABASE_URL", ""),
        api_port=int(os.environ.get("API_PORT", "8000")),
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
        # Basic Auth cho panel admin nội bộ (/admin/*, ui/pages/3_Admin.py)
        # — rỗng nếu chưa set trong .env (xem cảnh báo log lúc khởi động app ở
        # src/api/main.py: KHÔNG chạy production mà thiếu 2 biến này).
        admin_username=os.environ.get("ADMIN_USERNAME", ""),
        admin_password=os.environ.get("ADMIN_PASSWORD", ""),
        runner_enabled=_parse_bool(os.environ.get("RUNNER_ENABLED", "false")),
        runner_ai_enabled=_parse_bool(os.environ.get("RUNNER_AI_ENABLED", "false")),
        runner_ai_model=os.environ.get("RUNNER_AI_MODEL", ""),
        runner_db_path=os.environ.get("RUNNER_DB_PATH", "./data/runner.db"),
        runner_database_url=os.environ.get("RUNNER_DATABASE_URL", ""),
        runner_data_root=os.environ.get("RUNNER_DATA_ROOT", "./data/runner"),
    )


def _parse_bool(raw: str) -> bool:
    return raw.strip().lower() in ("1", "true", "yes", "on")
