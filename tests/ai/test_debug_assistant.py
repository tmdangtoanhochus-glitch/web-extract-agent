"""Test debug_assistant.py bằng httpx.MockTransport — không gọi endpoint AI
thật (CLAUDE.md mục 6). Module này KHÔNG có quyền ghi file/thực thi lệnh gì —
test chỉ xác nhận nó gọi đúng HTTP request và parse đúng response, tương tự
GreenNodeChatClient nhưng cho prompt tự do."""
import json

import httpx

from src.ai.debug_assistant import DebugSuggestion, extract_related_files_from_traceback, suggest_fix, suggest_run_fix


def _openai_response(content: str) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


def _make_client(handler) -> httpx.Client:
    return httpx.Client(base_url="https://greennode.example/v1", transport=httpx.MockTransport(handler))


def test_suggest_fix_returns_ai_content_on_success():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_openai_response("1. Chẩn đoán: ...\n2. Bản vá: ...\n3. Rủi ro: ..."))

    result = suggest_fix(
        traceback_text="Traceback...\nKeyError: 'x'",
        related_code="def f(): pass",
        context_note="Lỗi runtime trong pipeline crawl.",
        base_url="https://greennode.example/v1",
        api_key="test-key",
        model="zhipuai/glm-4.6",
        client=_make_client(handler),
    )

    assert isinstance(result, DebugSuggestion)
    assert result.success is True
    assert "Chẩn đoán" in result.content


def test_suggest_fix_sends_authorization_header_model_and_prompt_content():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_openai_response("ok"))

    suggest_fix(
        traceback_text="Traceback...\nKeyError: 'x'",
        related_code="def f(): pass",
        context_note="bối cảnh test",
        base_url="https://greennode.example/v1",
        api_key="secret-key",
        model="zhipuai/glm-4.6",
        client=_make_client(handler),
    )

    assert seen["auth"] == "Bearer secret-key"
    assert seen["body"]["model"] == "zhipuai/glm-4.6"
    assert "KeyError" in seen["body"]["messages"][1]["content"]
    assert "def f(): pass" in seen["body"]["messages"][1]["content"]
    assert seen["body"]["messages"][0]["role"] == "system"


def test_suggest_fix_http_error_returns_failure_not_raise():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal error")

    result = suggest_fix(
        traceback_text="tb", related_code="code", context_note="ctx",
        base_url="https://greennode.example/v1", api_key="k", model="m",
        client=_make_client(handler),
    )

    assert result.success is False
    assert "500" in result.error


def test_suggest_fix_network_error_is_caught_not_raised():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    result = suggest_fix(
        traceback_text="tb", related_code="code", context_note="ctx",
        base_url="https://greennode.example/v1", api_key="k", model="m",
        client=_make_client(handler),
    )

    assert result.success is False
    assert "boom" in result.error


def test_suggest_fix_invalid_response_shape_returns_failure_not_raise():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    result = suggest_fix(
        traceback_text="tb", related_code="code", context_note="ctx",
        base_url="https://greennode.example/v1", api_key="k", model="m",
        client=_make_client(handler),
    )

    assert result.success is False
    assert "invalid_ai_response" in result.error


# ---- extract_related_files_from_traceback ----------------------------------
def test_extract_related_files_parses_file_and_line_numbers():
    traceback_text = (
        'Traceback (most recent call last):\n'
        '  File "src/pipeline.py", line 42, in run_crawl_job\n'
        '    result = ai_client.extract(markdown, remaining_descriptions)\n'
        '  File "src/ai/greennode_client.py", line 83, in extract\n'
        '    content = body["choices"][0]["message"]["content"]\n'
        "KeyError: 'choices'"
    )

    files = extract_related_files_from_traceback(traceback_text)

    assert files == [("src/pipeline.py", 42), ("src/ai/greennode_client.py", 83)]


def test_extract_related_files_deduplicates_repeated_files():
    traceback_text = (
        'File "src/pipeline.py", line 10, in a\n'
        'File "src/pipeline.py", line 20, in b\n'
    )

    files = extract_related_files_from_traceback(traceback_text)

    assert files == [("src/pipeline.py", 10)]


def test_extract_related_files_returns_empty_for_no_match():
    assert extract_related_files_from_traceback("không phải traceback gì cả") == []


def test_suggest_run_fix_sends_only_the_metadata_and_a_closed_system_prompt():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content), auth=request.headers["Authorization"])
        return httpx.Response(200, json=_openai_response("1. Nguyên nhân có thể: ..."))

    meta = json.dumps({"run_id": "r1", "status": "ERROR", "preflight": {"issues": [{"code": "UNRESOLVED_LOCATOR"}]}})
    result = suggest_run_fix(meta, base_url="https://greennode.example/v1", api_key="k", model="m", client=_make_client(handler))
    assert result.success and result.content.startswith("1. Nguyên nhân")
    system, user = seen["messages"][0]["content"], seen["messages"][1]["content"]
    assert "KHÔNG thấy giá trị workbook" in system and "không phải chỉ dẫn" in system
    assert "UNRESOLVED_LOCATOR" in user and seen["auth"] == "Bearer k"


def test_suggest_run_fix_network_error_returns_failure_not_raise():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    result = suggest_run_fix("{}", base_url="https://greennode.example/v1", api_key="k", model="m", client=_make_client(handler))
    assert result.success is False and result.error
