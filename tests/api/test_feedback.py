"""Test luồng phản hồi người dùng: AI_DEBUG phân loại -> trả lời trực tiếp hoặc
chuyển admin kèm trace (mock `triage_fn`, không gọi AI thật — CLAUDE.md mục 6)."""
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.ai.feedback_triage import TriageResult, triage_feedback
from src.api.admin import create_admin_router
from src.api.feedback import create_feedback_router, redact
from src.storage.sqlite_storage import SQLiteStorage

_AUTH = ("admin", "s3cr3t")


def _client(storage, triage):
    app = FastAPI()
    app.include_router(create_feedback_router(storage, "https://ai.example/v1", "k", "m", triage_fn=triage))
    app.include_router(create_admin_router(
        storage=storage, ai_debug_base_url="", ai_debug_api_key="", ai_debug_model="",
        admin_username=_AUTH[0], admin_password=_AUTH[1]))
    return TestClient(app)


def test_not_a_bug_with_high_confidence_is_answered_directly():
    storage = SQLiteStorage(":memory:")
    seen = {}

    def triage(**kw):
        seen.update(kw)
        return TriageResult(is_bug=False, confidence=0.9, answer="Hãy chọn chế độ Bảng HTML.")

    client = _client(storage, triage)
    resp = client.post("/feedback", json={"screen": "crawl-buoc-2", "message": "sao không ra bảng"})

    assert resp.status_code == 201
    assert resp.json()["status"] == "answered"
    assert "Bảng HTML" in resp.json()["answer"]
    assert client.get("/admin/feedback", auth=_AUTH).json() == []


def test_bug_is_escalated_to_admin_with_trace_and_can_be_resolved():
    storage = SQLiteStorage(":memory:")
    storage.add_audit_log("crawl_failed", job_id="j1", detail={"error": "http_500"})
    client = _client(storage, lambda **kw: TriageResult(is_bug=True, confidence=0.95, diagnosis="Lỗi 500 từ nguồn"))

    resp = client.post("/feedback", json={"screen": "crawl-buoc-4", "message": "lưu dữ liệu bị lỗi"})
    assert resp.json()["status"] == "escalated"

    items = client.get("/admin/feedback", auth=_AUTH).json()
    assert len(items) == 1
    assert items[0]["ai_diagnosis"] == "Lỗi 500 từ nguồn"
    assert items[0]["trace"]["recent_crawl_failures"][0]["job_id"] == "j1"

    assert client.post(f"/admin/feedback/{items[0]['feedback_id']}/resolve", auth=_AUTH).status_code == 200
    assert client.get("/admin/feedback", auth=_AUTH).json() == []


def test_low_confidence_not_bug_is_still_escalated():
    storage = SQLiteStorage(":memory:")
    client = _client(storage, lambda **kw: TriageResult(is_bug=False, confidence=0.4, answer="có lẽ..."))
    assert client.post("/feedback", json={"screen": "runner", "message": "không chạy được"}).json()["status"] == "escalated"


def test_ai_failure_is_escalated_not_answered():
    storage = SQLiteStorage(":memory:")
    client = _client(storage, lambda **kw: TriageResult(success=False, error="timeout"))
    assert client.post("/feedback", json={"screen": "runner", "message": "không chạy được"}).json()["status"] == "escalated"


def test_secrets_are_redacted_before_ai_and_storage():
    storage = SQLiteStorage(":memory:")
    seen = {}

    def triage(**kw):
        seen.update(kw)
        return TriageResult(is_bug=True, confidence=0.9)

    client = _client(storage, triage)
    client.post("/feedback", json={"screen": "crawl", "message": "lỗi cookie: sessionid=abc123 xyz"})

    assert "abc123" not in seen["message"]
    assert "abc123" not in str(client.get("/admin/feedback", auth=_AUTH).json())
    assert "abc" not in redact("token=abcdefg")


def test_admin_feedback_requires_auth():
    client = _client(SQLiteStorage(":memory:"), lambda **kw: TriageResult())
    assert client.get("/admin/feedback").status_code == 401


def test_triage_feedback_parses_json_and_handles_bad_response():
    def handler(content):
        return httpx.MockTransport(lambda req: httpx.Response(200, json={"choices": [{"message": {"content": content}}]}))

    ok = httpx.Client(base_url="https://x", transport=handler(
        'Kết quả: {"is_bug": false, "confidence": 0.8, "answer": "ok", "diagnosis": ""}'))
    result = triage_feedback("m", "s", "c", "https://x", "k", "m", client=ok)
    assert (result.success, result.is_bug, result.confidence, result.answer) == (True, False, 0.8, "ok")

    bad = httpx.Client(base_url="https://x", transport=handler("không phải json"))
    assert triage_feedback("m", "s", "c", "https://x", "k", "m", client=bad).success is False
