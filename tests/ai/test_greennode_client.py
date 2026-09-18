"""Test GreenNodeChatClient bằng httpx.MockTransport — không gọi endpoint thật.

`base_url` dùng trong test có hậu tố `/v1` và `model` có prefix nhà cung cấp
(`"openai/gpt-4o"`) đúng theo format thật đã xác nhận qua docs.greennode.ai —
xem docstring `src/ai/greennode_client.py`."""
import json

import httpx
import pytest

from src.ai.base import ExtractionResult
from src.ai.greennode_client import GreenNodeChatClient

_BASE_URL = "https://greennode.example/v1"


def _openai_response(content: str) -> dict:
    return {
        "id": "chatcmpl-test",
        "choices": [{"message": {"role": "assistant", "content": content}}],
    }


def _make_client(handler, base_url: str = _BASE_URL, **kwargs) -> GreenNodeChatClient:
    mock_client = httpx.Client(base_url=base_url, transport=httpx.MockTransport(handler))
    return GreenNodeChatClient(
        base_url=base_url,
        api_key="test-key",
        model="openai/gpt-4o",
        client=mock_client,
        **kwargs,
    )


def test_extract_parses_clean_json_response():
    """Response dạng 1 object đơn (không phải array) vẫn phải hoạt động được
    — backward compat, xem `ExtractionResult.fields` (trả record đầu tiên)."""
    ai_json = {
        "price": {"value": 75000000, "confidence": 0.95, "evidence": "giá 75.000.000 đồng"},
        "date": {"value": "2026-09-11", "confidence": 0.8, "evidence": "ngày 11/09/2026"},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_openai_response(json.dumps(ai_json)))

    client = _make_client(handler)
    result = client.extract("nội dung trang", {"price": "giá vàng", "date": "ngày cập nhật"})

    assert isinstance(result, ExtractionResult)
    assert result.success is True
    assert result.fields["price"].value == 75000000
    assert result.fields["price"].confidence == 0.95
    assert result.fields["price"].evidence == "giá 75.000.000 đồng"
    assert result.fields["date"].value == "2026-09-11"


def test_extract_parses_json_array_with_multiple_records():
    """Trang có nhiều bản ghi (vd. nhiều quote/sách) — AI trả về JSON array,
    mỗi phần tử 1 record — phải lưu được tất cả, không chỉ record đầu."""
    ai_json = [
        {"quote": {"value": "Quote A", "confidence": 0.9, "evidence": "e1"}},
        {"quote": {"value": "Quote B", "confidence": 0.85, "evidence": "e2"}},
        {"quote": {"value": "Quote C", "confidence": 0.8, "evidence": "e3"}},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_openai_response(json.dumps(ai_json)))

    client = _make_client(handler)
    result = client.extract("nội dung", {"quote": "câu trích dẫn"})

    assert result.success is True
    assert len(result.records) == 3
    assert [r["quote"].value for r in result.records] == ["Quote A", "Quote B", "Quote C"]
    assert result.fields["quote"].value == "Quote A"  # backward compat: record đầu


def test_extract_handles_json_wrapped_in_extra_text_or_markdown_fence():
    ai_json = {"price": {"value": 100, "confidence": 0.5, "evidence": "e"}}
    wrapped = f"Đây là kết quả:\n```json\n{json.dumps(ai_json)}\n```\nHết."

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_openai_response(wrapped))

    client = _make_client(handler)
    result = client.extract("nội dung", {"price": "giá"})

    assert result.success is True
    assert result.fields["price"].value == 100


def test_extract_repairs_truncated_json_array_response():
    """Response bị cắt giữa chừng do max_tokens (thường gặp khi trang có
    nhiều bản ghi) — phải repair được thay vì fail toàn bộ, giữ lại các
    record đã hoàn chỉnh trước điểm bị cắt."""
    truncated = (
        '[{"price": {"value": 1, "confidence": 0.9, "evidence": "e1"}}, '
        '{"price": {"value": 2, "confidence": 0.8, "evidence": "e2"}}, '
        '{"price": {"value": 3, "confidence": 0.7, "ev'  # bị cắt dở dang
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_openai_response(truncated))

    client = _make_client(handler)
    result = client.extract("nội dung", {"price": "giá"})

    assert result.success is True
    assert len(result.records) == 2
    assert [r["price"].value for r in result.records] == [1, 2]


