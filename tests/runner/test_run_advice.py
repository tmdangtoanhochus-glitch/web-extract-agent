"""Báo lỗi và gợi ý sửa cho run Automation: metadata-only, có gợi ý cố định, AI chỉ nhận metadata."""
import json

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from src.ai.debug_assistant import DebugSuggestion
from src.api.runner import create_runner_router
from src.runner.repository import Repository
from src.runner.run_advice import needs_attention, rule_based_hints, run_metadata
from src.runner.service import RunnerError, Service

METRICS = {"passed": 0, "failed": 0, "errors": 1, "unverified": 0, "duration": 2}
BLOCKED = {"status": "blocked", "active_steps": 2, "active_testcases": 0, "warnings": [],
           "issues": [{"sheet": "testcases", "code": "ENTER_AND_ACTIVATE_USER_TESTCASES"},
                      {"sheet": "steps", "row": 3, "code": "UNRESOLVED_LOCATOR"}]}


class Advisor:
    def __init__(self, success=True):
        self.calls, self.success = [], success

    def __call__(self, meta_json):
        self.calls.append(meta_json)
        return DebugSuggestion(content="1. Nguyên nhân...", success=self.success, error=None if self.success else "boom")


def build(tmp_path, advisor=None):
    repo = Repository()
    service = Service(repo, tmp_path / "server", clock=lambda: 1000000.0)
    service.add_user("owner", "synthetic-password-1", "admin")
    user = service.add_user("other", "synthetic-password-2")
    service.add_user("stranger", "synthetic-password-3")
    pair = service.register_agent(user)
    agent = service.agent(pair["agent_token"])
    app = FastAPI()

    @app.exception_handler(RunnerError)
    async def handler(req, exc):
        return JSONResponse(status_code=exc.code, content={"detail": str(exc)})

    app.include_router(create_runner_router(service, advisor=advisor))
    return service, repo, user, agent, TestClient(app)


def login(client, name, password):
    session = client.post("/runner/login", json={"username": name, "password": password}).json()["session"]
    return {"Authorization": "Bearer " + session}


def blocked_run(service, user, agent):
    run = service.create_run(user, agent["id"], "UAT.xlsx", local_ref="UAT.xlsx")
    service.claim(agent)
    service.finish(agent, run["run_id"], {**METRICS, "preflight": BLOCKED})
    return run["run_id"]


def test_metadata_has_only_counts_and_preflight_codes():
    meta = run_metadata({"run_id": "r1", "status": "ERROR", "passed": 0, "failed": 0, "errors": 1, "unverified": 0,
                         "duration": 2, "owner": "secret-owner", "config_name": "Lương_2026.xlsx", "preflight": BLOCKED})
    text = json.dumps(meta)
    assert "secret-owner" not in text and "Lương" not in text
    assert meta["preflight"]["issues"][1] == {"sheet": "steps", "row": 3, "code": "UNRESOLVED_LOCATOR"}


def test_rule_based_hints_cover_codes_and_status_without_duplicates():
    meta = run_metadata({"run_id": "r", "status": "ERROR", "errors": 1, "preflight": BLOCKED})
    hints = rule_based_hints(meta)
    assert any(h.startswith("ENTER_AND_ACTIVATE_USER_TESTCASES") for h in hints)
    assert any(h.startswith("UNRESOLVED_LOCATOR (sheet steps, dòng 3)") for h in hints)
    assert not any(h.startswith("ERROR:") for h in hints)  # preflight đã giải thích, không thêm gợi ý chung
    assert any(h.startswith("FAILED:") for h in rule_based_hints({"status": "FAILED"}))
    assert any(h.startswith("LOST:") for h in rule_based_hints({"status": "LOST"}))


@pytest.mark.parametrize("run,expected", [({"status": "PASSED"}, False), ({"status": "FAILED"}, True),
    ({"status": "UNVERIFIED"}, True), ({"status": "LOST"}, True), ({"status": "QUEUED"}, False),
    ({"status": "PASSED", "preflight": {"status": "blocked"}}, True)])
def test_needs_attention(run, expected):
    assert needs_attention(run) is expected


