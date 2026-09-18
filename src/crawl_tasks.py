"""Small, process-local queue for public crawl controls; no credentials on disk."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import secrets
from threading import Condition, RLock
import time
from uuid import uuid4


class TaskNotFound(LookupError):
    pass


class QueueFull(ValueError):
    pass


class CrawlTasks:
    def __init__(self, workers=2, capacity=8, retention_seconds=3600, pause_seconds=900):
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="crawl")
        self.capacity = capacity
        self.retention_seconds = retention_seconds
        self.pause_seconds = pause_seconds
        self.condition = Condition(RLock())
        self.jobs = {}
        self.closed = False

    def _purge(self):
        now = time.monotonic()
        for key, job in list(self.jobs.items()):
            if job["finished"] is not None and now - job["finished"] > self.retention_seconds:
                del self.jobs[key]

    def submit(self, execute):
        with self.condition:
            self._purge()
            if self.closed or sum(j["finished"] is None for j in self.jobs.values()) >= self.capacity:
                raise QueueFull("Hàng đợi crawl đang đầy; thử lại sau")
            # Also bound retained results, evicting the oldest completed task first.
            if len(self.jobs) >= self.capacity * 4:
                oldest = next((key for key, job in self.jobs.items() if job["finished"] is not None), None)
                if oldest:
                    del self.jobs[oldest]
            job_id, control = uuid4().hex, secrets.token_urlsafe(32)
            job = {"id": job_id, "digest": hashlib.sha256(control.encode()).hexdigest(),
                   "state": "queued", "pause": False, "cancel": False, "started": False,
                   "paused_at": None, "finished": None, "progress": {}, "result": None, "error": None}
            self.jobs[job_id] = job
            self.pool.submit(self._execute, job, execute)
            return {"id": job_id, "control": control, "state": "queued"}

    def _checkpoint(self, job):
        with self.condition:
            while job["pause"] and not job["cancel"] and not self.closed:
                job["state"] = "paused"
                if time.monotonic() - job["paused_at"] >= self.pause_seconds:
                    job["cancel"] = True
                    break
                self.condition.wait(timeout=0.2)
            if job["cancel"] or self.closed:
                return False
            job["state"] = "running"
            return True

    def _progress(self, job, progress):
        with self.condition:
            job["progress"].update(progress)

    def _execute(self, job, execute):
        try:
            with self.condition:
                job["started"] = True
            if not self._checkpoint(job):
                with self.condition:
                    job["state"] = "cancelled"
                return
            result = execute(lambda: self._checkpoint(job), lambda p: self._progress(job, p))
            with self.condition:
                job["result"] = result
                job["state"] = "cancelled" if result.get("status") == "cancelled" else "completed"
        except Exception as exc:
            with self.condition:
                job["state"] = "failed"
                job["error"] = {"error_type": type(exc).__name__, "detail": "Crawl gặp lỗi; kiểm tra cấu hình hoặc báo admin"}
                headers = getattr(exc, "headers", None) or {}
                if headers.get("X-Crawl-Request-ID"):
                    job["error"]["request_id"] = headers["X-Crawl-Request-ID"]
        finally:
            with self.condition:
                job["finished"] = time.monotonic()
                self.condition.notify_all()

    def _authorized(self, job_id, control):
        self._purge()
        job = self.jobs.get(job_id)
        digest = hashlib.sha256((control or "").encode()).hexdigest()
        if job is None or not secrets.compare_digest(job["digest"], digest):
            raise TaskNotFound("Không tìm thấy đợt crawl hoặc mã điều khiển không hợp lệ")
        return job

    def status(self, job_id, control):
        with self.condition:
            job = self._authorized(job_id, control)
            return {"id": job["id"], "state": job["state"], "progress": dict(job["progress"]),
                    "result": job["result"], "error": job["error"]}

    def action(self, job_id, control, action):
        with self.condition:
            job = self._authorized(job_id, control)
            if action not in {"pause", "resume", "cancel"}:
                raise ValueError("Unknown action")
            if job["finished"] is None:
                if action == "cancel":
                    job["cancel"] = True
                    job["state"] = "cancel_requested"
                elif not job["cancel"]:
                    job["pause"] = action == "pause"
                    if job["pause"]:
                        job["paused_at"] = job["paused_at"] or time.monotonic()
                        job["state"] = "pause_requested"
                    else:
                        job["paused_at"] = None
                        job["state"] = "running" if job["started"] else "queued"
                self.condition.notify_all()
            return self.status(job_id, control)

    def shutdown(self):
        with self.condition:
            self.closed = True
            self.condition.notify_all()
        self.pool.shutdown(wait=False)
