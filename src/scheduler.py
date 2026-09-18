"""Chạy job crawl định kỳ bằng APScheduler (CLAUDE.md mục "Tech stack":
"APScheduler (không dùng Celery+Redis cho MVP — quá nặng so với nhu cầu)").

`CrawlScheduler` chỉ là lớp mỏng gọi lại đúng `run_crawl_job()` — không viết
logic crawl riêng ở đây (CLAUDE.md mục "Quy ước code": "scheduler sẽ gọi lại
đúng các hàm này, không viết logic lồng trong route handler").

Job được lưu vào `StorageEngine` (bảng `scheduled_jobs`) để nạp lại đúng lịch
sau khi app restart — `BackgroundScheduler` mặc định của APScheduler chỉ giữ
job trong bộ nhớ tiến trình, mất hết khi process dừng.
"""
from __future__ import annotations

import logging
import math
from dataclasses import asdict, replace
from threading import RLock
import traceback as traceback_module
from typing import Any, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from .ai.base import AIClient
from .fetch.base import FetchEngine
from .pipeline import run_crawl_job, run_file_crawl_job
from .storage.base import ScheduledJob, StorageEngine

logger = logging.getLogger(__name__)


def validate_trigger(trigger_type, trigger_args, timezone=None):
    """Validate public trigger constructors before making any persistent changes."""
    args = dict(trigger_args)
    if timezone is not None:
        args.setdefault("timezone", timezone)
    try:
        if trigger_type == "interval":
            durations = [float(args.get(unit, 0)) for unit in ("weeks", "days", "hours", "minutes", "seconds")]
            if any(not math.isfinite(value) or value < 0 for value in durations) or sum(durations) <= 0:
                raise ValueError("Invalid interval")
            return IntervalTrigger(**args)
        if trigger_type == "cron":
            if not any(key in args for key in ("year", "month", "day", "week", "day_of_week", "hour", "minute", "second")):
                raise ValueError("Missing cron fields")
            return CronTrigger(**args)
    except Exception:
        raise ValueError("Thời gian lịch không hợp lệ; kiểm tra chu kỳ, giờ và múi giờ") from None
    raise ValueError("Chỉ hỗ trợ lịch interval hoặc cron")