def test_extract_missing_field_in_response_defaults_to_zero_confidence():
    ai_json = {"price": {"value": 100, "confidence": 0.5, "evidence": "e"}}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_openai_response(json.dumps(ai_json)))

    client = _make_client(handler)
    result = client.extract("nội dung", {"price": "giá", "unit": "đơn vị"})

    assert result.fields["unit"].value is None
    assert result.fields["unit"].confidence == 0.0


def test_extract_matches_field_name_case_insensitively():
    """Model trả key khác hoa/thường so với tên field yêu cầu (vd. "quote" thay
    vì "Quote") vẫn phải khớp được — tránh bug thật gặp phải: field bị rơi về
    None/confidence 0 dù model đã trích đúng giá trị, chỉ vì lệch cách viết hoa."""
    ai_json = {"quote": {"value": "Đời là bể khổ", "confidence": 0.9, "evidence": "e"}}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_openai_response(json.dumps(ai_json)))

    client = _make_client(handler)
    result = client.extract("nội dung", {"Quote": "câu trích dẫn"})

    assert result.fields["Quote"].value == "Đời là bể khổ"
    assert result.fields["Quote"].confidence == 0.9


def test_extract_clamps_out_of_range_confidence():
    ai_json = {"price": {"value": 100, "confidence": 1.7, "evidence": "e"}}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_openai_response(json.dumps(ai_json)))

    client = _make_client(handler)
    result = client.extract("nội dung", {"price": "giá"})

    assert result.fields["price"].confidence == 1.0


def test_extract_invalid_json_content_returns_failure_not_raise():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_openai_response("đây không phải JSON gì cả"))

    client = _make_client(handler)
    result = client.extract("nội dung", {"price": "giá"})

    assert result.success is False
    assert result.error is not None
    assert result.fields == {}


def test_extract_http_error_status_returns_failure_not_raise():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal error")

    client = _make_client(handler)
    result = client.extract("nội dung", {"price": "giá"})

    assert result.success is False
    assert "500" in result.error


def test_extract_network_error_is_caught_not_raised():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    client = _make_client(handler)
    result = client.extract("nội dung", {"price": "giá"})

    assert result.success is False
    assert "boom" in result.error


def test_extract_sends_authorization_header_and_model():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_openai_response(json.dumps({"price": {"value": 1, "confidence": 1, "evidence": "e"}})))

    client = _make_client(handler)
    client.extract("nội dung", {"price": "giá"})

    assert seen["auth"] == "Bearer test-key"
    assert seen["body"]["model"] == "openai/gpt-4o"
    assert seen["body"]["messages"][0]["role"] == "system"


def test_extract_posts_to_confirmed_chat_completions_path():
    """Endpoint thật đã xác nhận: POST {base_url}/chat/completions với base_url
    có hậu tố /v1 (docs.greennode.ai) — request phải đi tới đúng path này,
    không bị httpx cắt mất phần /v1 khi ghép base_url + path tương đối."""
    seen_url = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_url["value"] = str(request.url)
        return httpx.Response(200, json=_openai_response(json.dumps({"price": {"value": 1, "confidence": 1, "evidence": "e"}})))

    client = _make_client(handler)
    client.extract("nội dung", {"price": "giá"})

    assert seen_url["value"] == "https://greennode.example/v1/chat/completions"


def test_warns_when_base_url_missing_v1_suffix(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_openai_response("{}"))

    with caplog.at_level("WARNING"):
        _make_client(handler, base_url="https://greennode.example")

    assert any("/v1" in record.message for record in caplog.records)


def test_no_warning_when_base_url_has_v1_suffix(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_openai_response("{}"))

    with caplog.at_level("WARNING"):
        _make_client(handler)

    assert caplog.records == []


def test_extract_raises_value_error_for_empty_field_descriptions():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_openai_response("{}"))

    client = _make_client(handler)

    with pytest.raises(ValueError):
        client.extract("nội dung", {})