def test_suggest_fix_returns_rule_hints_and_ai_text_using_metadata_only(tmp_path):
    advisor = Advisor()
    service, repo, user, agent, client = build(tmp_path, advisor)
    try:
        rid = blocked_run(service, user, agent)
        response = client.post(f"/runner/runs/{rid}/suggest-fix", headers=login(client, "other", "synthetic-password-2"))
        assert response.status_code == 200
        body = response.json()
        assert body["ai"].startswith("1. Nguyên nhân") and body["ai_error"] is None
        assert any("UNRESOLVED_LOCATOR" in h for h in body["hints"])
        sent = json.loads(advisor.calls[0])
        assert sent["preflight"]["issues"][0]["code"] == "ENTER_AND_ACTIVATE_USER_TESTCASES"
        assert "UAT.xlsx" not in advisor.calls[0]  # không gửi tên file
        assert [e for e in repo.all("audit") if e["event"] == "RUN_SUGGEST_FIX"]
    finally:
        repo.close()


@pytest.mark.parametrize("advisor", [None, Advisor(success=False)])
def test_suggest_fix_falls_back_to_rule_hints_when_ai_missing_or_failing(tmp_path, advisor):
    service, repo, user, agent, client = build(tmp_path, advisor)
    try:
        rid = blocked_run(service, user, agent)
        body = client.post(f"/runner/runs/{rid}/suggest-fix", headers=login(client, "other", "synthetic-password-2")).json()
        assert body["hints"] and body["ai"] is None and body["ai_error"]
    finally:
        repo.close()


def test_suggest_fix_rejects_healthy_run_foreign_user_and_rate_limits(tmp_path):
    service, repo, user, agent, client = build(tmp_path, Advisor())
    try:
        rid = blocked_run(service, user, agent)
        owner_h = login(client, "other", "synthetic-password-2")
        assert client.post(f"/runner/runs/{rid}/suggest-fix", headers=login(client, "stranger", "synthetic-password-3")).status_code == 404
        assert client.post(f"/runner/runs/{rid}/suggest-fix", headers=login(client, "owner", "synthetic-password-1")).status_code == 200  # admin
        ok = service.create_run(user, agent["id"], "OK.xlsx", local_ref="OK.xlsx")
        service.claim(agent)
        service.finish(agent, ok["run_id"], {"passed": 1, "failed": 0, "errors": 0, "unverified": 0, "duration": 1})
        assert client.post(f"/runner/runs/{ok['run_id']}/suggest-fix", headers=owner_h).status_code == 409
        codes = [client.post(f"/runner/runs/{rid}/suggest-fix", headers=owner_h).status_code for _ in range(6)]
        assert codes[:5] == [200] * 5 and codes[5] == 429
    finally:
        repo.close()


def test_report_run_is_redacted_owner_scoped_and_visible_only_to_admin(tmp_path):
    service, repo, user, agent, client = build(tmp_path)
    try:
        rid = blocked_run(service, user, agent)
        owner_h = login(client, "other", "synthetic-password-2")
        note = "Không chạy được password=Hunter2abc và token: abcdefghijklmnopqrstuvwxyz0123456789ABCDEF"
        assert client.post(f"/runner/runs/{rid}/report", json={"note": note},
                           headers=login(client, "stranger", "synthetic-password-3")).status_code == 404
        response = client.post(f"/runner/runs/{rid}/report", json={"note": note}, headers=owner_h)
        assert response.status_code == 200 and response.json()["status"] == "received"
        assert client.get("/runner/reports", headers=owner_h).status_code == 403
        data = client.get("/runner/reports", headers=login(client, "owner", "synthetic-password-1")).json()
        saved = data["reports"][0]["detail"]
        assert "Hunter2abc" not in saved["note"] and "abcdefghijklmnopqrstuvwxyz" not in saved["note"]
        assert saved["run"]["status"] == "ERROR" and data["runs_needing_attention"][0]["run_id"] == rid
        assert client.post(f"/runner/runs/{rid}/report", json={"note": "x" * 501}, headers=owner_h).status_code == 422
    finally:
        repo.close()
