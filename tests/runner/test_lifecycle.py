import json

import httpx

from runner_agent.client import LocalAgent, write_json


def test_agent_crash_recovery_reports_error_and_deletes_temp(tmp_path):
    sent = []
    def handler(req):
        sent.append(json.loads(req.content))
        return httpx.Response(200, json={})
    client = httpx.Client(base_url="http://localhost", transport=httpx.MockTransport(handler))
    agent = LocalAgent("http://localhost", "fake", tmp_path, tmp_path / "state", client=client, clock=lambda: 100)
    rid = "UAT_20260101_000000"
    folder = agent.state / "temp_uploads" / rid
    folder.mkdir()
    (folder / "testcase.xlsx").write_bytes(b"fake")
    path = agent.state / "journal" / (rid + ".json")
    write_json(path, {"run_id": rid, "state": "RUNNING", "finished_at": None})
    agent.recover()
    agent.resend_results()
    assert not folder.exists()
    assert sent[0]["errors"] == 1
    assert json.loads(path.read_text())["state"] == "REPORTED"


def test_local_retention_notifies_before_delete(tmp_path, capsys):
    now = [0]
    client = httpx.Client(base_url="http://localhost", transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    agent = LocalAgent("http://localhost", "fake", tmp_path, tmp_path / "state", client=client, clock=lambda: now[0])
    rid = "UAT_20260101_000000"
    folder = agent.state / "runs" / rid
    folder.mkdir()
    write_json(agent.state / "journal" / (rid + ".json"), {
        "run_id": rid, "state": "REPORTED", "finished_at": 0, "notification_at": None, "deleted_at": None})
    now[0] = 6 * 86400
    agent.cleanup()
    assert folder.exists()
    assert rid in capsys.readouterr().out
    now[0] = 7 * 86400
    agent.cleanup()
    assert not folder.exists()
    audit = json.loads((agent.state / "retention_audit.jsonl").read_text())
    assert audit["notification_sent_at"] == 6 * 86400


def test_transport_failure_preserves_result_for_retry(tmp_path):
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(503 if len(calls) == 1 else 200, json={})
    client = httpx.Client(base_url="http://localhost", transport=httpx.MockTransport(handler))
    agent = LocalAgent("http://localhost", "fake", tmp_path, tmp_path / "state", client=client)
    path = agent.state / "journal" / "UAT_20260101_000000.json"
    write_json(path, {"run_id": "UAT_20260101_000000", "state": "PENDING_RESULT", "result": {
        "passed": 1, "failed": 0, "errors": 0, "unverified": 0, "duration": 3}})
    agent.resend_results()
    assert json.loads(path.read_text())["state"] == "PENDING_RESULT"
    agent.resend_results()
    assert json.loads(path.read_text())["state"] == "REPORTED"
