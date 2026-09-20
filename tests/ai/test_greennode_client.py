"""Test GreenNodeChatClient bằng httpx.MockTransport — không gọi endpoint thật.

`base_url` dùng trong test có hậu tố `/v1` và `model` có prefix nhà cung cấp
(`"openai/gpt-4o"`) đúng theo format thật đã xác nhận qua docs.greennode.ai —
xem docstring `src/ai/greennode_client.py`."""
import json
import threading
import time

import httpx
import pytest

from src.ai.base import ExtractionResult
from src.ai.greennode_client import GreenNodeChatClient, _split_markdown

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


def _long_markdown(num_lines: int = 200) -> str:
    return "\n".join(f"dòng {i} " + "x" * 90 for i in range(num_lines))  # ~20k ký tự, chia >= 3 đoạn


def test_parallel_true_runs_chunks_concurrently_not_sequentially():
    """`parallel=True` (người dùng tự tick 'Nhanh') phải THỰC SỰ chạy đồng thời —
    tổng thời gian phải gần bằng đoạn chậm nhất, không phải tổng các đoạn cộng lại."""
    SLEEP = 0.25

    def handler(request: httpx.Request) -> httpx.Response:
        time.sleep(SLEEP)
        return httpx.Response(200, json=_openai_response(
            json.dumps({"a": {"value": "r", "confidence": 0.9, "evidence": "e"}})))

    client = _make_client(handler)
    markdown = _long_markdown()
    chunks, _ = _split_markdown(markdown)
    num_chunks = len(chunks)
    assert num_chunks >= 3  # nếu không thì test không kiểm được điều muốn kiểm

    t0 = time.monotonic()
    result = client.extract(markdown, {"a": "mô tả"}, parallel=True)
    elapsed = time.monotonic() - t0

    assert result.success is True
    assert len(result.records) == num_chunks
    # Song song: gần SLEEP (1 lượt), không phải num_chunks * SLEEP (tuần tự).
    assert elapsed < SLEEP * num_chunks * 0.6


def test_sequential_stays_sequential_for_comparison():
    """Đối chứng: KHÔNG tick 'Nhanh' (mặc định `parallel=False`) thì tổng thời
    gian phải gần bằng tổng các đoạn cộng lại, không được tự ý chạy song song."""
    SLEEP = 0.2

    def handler(request: httpx.Request) -> httpx.Response:
        time.sleep(SLEEP)
        return httpx.Response(200, json=_openai_response(
            json.dumps({"a": {"value": "r", "confidence": 0.9, "evidence": "e"}})))

    client = _make_client(handler)
    markdown = _long_markdown()
    chunks, _ = _split_markdown(markdown)
    num_chunks = len(chunks)

    t0 = time.monotonic()
    result = client.extract(markdown, {"a": "mô tả"})  # parallel mặc định False
    elapsed = time.monotonic() - t0

    assert result.success is True
    assert elapsed >= SLEEP * num_chunks * 0.8


def test_parallel_preserves_chunk_order_regardless_of_which_finishes_first():
    """Đoạn xong SAU vẫn phải nằm ĐÚNG vị trí của nó trong kết quả — không được
    xáo trộn theo thứ tự hoàn thành khi chạy song song."""
    lock = threading.Lock()
    seen_order: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        content = json.loads(request.content)["messages"][1]["content"]
        # Đoạn đầu tiên (chứa "dòng 0 ") cố tình xong CHẬM nhất.
        if "dòng 0 " in content:
            time.sleep(0.3)
            value = "cham"
        else:
            time.sleep(0.02)
            value = "nhanh"
        with lock:
            seen_order.append(value)
        return httpx.Response(200, json=_openai_response(
            json.dumps({"a": {"value": value, "confidence": 0.9, "evidence": "e"}})))

    client = _make_client(handler)
    markdown = _long_markdown()
    result = client.extract(markdown, {"a": "mô tả"}, parallel=True)

    assert result.success is True
    assert seen_order[0] != "cham"  # đoạn khác thực sự xong trước (chứng minh có chạy song song)
    assert result.records[0]["a"].value == "cham"  # nhưng kết quả vẫn đúng thứ tự đoạn 1 trước