class CrawlScheduler:
    """`scheduler` cho phép inject 1 `BackgroundScheduler` đã cấu hình sẵn
    (vd. test dùng interval rất ngắn) — theo adapter/test-double pattern
    CLAUDE.md mục 6."""

    def __init__(
        self,
        fetcher: FetchEngine,
        ai_client: AIClient,
        storage: StorageEngine,
        scheduler: BackgroundScheduler | None = None,
        confidence_threshold: float = 0.7,
    ) -> None:
        self._fetcher = fetcher
        self._ai_client = ai_client
        self._storage = storage
        self._scheduler = scheduler or BackgroundScheduler()
        self._confidence_threshold = confidence_threshold
        self._management_lock = RLock()

    def start(self) -> None:
        """Khởi động scheduler và nạp lại toàn bộ job đang bật (`enabled`)
        từ storage — để lịch chạy tiếp đúng sau khi app restart."""
        if not self._scheduler.running:
            self._scheduler.start()
        for job in self._storage.list_scheduled_jobs(enabled_only=True):
            self._register_job(job)

    def shutdown(self, wait: bool = False) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=wait)

    def add_job(
        self,
        dataset_id: Optional[str],
        url: str,
        field_descriptions: dict[str, str],
        trigger_type: str,
        trigger_args: dict[str, Any],
        storage_mode: str = "db",
        file_path: Optional[str] = None,
        write_mode: Optional[str] = None,
        key_field: Optional[str] = None,
        image_fields: Optional[list[str]] = None,
        crawl_options: Optional[dict] = None,
    ) -> ScheduledJob:
        """Tạo job mới: lưu vào storage TRƯỚC (không mất job nếu crash ngay
        sau khi đăng ký với APScheduler), rồi đăng ký chạy thật. `dataset_id`
        chỉ cần khi `storage_mode="db"` — `None` cho job `storage_mode="file"`."""
        validate_trigger(trigger_type, trigger_args, self._scheduler.timezone)
        job = self._storage.create_scheduled_job(
            dataset_id=dataset_id,
            url=url,
            field_descriptions=field_descriptions,
            trigger_type=trigger_type,
            trigger_args=trigger_args,
            storage_mode=storage_mode,
            file_path=file_path,
            write_mode=write_mode,
            key_field=key_field,
            image_fields=image_fields,
            crawl_options=crawl_options,
        )
        try:
            self._register_job(job)
        except Exception:
            self._storage.delete_scheduled_job(job.job_id)
            raise
        return job

    def describe(self, job):
        live = self._scheduler.get_job(job.job_id)
        next_run = getattr(live, "next_run_time", None) if job.enabled else None
        return {**asdict(job), "next_run_at": next_run.isoformat() if next_run else None,
                "scheduler_running": self._scheduler.running,
                "timezone": str(job.trigger_args.get("timezone") or self._scheduler.timezone)}

    def configure(self, job_id, enabled=None, trigger_type=None, trigger_args=None):
        with self._management_lock:
            old = self._storage.get_scheduled_job(job_id)
            if old is None:
                raise LookupError("Không tìm thấy lịch")
            updated = replace(old, enabled=old.enabled if enabled is None else enabled,
                              trigger_type=trigger_type if trigger_type is not None else old.trigger_type,
                              trigger_args=trigger_args if trigger_args is not None else old.trigger_args)
            if updated.enabled or trigger_type is not None:
                validate_trigger(updated.trigger_type, updated.trigger_args, self._scheduler.timezone)
            if updated == old:
                return old
            self._storage.configure_scheduled_job(job_id, updated.enabled, updated.trigger_type, updated.trigger_args)
            try:
                if updated.enabled:
                    self._register_job(updated)
                elif self._scheduler.get_job(job_id) is not None:
                    self._scheduler.remove_job(job_id)
            except Exception:
                self._storage.configure_scheduled_job(job_id, old.enabled, old.trigger_type, old.trigger_args)
                raise
            self._storage.add_audit_log("schedule_configured", job_id=job_id, detail={
                "enabled": updated.enabled, "trigger_type": updated.trigger_type,
                "trigger_args": updated.trigger_args})
            return self._storage.get_scheduled_job(job_id)

    def remove_job(self, job_id: str) -> None:
        with self._management_lock:
            self._storage.delete_scheduled_job(job_id)
            if self._scheduler.get_job(job_id) is not None:
                self._scheduler.remove_job(job_id)

    def _register_job(self, job: ScheduledJob) -> None:
        self._scheduler.add_job(
            self._run_job,
            trigger=validate_trigger(job.trigger_type, job.trigger_args, self._scheduler.timezone),
            id=job.job_id,
            replace_existing=True,
            kwargs={"job_id": job.job_id},
            max_instances=1,
            coalesce=True,
        )

    def _run_job(self, job_id: str) -> None:
        """Chạy 1 lần crawl theo job đã lưu — rẽ nhánh theo `storage_mode`
        ("db" | "file", xem `pipeline.py`). KHÔNG để exception văng ra làm
        chết luồng scheduler (mất khả năng chạy các job khác); luôn ghi lại
        kết quả/lỗi (kèm traceback đầy đủ nếu lỗi, cho panel admin) vào
        storage để tra cứu."""
        job = self._storage.get_scheduled_job(job_id)
        if job is None:
            logger.warning("Job %s không còn tồn tại trong storage — bỏ qua lần chạy này.", job_id)
            return
        if not job.enabled:
            return

        traceback_text: Optional[str] = None
        try:
            if job.crawl_options:
                from .bulk_crawl import CrawlOptions, run_bulk
                outcome = run_bulk(url=job.url, field_descriptions=job.field_descriptions,
                    options=CrawlOptions.model_validate(job.crawl_options), fetcher=self._fetcher,
                    ai_client=self._ai_client, storage=self._storage, dataset_id=job.dataset_id,
                    storage_mode=job.storage_mode, file_path=job.file_path, write_mode=job.write_mode or "append",
                    image_fields=job.image_fields, confidence_threshold=self._confidence_threshold)
                status = outcome["status"]
                self._storage.add_audit_log("bulk_schedule_run", job_id=job_id, detail=outcome)
            elif job.storage_mode == "file":
                file_result = run_file_crawl_job(
                    url=job.url,
                    field_descriptions=job.field_descriptions,
                    file_path=job.file_path,
                    write_mode=job.write_mode,
                    key_field=job.key_field,
                    fetcher=self._fetcher,
                    ai_client=self._ai_client,
                    storage=self._storage,
                    confidence_threshold=self._confidence_threshold,
                    image_fields=job.image_fields,
                )
                status = file_result.status
            else:
                db_result = run_crawl_job(
                    url=job.url,
                    field_descriptions=job.field_descriptions,
                    dataset_id=job.dataset_id,
                    fetcher=self._fetcher,
                    ai_client=self._ai_client,
                    storage=self._storage,
                    confidence_threshold=self._confidence_threshold,
                    image_fields=job.image_fields,
                )
                status = db_result.status
        except Exception:
            traceback_text = traceback_module.format_exc()
            logger.exception("Job %s lỗi không mong đợi khi chạy crawl %s.", job_id, job.url)
            status = "error"

        self._storage.update_scheduled_job_run(job_id, status=status, traceback_text=traceback_text)
