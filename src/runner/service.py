"""Rule-based auth/job lifecycle; không chạy browser trong backend."""
import hashlib
import secrets
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

TERMINAL = {"PASSED", "FAILED", "ERROR", "UNVERIFIED", "CANCELLED", "LOST"}


class RunnerError(ValueError):
    def __init__(self, message, code=400):
        super().__init__(message)
        self.code = code


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def safe_path(root, *parts):
    root = Path(root).resolve()
    target = root.joinpath(*parts)
    if any(p in ("", ".", "..") or "/" in p or "\\" in p or ":" in p for p in parts):
        raise RunnerError("Đường dẫn không hợp lệ")
    resolved = target.resolve()
    if root not in resolved.parents or target.is_symlink():
        raise RunnerError("Đường dẫn không hợp lệ")
    return resolved


class Service:
    def __init__(self, repo, root, clock=time.time):
        self.repo, self.root, self.clock = repo, Path(root).resolve(), clock
        self.hasher = PasswordHasher()
        self.dummy_hash = self.hasher.hash(secrets.token_urlsafe(24))
        for name in ("runs", "temp_uploads"):
            (self.root / name).mkdir(parents=True, exist_ok=True)

    def audit(self, event, user_id=None, run_id=None, detail=None):
        key = uuid.uuid4().hex
        entry = {"id": key, "event": event, "user_id": user_id, "run_id": run_id, "at": self.clock()}
        if detail is not None:
            entry["detail"] = detail
        self.repo.put("audit", key, entry)
        return key

    def add_user(self, username, password, role="user", bootstrap=False):
        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,64}", username) or len(password) < 12 or role not in ("admin", "user"):
            raise RunnerError("Username 3–64 ký tự; password tối thiểu 12 ký tự; role user/admin")
        with self.repo.transaction():
            users = self.repo.all("users")
            if bootstrap and users:
                raise RunnerError("Đã có user; dùng trang quản trị")
            if any(u["username"] == username for u in users):
                raise RunnerError("Username đã tồn tại", 409)
            user = {"id": uuid.uuid4().hex, "username": username,
                    "password_hash": self.hasher.hash(password), "role": role, "is_active": True,
                    "created_at": self.clock(), "updated_at": self.clock()}
            self.repo.put("users", user["id"], user)
            self.audit("USER_CREATED", user["id"])
            return self.public_user(user)

    @staticmethod
    def public_user(user):
        return {k: v for k, v in user.items() if k != "password_hash"}

    def reset_password(self, uid, new_password):
        """Admin đặt lại mật khẩu cho user quên mật khẩu — không có luồng "tự
        reset qua email" (chưa có hệ thống email), admin đặt trực tiếp mật khẩu
        mới rồi báo lại cho user qua kênh khác (không phải trách nhiệm hệ thống).
        Tự đánh dấu hết mọi yêu cầu "quên mật khẩu" đang chờ của user này —
        admin xử lý xong thì request biến mất khỏi danh sách chờ."""
        if len(new_password) < 12:
            raise RunnerError("Password tối thiểu 12 ký tự")
        with self.repo.transaction():
            target = self.repo.get("users", uid)
            if not target:
                raise RunnerError("Không tìm thấy user", 404)
            target.update(password_hash=self.hasher.hash(new_password), updated_at=self.clock())
            self.repo.put("users", uid, target)
            self.audit("USER_PASSWORD_RESET", uid)
            for req in self.repo.all("password_reset_requests"):
                if req["user_id"] == uid:
                    self.repo.delete("password_reset_requests", req["id"])
            return self.public_user(target)

    def request_password_reset(self, username):
        """Người dùng bị khoá tài khoản (quên mật khẩu) gửi yêu cầu — KHÔNG cần
        đăng nhập (route công khai). CHỦ Ý không tiết lộ username có tồn tại
        hay không qua response (tránh dò username): luôn coi như thành công,
        chỉ thật sự tạo request nếu username khớp user đang active. Nhiều lần
        gửi liên tiếp cho cùng user chỉ giữ 1 request đang chờ (idempotent),
        tránh admin bị spam danh sách chờ."""
        with self.repo.transaction():
            user = next((u for u in self.repo.all("users") if u["username"] == username), None)
            if not user or not user["is_active"]:
                return
            if any(r["user_id"] == user["id"] for r in self.repo.all("password_reset_requests")):
                return
            rid = uuid.uuid4().hex
            self.repo.put("password_reset_requests", rid, {
                "id": rid, "user_id": user["id"], "username": user["username"], "created_at": self.clock(),
            })
            self.audit("PASSWORD_RESET_REQUESTED", user["id"])

    def login(self, username, password):
        with self.repo.transaction():
            user = next((u for u in self.repo.all("users") if u["username"] == username), None)
            try:
                valid = self.hasher.verify(user["password_hash"] if user else self.dummy_hash, password)
            except VerificationError:
                valid = False
            if not valid or not user or not user["is_active"]:
                raise RunnerError("Đăng nhập không hợp lệ", 401)
            token = secrets.token_urlsafe(32)
            self.repo.put("sessions", digest(token), {"user_id": user["id"], "expires_at": self.clock() + 28800})
            self.audit("LOGIN", user["id"])
            return {"session": token, "user": self.public_user(user)}

    def authenticate(self, token):
        session = self.repo.get("sessions", digest(token))
        user = self.repo.get("users", session["user_id"]) if session else None
        if not session or session["expires_at"] <= self.clock() or not user or not user["is_active"]:
            raise RunnerError("Cần đăng nhập", 401)
        return self.public_user(user)

    def register_agent(self, user):
        token = secrets.token_urlsafe(32)
        agent = {"id": uuid.uuid4().hex, "owner": user["id"], "token_hash": digest(token),
                 "active": True, "last_seen": None}
        with self.repo.transaction():
            self.repo.put("agents", agent["id"], agent)
            self.audit("AGENT_REGISTERED", user["id"])
        return {"agent_id": agent["id"], "agent_token": token}

    def agent(self, token):
        agent = next((a for a in self.repo.all("agents") if a["token_hash"] == digest(token)), None)
        owner = self.repo.get("users", agent["owner"]) if agent else None
        if not agent or not agent["active"] or not owner or not owner["is_active"]:
            raise RunnerError("Agent không hợp lệ", 401)
        return agent

    def owned_run(self, run_id, user):
        run = self.repo.get("runs", run_id)
        if not run or (run["owner"] != user["id"] and user["role"] != "admin"):
            raise RunnerError("Không tìm thấy run", 404)
        return run

    def create_run(self, user, agent_id, config_name, config=None, local_ref=None):
        # Backend không nhận local path tùy ý: chỉ basename đã đăng ký trong agent config root.
        if not re.fullmatch(r"[\w .-]{1,100}\.xlsx", config_name) or ".." in config_name:
            raise RunnerError("Tên config .xlsx không hợp lệ")
        if (config is None) == (local_ref is None):
            raise RunnerError("Chọn upload hoặc local config")
        if local_ref is not None and local_ref != config_name:
            raise RunnerError("Local config chỉ dùng tên file")
        if config is not None and len(config) > 10 * 1024 * 1024:
            raise RunnerError("Config tối đa 10 MB", 413)
        with self.repo.transaction():
            agent = self.repo.get("agents", agent_id)
            if not agent or agent["owner"] != user["id"] or not agent["active"]:
                raise RunnerError("Agent không thuộc user", 403)
            stem = re.sub(r"[^\w-]", "_", Path(config_name).stem)
            base = stem + "_" + datetime.fromtimestamp(self.clock(), timezone.utc).strftime("%Y%m%d_%H%M%S")
            run_id = base
            while self.repo.get("runs", run_id):
                run_id = base + "_" + uuid.uuid4().hex[:8]
            run = {"run_id": run_id, "owner": user["id"], "agent_id": agent_id,
                   "config_name": config_name, "local_ref": local_ref, "status": "QUEUED",
                   "created_at": self.clock(), "started_at": None, "finished_at": None,
                   "expires_at": None, "notification_sent_at": None, "deleted_at": None,
                   "deletion_reason": None, "passed": 0, "failed": 0, "errors": 0,
                   "unverified": 0, "duration": 0, "artifacts": []}
            if config is not None:
                target = safe_path(self.root / "temp_uploads", run_id)
                target.mkdir()
                (target / "testcase.xlsx").write_bytes(config)
            self.repo.put("runs", run_id, run)
            self.audit("RUN_CREATED", user["id"], run_id)
            return run

    def claim(self, agent):
        with self.repo.transaction():
            agent["last_seen"] = self.clock()
            self.repo.put("agents", agent["id"], agent)
            # Một agent nhận tối đa một run đang chạy.
            runs = self.repo.all("runs")
            if any(r["agent_id"] == agent["id"] and r["status"] == "RUNNING" for r in runs):
                return None
            run = next((r for r in sorted(runs, key=lambda r: r["created_at"])
                        if r["agent_id"] == agent["id"] and r["status"] == "QUEUED"), None)
            if not run:
                return None
            run.update(status="RUNNING", started_at=self.clock(), heartbeat_at=self.clock())
            self.repo.put("runs", run["run_id"], run)
            self.audit("RUN_STARTED", run["owner"], run["run_id"])
            return run

    def check_agent_run(self, agent, run_id):
        run = self.repo.get("runs", run_id)
        if not run or run["agent_id"] != agent["id"]:
            raise RunnerError("Không tìm thấy run", 404)
        return run

    def finish(self, agent, run_id, result):
        with self.repo.transaction():
            run = self.check_agent_run(agent, run_id)
            late = run["status"] == "LOST" and run.get("started_at") is not None
            if run["status"] in TERMINAL and (not late or run.get("late_result")):
                return run
            if run["status"] != "RUNNING" and not late:
                raise RunnerError("Run chưa chạy", 409)
            counts = {k: result[k] for k in ("passed", "failed", "errors", "unverified")}
            total = sum(counts.values())
            status = ("ERROR" if counts["errors"] or not total else "FAILED" if counts["failed"]
                      else "UNVERIFIED" if counts["unverified"] else "PASSED")
            report = result.get("preflight")
            if report is not None:
                from .preflight_contract import PreflightReport
                report = PreflightReport.model_validate(report).model_dump(exclude_none=True)
                if report["status"] == "blocked":
                    status = "ERROR"
                    counts = {"passed": 0, "failed": 0, "errors": max(1, counts["errors"]), "unverified": 0}
            if late:
                received = {**counts, "status": status, "duration": result["duration"],
                            "received_at": self.clock()}
                if report is not None:
                    received["preflight"] = report
                run["late_result"] = received
                self.repo.put("runs", run_id, run)
                self.audit("RUN_LATE_RESULT_RECEIVED_NO_REPLAY", run["owner"], run_id)
                return run
            if report is not None:
                run["preflight"] = report
            run.update(**counts, status=status, duration=result["duration"], finished_at=self.clock(),
                       expires_at=self.clock() + 7 * 86400)
            self.remove_temp(run_id)
            self.repo.put("runs", run_id, run)
            self.audit("RUN_FINISHED", run["owner"], run_id)
            return run

    def remove_temp(self, run_id):
        target = safe_path(self.root / "temp_uploads", run_id)
        if target.exists():
            shutil.rmtree(target)

    def maintenance(self):
        """Thông báo bền vững trong UI; xóa sau hạn và ít nhất 24h sau thông báo."""
        with self.repo.transaction():
            now = self.clock()
            for run in self.repo.all("runs"):
                rid = run["run_id"]
                if (run["status"] == "RUNNING" and now - run.get("heartbeat_at", now) > 300) or (
                        run["status"] == "QUEUED" and now - run["created_at"] > 86400):
                    run.update(status="LOST", finished_at=now, expires_at=now + 7 * 86400)
                    self.remove_temp(rid)
                    self.audit("RUN_LOST_NO_AUTOMATIC_RETRY", run["owner"], rid)
                expiry = run.get("expires_at")
                if expiry and not run["deleted_at"]:
                    if now >= expiry - 86400 and run["notification_sent_at"] is None:
                        run["notification_sent_at"] = now
                        self.repo.put("notifications", rid, {"run_id": rid, "owner": run["owner"],
                                      "created_at": now, "delete_after": max(expiry, now + 86400)})
                        self.audit("RETENTION_NOTIFICATION", run["owner"], rid)
                    notified = run["notification_sent_at"]
                    if notified is not None and now >= max(expiry, notified + 86400):
                        folder = safe_path(self.root / "runs", rid)
                        if folder.exists():
                            shutil.rmtree(folder)
                        run.update(deleted_at=now, deletion_reason="retention_policy_7_days")
                        self.audit("RUN_ARTIFACTS_DELETED", run["owner"], rid)
                self.repo.put("runs", rid, run)