def test_parallel_one_bad_chunk_is_skipped_same_as_sequential():
    """Hành vi bỏ qua đoạn lỗi + giữ warning phải GIỐNG HỆT chế độ tuần tự khi
    chạy song song — chỉ khác thời gian chờ."""
    seen_prompts = []

    def handler(request: httpx.Request) -> httpx.Response:
        content = json.loads(request.content)["messages"][1]["content"]
        with threading.Lock():
            seen_prompts.append(content)
        if "dòng 0 " in content:
            raise httpx.ReadTimeout("boom", request=request)
        return httpx.Response(200, json=_openai_response(
            json.dumps([{"a": {"value": "r", "confidence": 0.9, "evidence": "e"}}])))

    client = _make_client(handler)
    result = client.extract(_long_markdown(), {"a": "mô tả"}, parallel=True)

    assert result.success is True
    assert result.warning is not None
    assert "đoạn 1" in result.warning and "boom" in result.warning


def test_extract_defaults_to_sequential_when_parallel_not_given():
    """Gọi extract() KHÔNG truyền `parallel` (code cũ/nơi khác gọi) vẫn phải hoạt
    động — mặc định tuần tự, không lỗi thiếu tham số."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_openai_response(
            json.dumps({"price": {"value": 1, "confidence": 1, "evidence": "e"}})))

    client = _make_client(handler)
    result = client.extract("nội dung ngắn", {"price": "giá"})

    assert result.success is True


# ---------------------------------------------------------------- hạn mức (rate limit), 429, tiến độ
from src.ai.rate_limiter import ModelRateLimiter  # noqa: E402


class _FakeClock:
    def __init__(self):
        self.now = 0.0
        self.slept = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds
        self.slept += seconds


def _ok(value="r"):
    return httpx.Response(200, json=_openai_response(json.dumps([{"a": {"value": value, "confidence": 0.9, "evidence": "e"}}])))


def _limited_client(handler, limits=None, **kw):
    clock = _FakeClock()
    limiter = ModelRateLimiter(limits or {}, clock=clock, sleep=clock.sleep)
    return _make_client(handler, rate_limiter=limiter, **kw), limiter, clock


def test_429_waits_for_retry_after_then_retries_and_succeeds_without_counting_as_a_failed_chunk():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"retry-after": "21"}, json={"message": "API rate limit exceeded"})
        return _ok()

    client, _, clock = _limited_client(handler)
    result = client.extract("nội dung", {"a": "mô tả"})

    assert result.success is True and result.warning is None
    assert len(calls) == 2
    assert clock.slept >= 21  # đã CHỜ đúng Retry-After, không thử lại tức thì


def test_429_that_never_clears_gives_up_after_a_few_waits_with_a_clear_error():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(429, headers={"retry-after": "5"}, json={"message": "API rate limit exceeded"})

    client, _, _ = _limited_client(handler)
    result = client.extract("nội dung", {"a": "mô tả"})

    assert result.success is False and "rate_limited" in result.error
    assert len(calls) == 5  # 1 lần đầu + 4 lần chờ rồi thử lại


def test_429_does_not_use_up_the_normal_single_retry_for_other_errors():
    """Chuỗi 429 -> 500 -> 200: lỗi 500 vẫn được thử lại 1 lần bình thường sau khi đã chờ 429."""
    statuses = iter([429, 500, 200])
    calls = []

    def handler(request):
        calls.append(1)
        status = next(statuses)
        if status == 429:
            return httpx.Response(429, headers={"retry-after": "1"})
        if status == 500:
            return httpx.Response(500, text="lỗi")
        return _ok()

    client, _, _ = _limited_client(handler)
    result = client.extract("nội dung", {"a": "mô tả"})

    assert result.success is True and len(calls) == 3


def test_configured_limit_delays_calls_instead_of_sending_and_getting_429():
    """Hạn mức 1 request/phút: 3 đoạn tuần tự phải tự CHỜ ~61s giữa các lượt, và server không bao giờ thấy 429."""
    calls = []

    def handler(request):
        calls.append(1)
        return _ok()

    client, _, clock = _limited_client(handler, limits={"openai/gpt-4o": 1})
    result = client.extract(_long_markdown(), {"a": "mô tả"})
    chunks, _ = _split_markdown(_long_markdown())

    assert result.success is True and len(calls) == len(chunks) >= 3
    assert clock.slept >= 61 * (len(chunks) - 1) - 1


def test_ratelimit_header_from_api_becomes_the_limit():
    def handler(request):
        response = _ok()
        response.headers["x-ratelimit-limit-minute"] = "7"
        return response

    client, limiter, _ = _limited_client(handler, limits={"openai/gpt-4o": 2})
    client.extract("nội dung", {"a": "mô tả"})

    assert limiter.limit_for("openai/gpt-4o") == 7  # header là chuẩn, ghi đè cấu hình


def test_progress_events_report_chunks_done_over_total_for_sequential_mode():
    events = []

    def handler(request):
        return _ok()

    client, _, _ = _limited_client(handler)
    markdown = _long_markdown()
    chunks, _ = _split_markdown(markdown)
    result = client.extract(markdown, {"a": "mô tả"}, on_progress=events.append)

    assert result.success is True
    assert events[0]["ai_chunks_total"] == len(chunks) and events[0]["ai_chunks_done"] == 0
    assert events[-1]["ai_chunks_done"] == len(chunks) and events[-1]["ai_calling"] == 0
    dones = [e["ai_chunks_done"] for e in events]
    assert dones == sorted(dones)  # chỉ tăng, từng đoạn một
    assert any(e["ai_calling"] >= 1 for e in events)  # có lúc báo "model đang xử lý"


def test_progress_events_show_waiting_for_rate_limit_with_a_countdown():
    events = []
    client, _, _ = _limited_client(lambda request: _ok(), limits={"openai/gpt-4o": 1})
    client.extract(_long_markdown(), {"a": "mô tả"}, on_progress=events.append)

    waiting = [e for e in events if e["ai_waiting"] >= 1]
    assert waiting and all(e["ai_wait_seconds"] > 0 for e in waiting)  # UI hiện được "chờ hạn mức, còn ~Ns"


def test_single_short_page_still_reports_one_chunk_progress():
    events = []
    client, _, _ = _limited_client(lambda request: _ok())
    client.extract("nội dung ngắn", {"a": "mô tả"}, on_progress=events.append)

    assert events[0]["ai_chunks_total"] == 1 and events[-1]["ai_chunks_done"] == 1


def test_a_broken_progress_callback_never_breaks_extraction():
    def boom(_):
        raise RuntimeError("UI hỏng")

    client, _, _ = _limited_client(lambda request: _ok())
    assert client.extract("nội dung", {"a": "mô tả"}, on_progress=boom).success is True


def test_parallel_mode_respects_the_limit_instead_of_firing_everything_at_once():
    """Nhanh + hạn mức 2/cửa sổ: dù có nhiều đoạn, trong mọi cửa sổ chỉ có tối đa 2 request được GỬI đi."""
    stamps, lock = [], threading.Lock()

    def handler(request):
        with lock:
            stamps.append(time.monotonic())
        return _ok()

    limiter = ModelRateLimiter({"openai/gpt-4o": 2}, window_seconds=0.4, margin_seconds=0.0)
    client = _make_client(handler, rate_limiter=limiter)
    markdown = _long_markdown()
    chunks, _ = _split_markdown(markdown)
    result = client.extract(markdown, {"a": "mô tả"}, parallel=True)

    assert result.success is True and len(stamps) == len(chunks) >= 3
    stamps.sort()
    for i in range(len(stamps) - 2):
        assert stamps[i + 2] - stamps[i] >= 0.35
