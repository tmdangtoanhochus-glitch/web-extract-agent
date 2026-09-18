import json

import httpx
import pytest

from runner_agent.client import LocalAgent, write_json

RESULT = {"passed": 1, "failed": 0, "errors": 0, "unverified": 0, "duration": 1}


def agent_at(tmp_path, now=100):
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(200, content=b"null" if req.url.path.endswith("claim") else b"{}",
                              headers={"Content-Type": "application/json"})
    agent = LocalAgent("http://localhost", "fake", tmp_path / "configs", tmp_path / "state",
        client=httpx.Client(base_url="http://localhost", transport=httpx.MockTransport(handler)), clock=lambda: now)
    return agent, calls


@pytest.mark.parametrize("bad", ["{incomplete", "[]", json.dumps({"run_id": "other", "state": "RUNNING"}),
    json.dumps({"run_id": "bad", "state": "UNTRUSTED"}),
    json.dumps({"run_id": "bad", "state": "REPORTED", "finished_at": "synthetic-private"}),
    json.dumps({"run_id": "bad", "state": "PENDING_RESULT", "result": {**RESULT, "value": "synthetic-private"}}),
    json.dumps({"run_id": "bad", "state": "REPORTED", "finished_at": float("nan")}),
    "x" * 128001], ids=["truncated_json", "wrong_type", "wrong_identity", "wrong_state",
                         "wrong_timestamp", "extra_result_data", "nan_timestamp", "oversized"])
def test_corrupt_journal_is_preserved_and_does_not_block_valid_results_or_allow_replay(tmp_path, bad, capsys):
    agent, calls = agent_at(tmp_path)
    folder = agent.state / "journal"
    corrupt = folder / "bad.json"
    corrupt.write_text(bad)
    write_json(folder / "good.json", {"run_id": "good", "state": "PENDING_RESULT", "result": RESULT})
    artifact = agent.state / "runs" / "bad"
    artifact.mkdir()
    agent.recover()
    agent.cleanup()
    agent.resend_results()
    agent.run({"run_id": "bad"}, worker=lambda *a: pytest.fail("Must never replay a corrupt journal"))
    assert corrupt.read_text() == bad and artifact.exists()
    assert [r.url.path for r in calls] == ["/runner/agent/runs/good/result"]
    assert json.loads((folder / "good.json").read_text())["state"] == "REPORTED"
    output = capsys.readouterr().out
    assert "synthetic-private" not in output and "incomplete" not in output
    assert output.count("Giai đoạn: read") == 1


def test_interrupted_write_blocks_only_its_run_and_is_not_overwritten(tmp_path):
    agent, calls = agent_at(tmp_path)
    folder = agent.state / "journal"
    pending = folder / "interrupted.pending"
    pending.write_text("synthetic partial write")
    agent.run({"run_id": "interrupted"}, worker=lambda *a: pytest.fail("No replay from pending evidence"))
    with pytest.raises(FileExistsError):
        write_json(folder / "interrupted.json", {"run_id": "interrupted"})
    write_json(folder / "good.json", {"run_id": "good", "state": "PENDING_RESULT", "result": RESULT})
    agent.tick()
    assert pending.read_text() == "synthetic partial write"
    assert [r.url.path for r in calls] == ["/runner/agent/runs/good/result", "/runner/agent/claim"]
    assert "interrupted_write" in agent.journal_warning_stages


def test_mismatched_journal_cannot_delete_another_run_artifacts(tmp_path):
    agent, _ = agent_at(tmp_path, now=10 * 86400)
    victim = agent.state / "runs" / "victim"
    victim.mkdir()
    path = agent.state / "journal" / "bad.json"
    write_json(path, {"run_id": "victim", "state": "REPORTED", "finished_at": 0, "notification_at": 1})
    original = path.read_bytes()
    agent.cleanup()
    assert victim.exists() and path.read_bytes() == original


def test_existing_pending_evidence_prevents_cleanup_and_metadata_resend(tmp_path):
    agent, calls = agent_at(tmp_path, now=10 * 86400)
    path = agent.state / "journal" / "old.json"
    write_json(path, {"run_id": "old", "state": "REPORTED", "finished_at": 0, "notification_at": 1, "result": RESULT})
    path.with_suffix(".pending").write_text("partial")
    artifact = agent.state / "runs" / "old"
    artifact.mkdir()
    agent.cleanup()
    with pytest.raises(ValueError):
        agent.resend_result("old")
    assert artifact.exists() and calls == []


def test_write_failure_after_server_ack_does_not_block_other_results(tmp_path, monkeypatch):
    import runner_agent.client as module
    agent, calls = agent_at(tmp_path)
    for rid in ("bad", "good"):
        write_json(agent.state / "journal" / (rid + ".json"), {"run_id": rid, "state": "PENDING_RESULT", "result": RESULT})
    original_write = module.write_json
    def fail_one(path, entry):
        if path.stem == "bad":
            raise OSError("synthetic-private")
        original_write(path, entry)
    monkeypatch.setattr(module, "write_json", fail_one)
    agent.resend_results()
    assert len(calls) == 2
    assert json.loads((agent.state / "journal" / "good.json").read_text())["state"] == "REPORTED"
    assert json.loads((agent.state / "journal" / "bad.json").read_text())["state"] == "PENDING_RESULT"
    assert "result_write" in agent.journal_warning_stages


def test_stable_retention_entry_is_not_rewritten_each_tick(tmp_path, monkeypatch):
    import runner_agent.client as module
    agent, _ = agent_at(tmp_path)
    write_json(agent.state / "journal" / "good.json", {"run_id": "good", "state": "REPORTED", "finished_at": 0})
    monkeypatch.setattr(module, "write_json", lambda *a: pytest.fail("No state change; no disk write needed"))
    agent.cleanup()
