"""Agent polling có journal local; không tự thực thi lại run sau crash."""
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from urllib.parse import urlparse

import httpx

from .config import validate_workbook
from src.runner.preflight_contract import PreflightReport, metadata

ROOT = Path(__file__).resolve().parents[1]
METRICS = ("passed", "failed", "errors", "unverified", "duration")


def child_path(root, name):
    if not re.fullmatch(r"[\w .-]{1,160}", name) or ".." in name or name in (".", ""):
        raise ValueError("Invalid local path")
    root = Path(root).resolve()
    candidate = root / name
    if candidate.is_symlink() or root not in candidate.resolve().parents:
        raise ValueError("Invalid local path")
    return candidate


def write_json(path, value):
    temporary = path.with_suffix(".pending")
    # Do not overwrite evidence of an interrupted write or follow a temporary symlink.
    with temporary.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value))
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def result_payload(result):
    if not isinstance(result, dict) or set(result) - {*METRICS, "preflight"} or not set(METRICS) <= set(result):
        raise ValueError("Invalid result metadata")
    for key in METRICS[:-1]:
        if type(result[key]) is not int or not 0 <= result[key] <= 100000:
            raise ValueError("Invalid result counts")
    duration = result["duration"]
    if type(duration) not in (int, float) or not 0 <= duration <= 604800 or not math.isfinite(duration):
        raise ValueError("Invalid result duration")
    payload = {key: result[key] for key in METRICS}
    if result.get("preflight") is not None:
        payload["preflight"] = PreflightReport.model_validate(result["preflight"]).model_dump(exclude_none=True)
    return payload


class JournalError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def load_journal(path, root):
    if path.is_symlink():
        raise JournalError("SYMLINK")
    try:
        checked = child_path(root, path.name)
        if path.suffix != ".json" or path.resolve() != checked:
            raise ValueError("Outside journal root")
    except ValueError:
        raise JournalError("UNSAFE_PATH") from None
    if path.with_suffix(".pending").exists() or path.with_suffix(".pending").is_symlink():
        raise JournalError("INTERRUPTED_WRITE")
    if path.stat().st_size > 128000:
        raise JournalError("TOO_LARGE")
    try:
        entry = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError):
        raise JournalError("INVALID_JSON") from None
    allowed = {"run_id", "state", "started_at", "finished_at", "notification_at", "deleted_at", "deletion_reason", "result"}
    if not isinstance(entry, dict) or set(entry) - allowed or entry.get("state") not in ("RUNNING", "PENDING_RESULT", "REPORTED"):
        raise JournalError("INVALID_METADATA")
    if entry.get("run_id") != path.stem:
        raise JournalError("IDENTITY_MISMATCH")
    for key in ("started_at", "finished_at", "notification_at", "deleted_at"):
        value = entry.get(key)
        if value is not None and (type(value) not in (int, float) or not 0 <= value <= 253402300799):
            raise JournalError("INVALID_TIMESTAMP")
    if entry["state"] == "PENDING_RESULT" or "result" in entry:
        try:
            result_payload(entry.get("result"))
        except ValueError:
            raise JournalError("INVALID_RESULT") from None
    if entry["state"] == "RUNNING" and entry.get("finished_at") is not None:
        raise JournalError("INVALID_METADATA")
    return entry


