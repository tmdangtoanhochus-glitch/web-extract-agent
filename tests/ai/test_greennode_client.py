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


def test_transient_error_is_retried_once_then_succeeds():
    """Timeout/lỗi mạng thường là tải đột biến tạm thời — lượt gọi đầu lỗi,
    lượt thử lại (2) phải thành công mà KHÔNG coi cả extract() là lỗi."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ReadTimeout("boom", request=request)
        return httpx.Response(200, json=_openai_response(
            json.dumps({"price": {"value": 100, "confidence": 0.9, "evidence": "e"}})))

    client = _make_client(handler)
    result = client.extract("nội dung", {"price": "giá"})

    assert len(calls) == 2
    assert result.success is True
    assert result.fields["price"].value == 100
    assert result.warning is None  # thành công ngay ở lần thử lại -> không cần cảnh báo


def test_single_chunk_fails_even_after_retry_returns_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("boom", request=request)

    client = _make_client(handler)
    result = client.extract("nội dung", {"price": "giá"})

    assert result.success is False
    assert "boom" in result.error


def test_retry_uses_a_longer_timeout_than_the_first_attempt():
    seen_timeouts = []

    class RecordingClient(httpx.Client):
        def post(self, *args, **kwargs):
            seen_timeouts.append(self.timeout)
            raise httpx.ReadTimeout("boom", request=httpx.Request("POST", _BASE_URL))

    # _make_client injects 1 client cố định (không đổi timeout được qua tham số
    # `timeout` của _extract_chunk) — dựng trực tiếp GreenNodeChatClient KHÔNG
    # inject client để mỗi lần gọi tự tạo httpx.Client mới với timeout tương ứng.
    client = GreenNodeChatClient(
        base_url=_BASE_URL, api_key="k", model="openai/gpt-4o", timeout_seconds=30.0,
    )
    first = client._timeout_for("x" * 8000, attempt=1)
    second = client._timeout_for("x" * 8000, attempt=2)
    assert second > first
    assert first >= 30.0  # timeout cấu hình luôn là mức sàn, không bị rút ngắn


def test_timeout_floor_never_goes_below_configured_value_for_a_small_chunk():
    client = GreenNodeChatClient(base_url=_BASE_URL, api_key="k", model="openai/gpt-4o", timeout_seconds=30.0)
    timeout = client._timeout_for("ngắn", attempt=1)
    assert 30.0 <= timeout < 31.0  # gần như bằng mức sàn cho đoạn rất ngắn


def test_timeout_for_a_full_chunk_matches_thoi_gian_do_thuc_te_voi_qwen():
    """Hiệu chỉnh theo số liệu đo thật (xem docstring `_timeout_for`): 1 đoạn đầy
    8000 ký tự (~60 bản ghi) cần ~101.5s thực tế — timeout phải đủ lớn hơn con số
    đó với biên an toàn, không chỉ nhỉnh hơn timeout cấu hình 1 chút."""
    client = GreenNodeChatClient(base_url=_BASE_URL, api_key="k", model="openai/gpt-4o", timeout_seconds=30.0)
    timeout = client._timeout_for("x" * 8000, attempt=1)
    assert timeout >= 101.5 * 1.1  # ít nhất hơn 10% so với thời gian đo thật


def test_one_bad_chunk_no_longer_kills_the_whole_page_even_when_it_is_the_first_chunk():
    """Trước đây: đoạn ĐẦU TIÊN lỗi -> cả trang extract_failed dù các đoạn sau ổn.
    Giờ: bỏ qua đoạn lỗi (đã thử lại), giữ bản ghi các đoạn còn lại, coi là
    thành công một phần (có warning)."""
    seen_prompts = []

    def handler(request: httpx.Request) -> httpx.Response:
        content = json.loads(request.content)["messages"][1]["content"]
        seen_prompts.append(content)
        if "dòng 0 " in content:  # đoạn đầu luôn lỗi, kể cả sau khi thử lại
            raise httpx.ReadTimeout("boom", request=request)
        n = len(seen_prompts)
        return httpx.Response(200, json=_openai_response(
            json.dumps([{"a": {"value": f"r{n}", "confidence": 0.9, "evidence": "e"}}])))

    client = _make_client(handler)
    markdown = "\n".join(f"dòng {i} " + "x" * 90 for i in range(200))  # ~20k ký tự, chia >= 3 đoạn
    result = client.extract(markdown, {"a": "mô tả"})

    assert result.success is True
    assert len(result.records) >= 1  # các đoạn sau đoạn 1 vẫn được giữ lại
    assert result.warning is not None
    assert "đoạn 1" in result.warning and "boom" in result.warning


def test_warning_is_none_when_every_chunk_succeeds():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_openai_response(
            json.dumps({"price": {"value": 1, "confidence": 1, "evidence": "e"}})))

    client = _make_client(handler)
    result = client.extract("nội dung ngắn", {"price": "giá"})

    assert result.success is True
    assert result.warning is None


def test_page_beyond_max_chunks_reports_truncation_warning_instead_of_silent_drop():
    def handler(request: httpx.Request) -> httpx.Response:
        n = len([1 for _ in [request]]) or 1
        return httpx.Response(200, json=_openai_response(
            json.dumps([{"a": {"value": "r", "confidence": 0.9, "evidence": "e"}}])))

    client = _make_client(handler)
    # 7 đoạn ~8000 ký tự (vượt _MAX_CHUNKS=6) để kích hoạt truncation.
    markdown = "\n".join(f"dòng {i} " + "x" * 90 for i in range(900))
    result = client.extract(markdown, {"a": "mô tả"})

    assert result.success is True
    assert result.warning is not None
    assert "quá dài" in result.warning and "6 đoạn đầu" in result.warning


def test_long_markdown_is_chunked_not_truncated():
    """Trang dài được chia đoạn, bản ghi ở phần đuôi không bị mất."""
    seen_prompts = []

    def handler(request):
        seen_prompts.append(json.loads(request.content)["messages"][1]["content"])
        n = len(seen_prompts)
        return httpx.Response(200, json=_openai_response(
            json.dumps([{"a": {"value": f"r{n}", "confidence": 0.9, "evidence": "e"}}])))

    client = _make_client(handler)
    markdown = "\n".join(f"dòng {i} " + "x" * 90 for i in range(200))  # ~20k ký tự
    result = client.extract(markdown, {"a": "mô tả"})

    assert result.success is True
    assert len(seen_prompts) >= 3
    assert "dòng 199" in seen_prompts[-1]
    assert [r["a"].value for r in result.records] == [f"r{i}" for i in range(1, len(seen_prompts) + 1)]
