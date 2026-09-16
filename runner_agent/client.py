"""Agent polling có journal local; không tự thực thi lại run sau crash."""
import json
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
    temporary.write_text(json.dumps(value), encoding="utf-8")
    temporary.replace(path)


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
        if journal.exists():
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
            validate_workbook(content)
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
        except Exception:
            pass  # Chi tiết lỗi chỉ nằm local; không gửi raw exception.
        finally:
            # Chỉ xóa bản copy tạm của run; file người dùng chọn giữ nguyên.
            checked = child_path(self.state / "temp_uploads", rid)
            if checked.exists():
                shutil.rmtree(checked)
            result = {k: result[k] for k in METRICS}
            entry.update(state="PENDING_RESULT", result=result, finished_at=self.clock())
            write_json(journal, entry)
        self.resend_results()

    def resend_results(self):
        for path in (self.state / "journal").glob("*.json"):
            if path.is_symlink():
                continue
            entry = json.loads(path.read_text(encoding="utf-8"))
            if entry["state"] == "PENDING_RESULT":
                try:
                    self.request("POST", f"runs/{entry['run_id']}/result", json=entry["result"])
                except httpx.HTTPError:
                    continue
                entry["state"] = "REPORTED"
                write_json(path, entry)

    def recover(self):
        """Gọi một lần lúc startup: run bị ngắt được báo ERROR, không chạy lại."""
        for path in (self.state / "journal").glob("*.json"):
            if path.is_symlink():
                continue
            entry = json.loads(path.read_text(encoding="utf-8"))
            if entry["state"] == "RUNNING":
                entry.update(state="PENDING_RESULT", finished_at=self.clock(), result={
                    "passed": 0, "failed": 0, "errors": 1, "unverified": 0, "duration": 0})
                temp = child_path(self.state / "temp_uploads", entry["run_id"])
                if temp.exists():
                    shutil.rmtree(temp)
                write_json(path, entry)

    def cleanup(self):
        for path in (self.state / "journal").glob("*.json"):
            if path.is_symlink():
                continue
            entry = json.loads(path.read_text(encoding="utf-8"))
            finished = entry.get("finished_at")
            if finished is None or entry.get("deleted_at"):
                continue
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
            write_json(path, entry)