class LocalAgent:
    def __init__(self, api, token, configs, state, env_path=None, client=None, clock=time.time):
        parsed = urlparse(api)
        if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost", "::1")):
            raise ValueError("Agent yêu cầu HTTPS, trừ localhost")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("API URL không được chứa credential/query")
        self.client = client or httpx.Client(base_url=api.rstrip("/"),
                    headers={"Authorization": "Bearer " + token}, timeout=30, trust_env=False)
        self.configs, self.state = Path(configs).resolve(), Path(state).resolve()
        self.env_path, self.clock = env_path, clock
        self.journal_warning_stages = set()
        for name in ("runs", "temp_uploads", "journal"):
            (self.state / name).mkdir(parents=True, exist_ok=True)

    def request(self, method, path, **kwargs):
        response = self.client.request(method, "/runner/agent/" + path, **kwargs)
        response.raise_for_status()
        return response

    def tick(self, worker=None):
        self.cleanup()
        self.resend_results()
        run = self.request("POST", "claim").json()
        if run:
            self.run(run, worker=worker)

    def run(self, run, worker=None):
        rid = run["run_id"]
        journal = child_path(self.state / "journal", rid + ".json")
        if journal.exists() or journal.with_suffix(".pending").exists() or journal.with_suffix(".pending").is_symlink():
            return  # run đã nhận trước đó, không thực thi hai lần.
        entry = {"run_id": rid, "started_at": self.clock(), "state": "RUNNING",
                 "finished_at": None, "notification_at": None, "deleted_at": None}
        write_json(journal, entry)
        temp = child_path(self.state / "temp_uploads", rid)
        output = child_path(self.state / "runs", rid)
        temp.mkdir(exist_ok=True)
        output.mkdir(exist_ok=True)
        result = {"passed": 0, "failed": 0, "errors": 1, "unverified": 0, "duration": 0}
        try:
            if run.get("local_ref"):
                path = child_path(self.configs, run["local_ref"])
                if path.suffix.lower() != ".xlsx" or path.stat().st_size > 10 * 1024 * 1024:
                    raise ValueError("Invalid workbook")
                content = path.read_bytes()
            else:
                content = self.request("GET", f"runs/{rid}/config").content
            try:
                validate_workbook(content)
            except Exception:
                result["preflight"] = metadata({"active_steps": 0, "active_testcases": 0,
                    "issues": [{"sheet": "workbook", "code": "INVALID_WORKBOOK"}], "warnings": []})
                raise
            config = temp / "testcase.xlsx"
            config.write_bytes(content)
            if worker:
                result = worker(config, rid, output)
            else:
                command = [sys.executable, "-m", "runner_agent.executor", "--config", str(config),
                           "--run-id", rid, "--output", str(output)]
                if self.env_path:
                    command += ["--env-path", self.env_path]
                # Không kế thừa token agent hay credential backend vào executor.
                environment = {k: os.environ[k] for k in ("SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP")
                               if k in os.environ}
                creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                with subprocess.Popen(command, cwd=ROOT, env=environment, shell=False,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                      creationflags=creationflags) as process:
                    last_beat = 0
                    while process.poll() is None:
                        if self.clock() - last_beat >= 15:
                            try:
                                self.request("POST", f"runs/{rid}/heartbeat")
                            except httpx.HTTPError:
                                pass  # Không restart testcase vì mạng đứt.
                            last_beat = self.clock()
                        time.sleep(1)
                summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
                result = {k: summary[k] for k in METRICS}
                if summary.get("preflight") is not None:
                    result["preflight"] = PreflightReport.model_validate(summary["preflight"]).model_dump(exclude_none=True)
        except Exception:
            pass  # Chi tiết lỗi chỉ nằm local; không gửi raw exception.
        finally:
            # Chỉ xóa bản copy tạm của run; file người dùng chọn giữ nguyên.
            checked = child_path(self.state / "temp_uploads", rid)
            if checked.exists():
                shutil.rmtree(checked)
            report = result.get("preflight")
            result = {k: result[k] for k in METRICS}
            if report is not None:
                try:
                    result["preflight"] = PreflightReport.model_validate(report).model_dump(exclude_none=True)
                except ValueError:
                    pass
            entry.update(state="PENDING_RESULT", result=result, finished_at=self.clock())
            write_json(journal, entry)
        self.resend_results()

    def resend_results(self):
        for path, entry in self.journal_entries():
            if entry["state"] == "PENDING_RESULT":
                try:
                    self.request("POST", f"runs/{entry['run_id']}/result", json=result_payload(entry["result"]))
                except httpx.HTTPError:
                    continue
                entry["state"] = "REPORTED"
                try:
                    write_json(path, entry)
                except OSError:
                    self.journal_warning("result_write")

    def journal_warning(self, stage):
        if stage not in self.journal_warning_stages:
            self.journal_warning_stages.add(stage)
            print("Journal cần kiểm tra local; mục lỗi được giữ nguyên, không replay. Giai đoạn:", stage)

    def read_journal(self, path):
        return load_journal(path, self.state / "journal")

    def journal_entries(self):
        for path in (self.state / "journal").glob("*.json"):
            try:
                entry = self.read_journal(path)
            except (OSError, ValueError):
                self.journal_warning("read")
                continue
            yield path, entry
        if any((self.state / "journal").glob("*.pending")):
            self.journal_warning("interrupted_write")

    def resend_result(self, run_id):
        """Explicit metadata resend for an older server acknowledgement; no claim/execution."""
        path = child_path(self.state / "journal", run_id + ".json")
        entry = self.read_journal(path)
        if entry["state"] not in ("PENDING_RESULT", "REPORTED"):
            raise ValueError("Only a completed journal result can be resent")
        payload = result_payload(entry.get("result"))
        self.request("POST", f"runs/{run_id}/result", json=payload)
        entry["state"] = "REPORTED"
        write_json(path, entry)

    def recover(self):
        """Gọi một lần lúc startup: run bị ngắt được báo ERROR, không chạy lại."""
        for path, entry in self.journal_entries():
            if entry["state"] == "RUNNING":
                entry.update(state="PENDING_RESULT", finished_at=self.clock(), result={
                    "passed": 0, "failed": 0, "errors": 1, "unverified": 0, "duration": 0})
                try:
                    temp = child_path(self.state / "temp_uploads", entry["run_id"])
                    if temp.exists():
                        shutil.rmtree(temp)
                    write_json(path, entry)
                except (OSError, ValueError):
                    self.journal_warning("recovery")

    def cleanup(self):
        for path, entry in self.journal_entries():
            try:
                self.cleanup_entry(path, entry)
            except (OSError, ValueError):
                self.journal_warning("retention")

    def cleanup_entry(self, path, entry):
        original = dict(entry)
        finished = entry.get("finished_at")
        if finished is None or entry.get("deleted_at") is not None:
            return
        now = self.clock()
        if now >= finished + 6 * 86400 and entry.get("notification_at") is None:
            entry["notification_at"] = now
            print("Artifact local sắp hết hạn:", entry["run_id"])
        notice = entry.get("notification_at")
        if notice is not None and now >= max(finished + 7 * 86400, notice + 86400):
            folder = child_path(self.state / "runs", entry["run_id"])
            if folder.exists():
                shutil.rmtree(folder)
            entry.update(deleted_at=now, deletion_reason="retention_policy_7_days")
            with (self.state / "retention_audit.jsonl").open("a", encoding="utf-8") as audit:
                audit.write(json.dumps({"event": "RUN_ARTIFACTS_DELETED", "run_id": entry["run_id"],
                                       "deleted_at": now, "notification_sent_at": notice}) + "\n")
        if entry != original:
            write_json(path, entry)
