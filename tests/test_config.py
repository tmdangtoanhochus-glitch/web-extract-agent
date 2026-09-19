"""Test load_settings() — chủ yếu verify fallback của AI_DEBUG_* (model debug
cho panel admin, mặc định dùng chung AI_BASE_URL/AI_API_KEY, tách được riêng
khi cần — xem CLAUDE.md/README mục AI runtime)."""
import pytest

from src.config import load_settings


@pytest.fixture(autouse=True)
def _isolate_from_real_dotenv(monkeypatch):
    """Cô lập test khỏi file `.env` THẬT của máy dev — `load_settings()` tự gọi
    `load_dotenv()`, nên nếu `.env` thật có set `AI_DEBUG_*`/`AI_*`, giá trị
    thật sẽ đè lên trạng thái monkeypatch.delenv() giả lập "chưa set" (dotenv
    tự điền lại từ file vì `override=False` chỉ chặn ghi đè biến ĐANG có
    trong os.environ, không chặn việc điền biến vừa bị xoá). Test fallback ở
    file này chỉ nên phụ thuộc monkeypatch, không phụ thuộc `.env` thật."""
    monkeypatch.setattr("src.config.load_dotenv", lambda *args, **kwargs: False)


def test_ai_debug_settings_fall_back_to_shared_ai_settings_when_unset(monkeypatch):
    monkeypatch.delenv("AI_DEBUG_BASE_URL", raising=False)
    monkeypatch.delenv("AI_DEBUG_API_KEY", raising=False)
    monkeypatch.delenv("AI_DEBUG_MODEL", raising=False)
    monkeypatch.setenv("AI_BASE_URL", "https://shared.example/v1")
    monkeypatch.setenv("AI_API_KEY", "shared-key")
    monkeypatch.setenv("AI_MODEL", "openai/gpt-4o")

    settings = load_settings()

    assert settings.ai_debug_base_url == "https://shared.example/v1"
    assert settings.ai_debug_api_key == "shared-key"
    assert settings.ai_debug_model == "openai/gpt-4o"


def test_ai_debug_settings_can_be_overridden_independently(monkeypatch):
    monkeypatch.setenv("AI_BASE_URL", "https://shared.example/v1")
    monkeypatch.setenv("AI_API_KEY", "shared-key")
    monkeypatch.setenv("AI_MODEL", "openai/gpt-4o")
    monkeypatch.setenv("AI_DEBUG_BASE_URL", "https://debug-only.example/v1")
    monkeypatch.setenv("AI_DEBUG_API_KEY", "debug-key")
    monkeypatch.setenv("AI_DEBUG_MODEL", "zhipuai/glm-4.6")

    settings = load_settings()

    assert settings.ai_debug_base_url == "https://debug-only.example/v1"
    assert settings.ai_debug_api_key == "debug-key"
    assert settings.ai_debug_model == "zhipuai/glm-4.6"
    # Cấu hình extract chính không bị ảnh hưởng bởi biến debug riêng.
    assert settings.ai_base_url == "https://shared.example/v1"
    assert settings.ai_model == "openai/gpt-4o"


def test_ai_debug_timeout_falls_back_to_shared_ai_timeout_when_unset(monkeypatch):
    monkeypatch.delenv("AI_DEBUG_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setenv("AI_TIMEOUT_SECONDS", "45")

    settings = load_settings()

    assert settings.ai_debug_timeout_seconds == 45.0


def test_ai_debug_timeout_can_be_overridden_independently(monkeypatch):
    monkeypatch.setenv("AI_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("AI_DEBUG_TIMEOUT_SECONDS", "90")

    settings = load_settings()

    assert settings.ai_debug_timeout_seconds == 90.0
    assert settings.ai_timeout_seconds == 45.0


def test_ai_debug_timeout_defaults_to_30_when_nothing_set(monkeypatch):
    monkeypatch.delenv("AI_DEBUG_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("AI_TIMEOUT_SECONDS", raising=False)

    settings = load_settings()

    assert settings.ai_debug_timeout_seconds == 30.0


def test_runner_ai_model_is_optional_and_independent_of_ai_model(monkeypatch):
    monkeypatch.setenv("AI_MODEL", "qwen-flash")
    monkeypatch.delenv("RUNNER_AI_MODEL", raising=False)
    assert load_settings().runner_ai_model == ""  # trống = dùng chung AI_MODEL (xem src/api/main.py)

    monkeypatch.setenv("RUNNER_AI_MODEL", "glm-x")
    settings = load_settings()
    assert settings.runner_ai_model == "glm-x" and settings.ai_model == "qwen-flash"
