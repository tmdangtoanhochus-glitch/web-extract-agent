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
import traceback as traceback_module
from typing import Any, Optional

from apscheduler.schedulers.background import BackgroundScheduler

from .ai.base import AIClient
from .fetch.base import FetchEngine
from .pipeline import run_crawl_job, run_file_crawl_job
from .storage.base import ScheduledJob, StorageEngine

logger = logging.getLogger(__name__)


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
    ) -> ScheduledJob:
        """Tạo job mới: lưu vào storage TRƯỚC (không mất job nếu crash ngay
        sau khi đăng ký với APScheduler), rồi đăng ký chạy thật. `dataset_id`
        chỉ cần khi `storage_mode="db"` — `None` cho job `storage_mode="file"`."""
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
        )
        self._register_job(job)
        return job

    def remove_job(self, job_id: str) -> None:
        self._storage.delete_scheduled_job(job_id)
        if self._scheduler.get_job(job_id) is not None:
            self._scheduler.remove_job(job_id)

    def _register_job(self, job: ScheduledJob) -> None:
        self._scheduler.add_job(
            self._run_job,
            trigger=job.trigger_type,
            id=job.job_id,
            replace_existing=True,
            kwargs={"job_id": job.job_id},
            **job.trigger_args,
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

        traceback_text: Optional[str] = None
        try:
            if job.storage_mode == "file":
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
                )
                status = db_result.status
        except Exception:
            traceback_text = traceback_module.format_exc()
            logger.exception("Job %s lỗi không mong đợi khi chạy crawl %s.", job_id, job.url)
            status = "error"

        self._storage.update_scheduled_job_run(job_id, status=status, traceback_text=traceback_text)
