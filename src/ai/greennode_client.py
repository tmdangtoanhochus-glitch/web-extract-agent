"""AI client thật — gọi endpoint Qwen/GLM do GreenNode cấp qua MaaS (CLAUDE.md mục B).

Format đã XÁC NHẬN qua docs.greennode.ai (mục "Model as a Service" / "Kết nối
OpenAI-compatible với GreenNode MaaS"), không phải giả định:
- Base URL thật: `https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1` — LUÔN có
  hậu tố `/v1`, client OpenAI-compatible trỏ vào URL này rồi tự nối thêm path.
- Endpoint: `POST {base_url}/chat/completions`, header `Authorization: Bearer
  <api-key>` — KHÔNG cần header nào khác cho chat completions (header
  `portal-user-id` chỉ dùng cho API OCR riêng, không áp dụng ở đây).
- Request/response body đúng chuẩn OpenAI chat completions
  (`{"model", "messages", ...}` → `choices[0].message.content`).
- QUAN TRỌNG: `model` phải là ID có prefix nhà cung cấp lấy từ catalog GreenNode
  (VD xác nhận được: `"openai/gpt-4o"`), KHÔNG phải tên hiển thị (VD sai:
  "Qwen 3.6 Flash", "qwen-3.6-flash") — lấy ID thật qua `GET {base_url}/models`
  hoặc trang API Keys/Model Catalog trên console, điền vào `AI_MODEL` trong
  `.env`. Code ở đây KHÔNG hard-code hay validate cứng chuỗi model, chỉ truyền
  thẳng giá trị từ `.env` xuống — người vận hành chịu trách nhiệm điền đúng ID.

Dùng endpoint OpenAI-compatible `/chat/completions` (không dùng SDK `openai` để
tránh thêm dependency ngoài tech stack đã chốt — gọi thẳng qua `httpx`, vốn đã
có sẵn trong requirements.txt cho tầng fetch).

Endpoint thật + model name lấy từ `.env` (`AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL`)
— KHÔNG hard-code giá trị thật trong code.

Trang có thể chứa NHIỀU bản ghi giống nhau (vd. 10 quote, 20 sách trên 1 trang
danh sách) — prompt yêu cầu AI trả về JSON ARRAY (mỗi phần tử là 1 bản ghi),
không phải 1 object duy nhất như trước (xem docs/kien_audit/03).
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
    "Trang có thể chứa 1 hoặc nhiều bản ghi giống nhau (vd. nhiều sách, nhiều "
    "quote). Với mỗi bản ghi và mỗi field, trả về: value (giá trị trích được, "
    "hoặc null nếu không tìm thấy), confidence (số 0-1 thể hiện độ chắc chắn), "
    "evidence (câu/đoạn gốc trong nội dung chứa giá trị đó, hoặc null). "
    "Trả về 1 JSON array, mỗi phần tử là 1 object với key là tên field, value "
    "là object có dạng {\"value\": ..., \"confidence\": ..., \"evidence\": ...}. "
    "Nếu trang chỉ có 1 bản ghi, trả về array 1 phần tử. "
    "CHỈ trả lời bằng JSON array, không kèm giải thích, không dùng markdown code fence."
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
        max_tokens: int = 16384,
        client: Optional[httpx.Client] = None,
    ) -> None:
        _warn_if_base_url_missing_v1_suffix(base_url)
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
            parsed = _parse_json(content)
            records = _to_records(parsed, field_descriptions)
            return ExtractionResult(records=records, raw_response=content, success=True)
        except httpx.HTTPError as exc:
            logger.warning("Gọi AI extract lỗi mạng/HTTP: %s", exc)
            return ExtractionResult(success=False, error=str(exc))
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            logger.warning("Response AI không hợp lệ: %s", exc)
            return ExtractionResult(success=False, error=f"invalid_ai_response: {exc}")
        finally:
            if owns_client:
                client.close()


def _warn_if_base_url_missing_v1_suffix(base_url: str) -> None:
    """GreenNode MaaS yêu cầu base URL kết thúc bằng `/v1` (đã xác nhận qua
    docs.greennode.ai) — thiếu hậu tố này khiến mọi request 404 ở runtime mà
    lỗi rất khó đoán ra nguyên nhân. Chỉ cảnh báo (không raise) vì có thể đang
    trỏ tới 1 proxy/gateway khác có quy ước path riêng."""
    if base_url and not base_url.rstrip("/").endswith("/v1"):
        logger.warning(
            "AI_BASE_URL (%s) không kết thúc bằng '/v1' — endpoint GreenNode MaaS "
            "thật yêu cầu dạng 'https://<host>/v1'. Kiểm tra lại nếu request bị 404.",
            base_url,
        )


def _build_user_prompt(markdown: str, field_descriptions: dict[str, str]) -> str:
    fields_desc = "\n".join(f"- {name}: {desc}" for name, desc in field_descriptions.items())
    _MAX_MD = 8000
    if len(markdown) > _MAX_MD:
        markdown = markdown[:_MAX_MD] + "\n\n[... nội dung còn lại bị cắt để giới hạn thời gian xử lý]"
    return (
        f"Các field cần trích xuất:\n{fields_desc}\n\n"
        f"Nội dung trang (đã làm sạch, dạng Markdown):\n\"\"\"\n{markdown}\n\"\"\"\n\n"
        f"Trả về 1 JSON array, mỗi phần tử là 1 object với key là tên field, "
        f"value là object có dạng {{\"value\": ..., \"confidence\": ..., "
        f"\"evidence\": ...}}. Trang có thể có NHIỀU bảng cùng cấu trúc — "
        f"trích xuất TẤT CẢ bản ghi từ TẤT CẢ bảng, không bỏ sót. "
        f"Tối đa 100 bản ghi."
    )


def _parse_json(content: str) -> Any:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Fallback 1: model trả thêm text/markdown fence — lấy đoạn JSON đầu tiên.
    match = re.search(r"[\[{].*[\]}]", content, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # Fallback 2: response bị truncate (max_tokens cắt giữa chừng) —
    # tìm record hoàn chỉnh cuối cùng, cắt bỏ phần dở dang, đóng array.
    repaired = _repair_truncated_json(content)
    if repaired is not None:
        logger.warning("AI response bị truncate — đã repair (%d -> %d chars).",
                        len(content), len(repaired))
        return json.loads(repaired)

    raise ValueError(f"không parse được JSON từ AI response ({len(content)} chars)")


def _repair_truncated_json(content: str) -> Optional[str]:
    """Repair JSON array bị truncate bằng cách scan tracking string state,
    tìm } đóng record hoàn chỉnh cuối cùng (không nằm trong string)."""
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    if not text.startswith("["):
        return None

    in_string = False
    escape = False
    depth = 0
    last_close = -1
    for i, ch in enumerate(text):
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{" or ch == "[":
            depth += 1
        elif ch == "}" or ch == "]":
            depth -= 1
            if ch == "}" and depth == 1:
                last_close = i

    if last_close <= 0:
        return None
    truncated = text[:last_close + 1].rstrip().rstrip(",")
    return truncated + "]"


def _to_records(
    parsed: Any, field_descriptions: dict[str, str]
) -> list[dict[str, FieldExtraction]]:
    # AI trả về array → mỗi phần tử là 1 record.
    if isinstance(parsed, list):
        items = parsed
    elif isinstance(parsed, dict):
        # Backward compat: AI trả về single object → wrap thành array 1 phần tử.
        items = [parsed]
    else:
        raise ValueError(f"response AI không phải JSON array/object: {parsed!r}")

    records: list[dict[str, FieldExtraction]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        records.append(_to_field_extractions(item, field_descriptions))
    return records


def _to_field_extractions(
    item: dict[str, Any], field_descriptions: dict[str, str]
) -> dict[str, FieldExtraction]:
    # Model đôi khi trả key khác hoa/thường hoặc thừa khoảng trắng so với tên
    # field yêu cầu (vd. "quote" thay vì "Quote") dù đã trích đúng giá trị —
    # so khớp không phân biệt hoa/thường thay vì exact-match để field không bị
    # rơi về None/confidence 0 chỉ vì lệch cách viết hoa.
    normalized_item = {str(key).strip().lower(): value for key, value in item.items()}

    fields: dict[str, FieldExtraction] = {}
    unmatched: list[str] = []
    for name in field_descriptions:
        entry = normalized_item.get(name.strip().lower())
        if not isinstance(entry, dict):
            fields[name] = FieldExtraction(value=None, confidence=0.0, evidence=None)
            unmatched.append(name)
            continue
        fields[name] = FieldExtraction(
            value=entry.get("value"),
            confidence=_safe_confidence(entry.get("confidence")),
            evidence=entry.get("evidence"),
        )
    if unmatched:
        logger.warning(
            "AI response không có field %s (đã so khớp không phân biệt hoa/thường) "
            "— response thật trả về key: %s", unmatched, list(item.keys()),
        )
    return fields


def _safe_confidence(raw: Any) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.0
    return min(max(value, 0.0), 1.0)
