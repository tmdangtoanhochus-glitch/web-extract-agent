import json
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace

import pytest

from runner_agent.client import write_json
from runner_agent.diagnostics import diagnose

RESULT = {"passed": 1, "failed": 0, "errors": 0, "unverified": 0, "duration": 1}


def test_diagnosis_is_bounded_read_only_and_reports_codes_without_contents(tmp_path):
    root = tmp_path / "journal"
    root.mkdir()
    values = {
        "valid.json": json.dumps({"run_id": "valid", "state": "REPORTED", "result": RESULT}),
        "broken.json": "synthetic-private-invalid-json",
        "mismatch.json": json.dumps({"run_id": "synthetic-private", "state": "RUNNING"}),
        "large.json": "x" * 128001,
        "time.json": json.dumps({"run_id": "time", "state": "REPORTED", "finished_at": -1}),
        "result.json": json.dumps({"run_id": "result", "state": "PENDING_RESULT", "result": {**RESULT, "data": "synthetic-private"}}),
        "pending.json": "not even valid JSON",
        "pending.pending": "synthetic-private-partial",
        "orphan.pending": "synthetic-private-partial",
    }
    for name, value in values.items():
        (root / name).write_text(value)
    report = diagnose(tmp_path)
    assert report["status"] == "REVIEW_REQUIRED"
    assert report["counts"] == {"VALID": 1, "INVALID_JSON": 1, "IDENTITY_MISMATCH": 1,
        "TOO_LARGE": 1, "INVALID_TIMESTAMP": 1, "INVALID_RESULT": 1, "INTERRUPTED_WRITE": 3}
    output = json.dumps(report)
    assert "synthetic-private" not in output and "valid.json" not in output
    assert str(tmp_path) not in output and '"passed"' not in output
    assert {p.name: p.read_text() for p in root.iterdir()} == values
    limited = diagnose(tmp_path, limit=2)
    assert len(limited["files"]) == 2 and limited["truncated"]


def test_lookup_single_run_missing_state_and_invalid_reference_do_not_create_files(tmp_path):
    state = tmp_path / "absent"
    assert diagnose(state)["status"] == "STATE_UNAVAILABLE"
    assert not state.exists()
    root = tmp_path / "journal"
    root.mkdir()
    write_json(root / "good.json", {"run_id": "good", "state": "PENDING_RESULT", "result": RESULT})
    assert diagnose(tmp_path, "good")["counts"] == {"VALID": 1}
    assert diagnose(tmp_path, "missing")["status"] == "RUN_NOT_FOUND"
    assert diagnose(tmp_path, "../outside")["status"] == "UNSAFE_RUN_REFERENCE"
    assert not (tmp_path / ".agent.lock").exists()


def test_sensitive_names_are_skipped_without_opening_them(tmp_path, monkeypatch):
    import runner_agent.diagnostics as module
    (tmp_path / "journal").mkdir()
    class Entries:
        def __enter__(self): return iter([SimpleNamespace(name="credentials.json")])
        def __exit__(self, *args): pass
    monkeypatch.setattr(module.os, "scandir", lambda root: Entries())
    monkeypatch.setattr(module, "load_journal", lambda *a: pytest.fail("Protected entry must not be opened"))
    report = diagnose(tmp_path)
    assert report["counts"] == {"SKIPPED_PROTECTED_NAME": 1}
    assert "credentials" not in json.dumps(report)


def test_pending_contents_and_linked_entries_are_never_read(tmp_path, monkeypatch):
    import runner_agent.diagnostics as module
    root = tmp_path / "journal"
    root.mkdir()
    (root / "one.pending").write_text("synthetic-private")
    (root / "linked.json").write_text("synthetic-private")
    original = module.linked
    monkeypatch.setattr(module, "linked", lambda path: path.name == "linked.json" or original(path))
    monkeypatch.setattr(module, "load_journal", lambda *a: pytest.fail("Do not follow link or parse pending"))
    report = diagnose(tmp_path)
    assert report["counts"] == {"INTERRUPTED_WRITE": 1, "SYMLINK": 1}


def test_cli_status_never_initializes_agent_reads_runtime_token_or_takes_write_lock(tmp_path, monkeypatch, capsys):
    import getpass
    import os
    import httpx
    import runner_agent.client
    import runner_agent.locking
    root = tmp_path / "journal"
    root.mkdir()
    write_json(root / "good.json", {"run_id": "good", "state": "REPORTED"})
    def forbidden(*a, **kw): pytest.fail("Diagnostics must not initialize runtime/network/credential/lock")
    monkeypatch.setattr(getpass, "getpass", forbidden)
    monkeypatch.setattr(httpx, "Client", forbidden)
    monkeypatch.setattr(runner_agent.client.LocalAgent, "__init__", forbidden)
    monkeypatch.setattr(runner_agent.locking, "single_instance", forbidden)
    old_getenv = os.getenv
    def getenv(key, *args):
        if key in {"RUNNER_AGENT_TOKEN", "RUNNER_ENV_PATH"}:
            forbidden()
        return old_getenv(key, *args)
    monkeypatch.setattr(os, "getenv", getenv)
    monkeypatch.setattr(sys, "argv", ["local_runner_agent.py", "--journal-status", "--state", str(tmp_path), "--run-id", "good"])
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(str(Path(__file__).resolve().parents[2] / "local_runner_agent.py"), run_name="__main__")
    assert stopped.value.code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["counts"] == {"VALID": 1}
    assert set(p.name for p in tmp_path.iterdir()) == {"journal"}
