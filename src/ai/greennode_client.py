"""AI client thật — gọi endpoint Qwen/GLM do GreenNode cấp (CLAUDE.md mục B).

Dùng endpoint OpenAI-compatible `/v1/chat/completions` (không dùng SDK `openai`
để tránh thêm dependency ngoài tech stack đã chốt — gọi thẳng qua `httpx`, vốn
đã có sẵn trong requirements.txt cho tầng fetch).

Endpoint thật + model name lấy từ `.env` (`AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL`)
— KHÔNG hard-code giá trị thật trong code.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

import httpx

from .base import AIClient, ExtractionResult, FieldExtraction

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "Bạn là hệ thống trích xuất dữ liệu có cấu trúc từ nội dung trang web đã "
    "được làm sạch. Chỉ trích xuất giá trị THỰC SỰ xuất hiện trong nội dung "
    "được cung cấp, KHÔNG suy diễn hay bịa thông tin không có trong text. "
    "Với mỗi field được yêu cầu, trả về: value (giá trị trích được, hoặc null "
    "nếu không tìm thấy), confidence (số 0-1 thể hiện độ chắc chắn), evidence "
    "(câu/đoạn gốc trong nội dung chứa giá trị đó, hoặc null nếu value là null). "
    "CHỈ trả lời bằng 1 JSON object duy nhất, không kèm giải thích, không dùng "
    "markdown code fence."
)


class GreenNodeChatClient(AIClient):
    """`client` cho phép inject 1 `httpx.Client` có sẵn (vd. `httpx.MockTransport`
    khi test) — theo adapter/test-double pattern ở CLAUDE.md mục 6."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 30.0,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        client: Optional[httpx.Client] = None,
    ) -> None:
        self._base_url = base_url
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._injected_client = client

    def extract(self, markdown: str, field_descriptions: dict[str, str]) -> ExtractionResult:
        if not field_descriptions:
            raise ValueError("field_descriptions không được rỗng")

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(markdown, field_descriptions)},
            ],
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
        }

        owns_client = self._injected_client is None
        client = self._injected_client or httpx.Client(
            base_url=self._base_url, timeout=self._timeout_seconds
        )
        try:
            response = client.post(
                "/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            response.raise_for_status()
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            parsed = _parse_json_object(content)
            fields = _to_field_extractions(parsed, field_descriptions)
            return ExtractionResult(fields=fields, raw_response=content, success=True)
        except httpx.HTTPError as exc:
            logger.warning("Gọi AI extract lỗi mạng/HTTP: %s", exc)
            return ExtractionResult(success=False, error=str(exc))
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            logger.warning("Response AI không hợp lệ: %s", exc)
            return ExtractionResult(success=False, error=f"invalid_ai_response: {exc}")
        finally:
            if owns_client:
                client.close()


def _build_user_prompt(markdown: str, field_descriptions: dict[str, str]) -> str:
    fields_desc = "\n".join(f"- {name}: {desc}" for name, desc in field_descriptions.items())
    return (
        f"Các field cần trích xuất:\n{fields_desc}\n\n"
        f"Nội dung trang (đã làm sạch, dạng Markdown):\n\"\"\"\n{markdown}\n\"\"\"\n\n"
        f"Trả về đúng 1 JSON object với key là tên field, value là object có "
        f"dạng {{\"value\": ..., \"confidence\": ..., \"evidence\": ...}}."
    )


def _parse_json_object(content: str) -> dict[str, Any]:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Fallback: model có thể trả thêm text/markdown fence quanh JSON — lấy
    # đoạn từ dấu { đầu tiên đến } cuối cùng rồi thử parse lại.
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        raise ValueError(f"không tìm thấy JSON object trong response: {content!r}")
    return json.loads(match.group(0))


def _to_field_extractions(
    parsed: Any, field_descriptions: dict[str, str]
) -> dict[str, FieldExtraction]:
    if not isinstance(parsed, dict):
        raise ValueError(f"response AI không phải JSON object: {parsed!r}")

    fields: dict[str, FieldExtraction] = {}
    for name in field_descriptions:
        entry = parsed.get(name)
        if not isinstance(entry, dict):
            fields[name] = FieldExtraction(value=None, confidence=0.0, evidence=None)
            continue
        fields[name] = FieldExtraction(
            value=entry.get("value"),
            confidence=_safe_confidence(entry.get("confidence")),
            evidence=entry.get("evidence"),
        )
    return fields


def _safe_confidence(raw: Any) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.0
    return min(max(value, 0.0), 1.0)
