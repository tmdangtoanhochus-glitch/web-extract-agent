"""FastAPI backend — MVP tối giản: 1 endpoint crawl + 2 endpoint xem kết quả
(CLAUDE.md: "ưu tiên chạy được bản MVP tối giản — crawl 1 site tĩnh, lưu DB,
xem log — trước khi mở rộng").

`create_app()` nhận sẵn fetcher/ai_client/storage (dependency injection) để
test được mà không cần chạy thật (CLAUDE.md mục 6) — `app` ở cuối file mới là
instance thật, dùng khi chạy `uvicorn src.api.main:app`.

Lựa chọn lưu kết quả NGANG HÀNG khi tạo job (`storage_mode`, không phải ghi
kép): "db" (mặc định, giữ nguyên hành vi cũ — dataset/schema-match/dedup) hay
"file" (ghi JSON ra `data/exports/`, xem `src/storage/file_writer.py` — KHÔNG
dataset, KHÔNG dedup, KHÔNG schema-match).
"""
from __future__ import annotations

import dataclasses
import logging
import hashlib
import json
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional, Literal

from fastapi import FastAPI, HTTPException, Response, Header
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from uuid import UUID, uuid4
from urllib.parse import urlsplit
from fastapi.responses import FileResponse
from pydantic import BaseModel, SecretStr, ConfigDict, model_validator, Field
from ..crawl_tasks import CrawlTasks, QueueFull, TaskNotFound
from ..progress import PROGRESS_ID_PATTERN, ProgressStore
from ..bulk_crawl import CrawlOptions, plan_urls, run_bulk, preview_bulk
from .crawl_reports import create_report_router, context, exception_frames

from ..ai.base import AIClient
from ..ai.greennode_client import GreenNodeChatClient
from ..ai.rate_limiter import ModelRateLimiter
from ..config import load_settings
from ..fetch.base import FetchEngine, HybridFetcher, domain_of
from ..fetch.httpx_fetcher import HttpxFetcher
from ..pipeline import run_crawl_job, run_file_crawl_job
from ..scheduler import CrawlScheduler, validate_trigger
from ..storage.base import StorageEngine
from ..storage.file_writer import InvalidFilePathError, resolve_export_path
from ..storage.image_downloader import IMAGES_ROOT
from ..storage.postgres_storage import PostgresStorage
from ..storage.sqlite_storage import SQLiteStorage
from .admin import create_admin_router

_VALID_WRITE_MODES = ("append", "new_file", "overwrite_row")

logger = logging.getLogger(__name__)


class CrawlRequest(BaseModel):
    retry_of: UUID | None = None
    cookie_header: SecretStr | None = None
    cookie_origin: str | None = None
    crawl_options: CrawlOptions | None = None
    url: str
    field_descriptions: dict[str, str]
    dataset_id: Optional[str] = None
    dataset_name: Optional[str] = None
    storage_mode: str = "db"  # "db" | "file"
    file_path: Optional[str] = None
    write_mode: Optional[str] = None  # "append" | "new_file" | "overwrite_row"
    key_field: Optional[str] = None
    image_fields: list[str] = []  # field nào là ảnh cần tải về, xem image_downloader.py
    # Bỏ qua robots.txt cho đúng domain của url — hành động tường minh (CLAUDE.md
    # mục 3): bắt buộc kèm lý do, mỗi lần áp dụng đều log WARNING.
    ignore_robots: bool = False
    ignore_robots_reason: Optional[str] = None
    # Người dùng tự tick chọn ở Bước 3 (mặc định tắt) — chỉ có tác dụng khi trang
    # dài bị chia nhiều đoạn: gọi các đoạn ĐỒNG THỜI thay vì tuần tự, giảm hẳn
    # thời gian chờ nhưng tăng tải đồng thời lên AI/container (không đổi số lượt
    # gọi/chi phí AI so với tuần tự — xem AIClient.extract()).
    parallel_extract: bool = False
    # UI sinh 32 ký tự hex để hỏi tiến độ (`GET /crawl-progress/{id}`) trong lúc /crawl còn chạy — chỉ chứa nhãn giai
    # đoạn + số đếm, xem src/progress.py. Không thuộc cấu hình crawl nên loại khỏi config_fingerprint.
    progress_id: Optional[str] = Field(default=None, pattern=r"^[0-9a-f]{32}$")


class CrawlResponse(BaseModel):
    status: str
    dataset_id: Optional[str] = None
    record_id: Optional[str] = None
    file_path: Optional[str] = None
    data: Optional[dict] = None
    confidence: Optional[float] = None
    needs_review: Optional[bool] = None
    record_count: int = 0  # trang có thể chứa nhiều bản ghi (xem src/pipeline.py)
    detail: Optional[str] = None


class CrawlBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requests: list[CrawlRequest] = Field(min_length=1, max_length=20)


class CrawlControlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["pause", "resume", "cancel"]


class ScheduleCreateRequest(BaseModel):
    crawl_options: CrawlOptions | None = None
    url: str
    field_descriptions: dict[str, str]
    trigger_type: str  # "interval" | "cron" — truyền thẳng vào APScheduler
    trigger_args: dict
    dataset_id: Optional[str] = None
    storage_mode: str = "db"
    file_path: Optional[str] = None
    write_mode: Optional[str] = None
    key_field: Optional[str] = None
    image_fields: list[str] = []


class ScheduleUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool | None = None
    trigger_type: str | None = None
    trigger_args: dict | None = None

    @model_validator(mode="after")
    def validate_update(self):
        if (self.trigger_type is None) != (self.trigger_args is None):
            raise ValueError("Cần cả trigger_type và trigger_args")
        if self.enabled is None and self.trigger_type is None:
            raise ValueError("Cần trạng thái hoặc thời gian lịch")
        return self


def _validate_file_storage_config(
    file_path: Optional[str],
    write_mode: Optional[str],
    key_field: Optional[str],
    field_descriptions: dict[str, str],
) -> None:
    """Validate cấu hình storage_mode="file" — dùng chung cho /crawl và
    /schedules (mục 5 yêu cầu: 400 nếu thiếu field bắt buộc, 400 nếu file_path
    không hợp lệ)."""
    if not file_path:
        raise HTTPException(status_code=400, detail="cần file_path khi storage_mode='file'")
    if write_mode not in _VALID_WRITE_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"write_mode phải là 1 trong {_VALID_WRITE_MODES}",
        )
    if write_mode == "overwrite_row":
        if not key_field:
            raise HTTPException(status_code=400, detail="cần key_field khi write_mode='overwrite_row'")
        if key_field not in field_descriptions:
            raise HTTPException(
                status_code=400,
                detail=f"key_field {key_field!r} không nằm trong field_descriptions đã khai báo",
            )
    try:
        resolve_export_path(file_path)
    except InvalidFilePathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _log_manual_crawl_failure(storage: StorageEngine, url: str, status: str, detail: Optional[str]) -> None:
    """Ghi lỗi "Chạy crawl" thủ công (KHÔNG thuộc job lịch nào) vào
    `audit_log` để panel admin (`/admin/errors`) thấy lại được — trước đây
    lỗi này chỉ hiện thoáng qua trên UI (Bước 3) rồi mất, không tra cứu lại
    được sau đó."""
    storage.add_audit_log(
        event_type="crawl_failed", detail={"url": url, "status": status, "error": detail}
    )


def create_app(
    fetcher: FetchEngine,
    ai_client: AIClient,
    storage: StorageEngine,
    scheduler: Optional[CrawlScheduler] = None,
    ai_debug_base_url: str = "",
    ai_debug_api_key: str = "",
    ai_debug_model: str = "",
    ai_debug_timeout_seconds: float = 30.0,
    confidence_threshold: float = 0.7,
    admin_username: str = "",
    admin_password: str = "",
    runner_service=None,
    runner_planner=None,
) -> FastAPI:
    crawl_scheduler = scheduler or CrawlScheduler(
        fetcher=fetcher, ai_client=ai_client, storage=storage, confidence_threshold=confidence_threshold
    )
    crawl_tasks = CrawlTasks()
    progress_store = ProgressStore()

    @asynccontextmanager
    async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
        crawl_scheduler.start()
        retention_scheduler = None
        if runner_service is not None:
            from apscheduler.schedulers.background import BackgroundScheduler
            retention_scheduler = BackgroundScheduler()
            retention_scheduler.add_job(runner_service.maintenance, "interval", minutes=5,
                                        max_instances=1, coalesce=True)
            retention_scheduler.start()
            runner_service.maintenance()
        try:
            yield
        finally:
            crawl_tasks.shutdown()
            if retention_scheduler is not None:
                retention_scheduler.shutdown(wait=True)
            crawl_scheduler.shutdown()

    app = FastAPI(title="Web Data Extraction & Management Platform", lifespan=_lifespan)
    app.state.crawl_tasks = crawl_tasks
    app.state.progress_store = progress_store
    if runner_service is not None:
        from .runner import create_runner_router
        from ..runner.service import RunnerError

        @app.exception_handler(RunnerError)
        async def runner_error_handler(request, exc):
            return JSONResponse(status_code=exc.code, content={"detail": str(exc)})

        app.include_router(create_runner_router(runner_service, runner_planner))

    @app.get("/health")
    def health() -> dict:
        """Liveness/readiness cho nền tảng deploy (GreenNode AgentBase) — chỉ
        xác nhận process đang sống, KHÔNG kiểm tra DB/AI kết nối được hay
        không (đúng khái niệm "liveness", không phải "dependency check")."""
        return {"status": "ok"}

    def crawl_one(req: CrawlRequest, request_fetcher, on_progress=None) -> CrawlResponse:
        if not req.field_descriptions:
            raise HTTPException(status_code=422, detail="field_descriptions không được rỗng")
        if req.storage_mode not in ("db", "file"):
            raise HTTPException(status_code=400, detail="storage_mode phải là 'db' hoặc 'file'")

        if req.storage_mode == "file":
            _validate_file_storage_config(req.file_path, req.write_mode, req.key_field, req.field_descriptions)

            file_result = run_file_crawl_job(
                url=req.url,
                field_descriptions=req.field_descriptions,
                file_path=req.file_path,
                write_mode=req.write_mode,
                key_field=req.key_field,
                fetcher=request_fetcher,
                ai_client=ai_client,
                storage=storage,
                confidence_threshold=confidence_threshold,
                image_fields=req.image_fields,
                parallel_extract=req.parallel_extract,
                on_progress=on_progress,
            )
            if file_result.status in ("fetch_failed", "extract_failed"):
                _log_manual_crawl_failure(storage, req.url, file_result.status, file_result.detail)
                raise HTTPException(status_code=502, detail=file_result.detail or file_result.status)
            if file_result.status == "invalid_file_config":
                raise HTTPException(status_code=400, detail=file_result.detail)
            return CrawlResponse(
                status=file_result.status,
                file_path=file_result.file_path,
                data=file_result.data,
                confidence=file_result.confidence,
                needs_review=file_result.needs_review,
                record_count=file_result.record_count,
                detail=file_result.detail,
            )

        if not req.dataset_id and not req.dataset_name:
            raise HTTPException(
                status_code=422, detail="cần dataset_id (thêm vào dataset có sẵn) hoặc dataset_name (tạo mới)"
            )

        result = run_crawl_job(
            url=req.url,
            field_descriptions=req.field_descriptions,
            dataset_id=req.dataset_id,
            dataset_name=req.dataset_name,
            fetcher=request_fetcher,
            ai_client=ai_client,
            storage=storage,
            confidence_threshold=confidence_threshold,
            image_fields=req.image_fields,
            parallel_extract=req.parallel_extract,
            on_progress=on_progress,
        )

        if result.status == "dataset_not_found":
            raise HTTPException(status_code=404, detail=result.detail)
        if result.status == "schema_mismatch":
            raise HTTPException(status_code=409, detail=result.detail)
        if result.status in ("fetch_failed", "extract_failed"):
            _log_manual_crawl_failure(storage, req.url, result.status, result.detail)
            raise HTTPException(status_code=502, detail=result.detail or result.status)

        return CrawlResponse(
            status=result.status,
            dataset_id=result.dataset.dataset_id if result.dataset else None,
            record_id=result.record.record_id if result.record else None,
            data=result.record.data if result.record else None,
            confidence=result.record.confidence if result.record else None,
            needs_review=result.record.needs_review if result.record else None,
            record_count=result.record_count,
            detail=result.detail,
        )

    @app.exception_handler(RequestValidationError)
    async def safe_validation(request, exc):
        return JSONResponse(status_code=422, content={"detail": [
            {"loc": list(error["loc"]), "type": error["type"]} for error in exc.errors()]})

    app.include_router(create_report_router(storage))
    from .feedback import create_feedback_router
    app.include_router(create_feedback_router(
        storage, ai_debug_base_url=ai_debug_base_url, ai_debug_api_key=ai_debug_api_key,
        ai_debug_model=ai_debug_model, ai_debug_timeout_seconds=ai_debug_timeout_seconds,
    ))
    from .dataset_export import create_export_router
    app.include_router(create_export_router(storage))

    @app.post("/crawl")
    def crawl(req: CrawlRequest, response: Response):
        return crawl_impl(req, response)

    @app.get("/crawl-progress/{progress_id}")
    def crawl_progress(progress_id: str):
        """Tiến độ của 1 lượt /crawl đang chạy (giai đoạn tải/làm sạch/AI/lưu, đoạn AI đã xong/tổng, đang chờ hạn
        mức). Chỉ nhãn + số đếm — không có nội dung trang hay dữ liệu."""
        if not PROGRESS_ID_PATTERN.match(progress_id):
            raise HTTPException(status_code=404, detail="Không có tiến độ")
        data = progress_store.get(progress_id)
        if data is None:
            raise HTTPException(status_code=404, detail="Không có tiến độ")
        return data

    @app.post("/crawl-jobs", status_code=202)
    def submit_crawl(req: CrawlBatchRequest):
        if any(item.crawl_options is None for item in req.requests):
            raise HTTPException(400, "Chạy nền hiện dành cho kéo nhiều lượt / bảng")
        def destination(item):
            return (item.storage_mode, item.dataset_id, item.dataset_name, item.file_path, tuple(sorted(item.field_descriptions)))
        if any(destination(item) != destination(req.requests[0]) for item in req.requests):
            raise HTTPException(400, "Các nguồn trong một đợt phải dùng cùng dataset/file và schema")

        def execute(checkpoint, progress):
            items = []
            dataset_id = None
            for index, item in enumerate(req.requests, 1):
                if not checkpoint():
                    return {"status": "cancelled", "items": items, "dataset_id": dataset_id}
                progress({"source_index": index, "sources": len(req.requests), "processed": 0, "failed": 0})
                if not item.dataset_id and dataset_id and item.storage_mode == "db":
                    item = item.model_copy(update={"dataset_id": dataset_id})
                try:
                    result = crawl_impl(item, Response(), checkpoint=checkpoint, progress=progress)
                except HTTPException as exc:
                    result = {"status": "error", "failed": 1, "detail": "Nguồn này gặp lỗi; xem mã lượt kéo để báo admin",
                              "request_id": (exc.headers or {}).get("X-Crawl-Request-ID")}
                items.append({"url": item.url, **result})
                if item.storage_mode == "db":
                    dataset_id = result.get("dataset_id") or dataset_id
                if result.get("status") == "cancelled":
                    break
            status = "cancelled" if items and items[-1]["status"] == "cancelled" else "partial" if any(i.get("failed") for i in items) else "completed"
            return {"status": status, "items": items, "dataset_id": dataset_id}

        try:
            return crawl_tasks.submit(execute)
        except QueueFull as exc:
            raise HTTPException(429, str(exc)) from None

    @app.get("/crawl-jobs/{job_id}")
    def crawl_job_status(job_id: str, control: str | None = Header(default=None, alias="X-Crawl-Control")):
        try:
            return crawl_tasks.status(job_id, control)
        except TaskNotFound:
            raise HTTPException(404, "Không tìm thấy đợt crawl hoặc mã điều khiển không hợp lệ") from None

    @app.post("/crawl-jobs/{job_id}/control")
    def control_crawl(job_id: str, req: CrawlControlRequest,
                      control: str | None = Header(default=None, alias="X-Crawl-Control")):
        try:
            return crawl_tasks.action(job_id, control, req.action)
        except TaskNotFound:
            raise HTTPException(404, "Không tìm thấy đợt crawl hoặc mã điều khiển không hợp lệ") from None

    @app.post("/crawl/preview")
    def preview(req: CrawlRequest, response: Response):
        return crawl_impl(req, response, preview=True)

    def crawl_impl(req: CrawlRequest, response: Response, preview=False, checkpoint=None, progress=None):
        request_id = str(uuid4())
        headers = {"X-Crawl-Request-ID": request_id}
        response.headers.update(headers)
        metadata = context(req.url, req.field_descriptions, req.storage_mode)
        fingerprint = hashlib.sha256(json.dumps(req.model_dump(mode="json", exclude={
            "cookie_header", "cookie_origin", "dataset_id", "dataset_name", "retry_of", "progress_id"}),
            sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        metadata.update(config_fingerprint=fingerprint, operation="preview" if preview else "crawl")
        if req.retry_of:
            metadata["retry_of"] = str(req.retry_of)
        if req.crawl_options:
            metadata["crawl_options"] = req.crawl_options.model_dump(mode="json", exclude={"table_selector"})
        storage.add_audit_log("crawl_request", job_id=request_id, detail=metadata)
        if progress:
            progress({"request_id": request_id})
        # Job nền: dùng dict tiến độ của job; /crawl thường: dùng kho tiến độ theo progress_id do UI gửi.
        on_progress = progress or (progress_store.reporter(req.progress_id) if req.progress_id else None)
        try:
            retry_indices = None
            if req.retry_of:
                if preview or not req.crawl_options or req.crawl_options.mode != "table" or req.storage_mode != "db":
                    raise HTTPException(400, "Chỉ chạy lại lượt lỗi cho bảng lưu DB")
                entries = storage.list_audit_log(job_id=str(req.retry_of), limit=100)
                parent = next((e.detail for e in entries if e.event_type == "crawl_request"), {})
                outcome = next((e.detail for e in entries if e.event_type == "crawl_outcome"), {})
                if (parent.get("config_fingerprint") != fingerprint or parent.get("operation") != "crawl"
                        or not req.dataset_id or req.dataset_id != outcome.get("dataset_id")):
                    raise HTTPException(409, "Cấu hình hoặc dataset đã đổi; không thể chạy lại đợt cũ")
                retry_indices = [item["index"] for item in outcome.get("results") or []
                                 if item.get("status") not in {"saved", "unchanged", "empty"}]
                if not retry_indices:
                    raise HTTPException(409, "Đợt được chọn không có lượt lỗi để chạy lại")
            request_fetcher = fetcher
            if req.cookie_header:
                cookie = req.cookie_header.get_secret_value()
                origin = urlsplit(req.cookie_origin or "")
                target = urlsplit(req.url)
                if (not cookie or len(cookie) > 16384 or "\r" in cookie or "\n" in cookie
                    or origin.scheme not in {"http", "https"} or not origin.hostname
                    or origin[:2] != target[:2] or target.username or target.password):
                    raise HTTPException(400, "Invalid cookie or cookie origin")
                if not hasattr(fetcher, "with_request_cookie"):
                    raise HTTPException(400, "Fetcher does not support per-request cookies")
                request_fetcher = fetcher.with_request_cookie(req.url, cookie)
            if req.ignore_robots:
                reason = (req.ignore_robots_reason or "").strip()
                if len(reason) < 5:
                    raise HTTPException(400, "Bỏ qua robots.txt phải kèm lý do (tối thiểu 5 ký tự)")
                if not hasattr(request_fetcher, "with_robots_ignored"):
                    raise HTTPException(400, "Fetcher không hỗ trợ bỏ qua robots.txt theo request")
                logger.warning("Người dùng yêu cầu BỎ QUA robots.txt cho %s. Lý do: %s", req.url, reason)
                request_fetcher = request_fetcher.with_robots_ignored(domain_of(req.url), reason)
            if req.crawl_options:
                if not req.field_descriptions or req.storage_mode not in {"db", "file"}:
                    raise HTTPException(400, "Fields and valid storage mode required")
                if req.storage_mode == "file":
                    _validate_file_storage_config(req.file_path, req.write_mode, req.key_field, req.field_descriptions)
                try:
                    if preview:
                        result = preview_bulk(url=req.url, options=req.crawl_options,
                            field_descriptions=req.field_descriptions, fetcher=request_fetcher,
                            storage_mode=req.storage_mode, write_mode=req.write_mode or "append", image_fields=req.image_fields)
                    else:
                        result = run_bulk(url=req.url, field_descriptions=req.field_descriptions,
                            options=req.crawl_options, fetcher=request_fetcher, ai_client=ai_client, storage=storage,
                            dataset_id=req.dataset_id, dataset_name=req.dataset_name, storage_mode=req.storage_mode,
                            file_path=req.file_path, write_mode=req.write_mode or "append", image_fields=req.image_fields,
                            confidence_threshold=confidence_threshold, retry_indices=retry_indices,
                            checkpoint=checkpoint, progress=progress, parallel_extract=req.parallel_extract,
                            on_progress=on_progress)
                except ValueError as exc:
                    raise HTTPException(400, str(exc)) from None
            else:
                if preview:
                    raise HTTPException(400, "Bật kéo nhiều lượt / kéo bảng để xem trước")
                result = crawl_one(req, request_fetcher, on_progress).model_dump()
            storage.add_audit_log("crawl_outcome", job_id=request_id,
                                  detail={key: result.get(key) for key in ("status", "dataset_id", "saved", "skipped", "failed", "results")})
            return {**result, "request_id": request_id}
        except HTTPException as exc:
            storage.add_audit_log("crawl_outcome", job_id=request_id, detail={"status": "error", "http_status": exc.status_code})
            exc.headers = {**(exc.headers or {}), **headers}
            raise
        except Exception as exc:
            storage.add_audit_log("crawl_outcome", job_id=request_id,
                                  detail={"status": "error", "error_type": type(exc).__name__, "frames": exception_frames(exc)})
            raise HTTPException(500, "Crawl failed; send request ID to admin", headers=headers) from None

    @app.get("/datasets")
    def list_datasets() -> list[dict]:
        return [dataclasses.asdict(d) for d in storage.list_datasets()]

    @app.get("/datasets/{dataset_id}/records")
    def list_records(dataset_id: str, limit: int = 100, offset: int = 0) -> list[dict]:
        if storage.get_dataset(dataset_id) is None:
            raise HTTPException(status_code=404, detail="dataset không tồn tại")
        return [dataclasses.asdict(r) for r in storage.list_records(dataset_id, limit, offset)]

    @app.get("/exports/{file_path:path}")
    def download_export(file_path: str) -> FileResponse:
        try:
            resolved = resolve_export_path(file_path)
        except InvalidFilePathError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not resolved.exists() or not resolved.is_file():
            raise HTTPException(status_code=404, detail="file không tồn tại")
        return FileResponse(str(resolved), media_type="application/json", filename=resolved.name)

    @app.get("/images/{file_path:path}")
    def download_image_file(file_path: str) -> FileResponse:
        try:
            resolved = resolve_export_path(file_path, exports_root=IMAGES_ROOT)
        except InvalidFilePathError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not resolved.exists() or not resolved.is_file():
            raise HTTPException(status_code=404, detail="ảnh không tồn tại")
        return FileResponse(str(resolved), filename=resolved.name)

    @app.post("/schedules")
    def create_schedule(req: ScheduleCreateRequest) -> dict:
        try:
            validate_trigger(req.trigger_type, req.trigger_args)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        if req.crawl_options:
            try:
                plan_urls(req.url, req.crawl_options)
                if req.crawl_options.start_date:
                    raise ValueError("Schedules require a rolling window")
                if req.crawl_options.mode == "table" and set(req.crawl_options.columns) != set(req.field_descriptions):
                    raise ValueError("Invalid columns")
                if req.crawl_options.date_field and req.crawl_options.date_field not in req.crawl_options.columns:
                    raise ValueError("Invalid date field")
                if req.image_fields and req.crawl_options.mode == "table":
                    raise ValueError("Table image downloads unsupported")
                if req.storage_mode == "file" and req.write_mode != "append":
                    raise ValueError("Bulk file schedules require append")
            except ValueError:
                raise HTTPException(400, "Invalid bulk schedule configuration")
        if req.storage_mode not in ("db", "file"):
            raise HTTPException(status_code=400, detail="storage_mode phải là 'db' hoặc 'file'")

        if req.storage_mode == "file":
            _validate_file_storage_config(req.file_path, req.write_mode, req.key_field, req.field_descriptions)
            job = crawl_scheduler.add_job(
                dataset_id=None,
                url=req.url,
                field_descriptions=req.field_descriptions,
                trigger_type=req.trigger_type,
                trigger_args=req.trigger_args,
                storage_mode="file",
                file_path=req.file_path,
                write_mode=req.write_mode,
                key_field=req.key_field,
                image_fields=req.image_fields,
                crawl_options=req.crawl_options.model_dump(mode="json") if req.crawl_options else None,
            )
            return dataclasses.asdict(job)

        if not req.dataset_id:
            raise HTTPException(status_code=422, detail="cần dataset_id khi storage_mode='db'")
        dataset = storage.get_dataset(req.dataset_id)
        if dataset is None:
            raise HTTPException(status_code=404, detail="dataset không tồn tại")
        if sorted(req.field_descriptions.keys()) != dataset.schema_signature:
            raise HTTPException(
                status_code=409,
                detail="field_descriptions không khớp schema_signature của dataset đã chọn",
            )

        job = crawl_scheduler.add_job(
            dataset_id=req.dataset_id,
            url=req.url,
            field_descriptions=req.field_descriptions,
            trigger_type=req.trigger_type,
            trigger_args=req.trigger_args,
            image_fields=req.image_fields,
                crawl_options=req.crawl_options.model_dump(mode="json") if req.crawl_options else None,
        )
        return dataclasses.asdict(job)

    @app.get("/schedules")
    def list_schedules() -> list[dict]:
        return [crawl_scheduler.describe(job) for job in storage.list_scheduled_jobs()]

    @app.patch("/schedules/{job_id}")
    def update_schedule(job_id: str, req: ScheduleUpdateRequest):
        try:
            job = crawl_scheduler.configure(job_id, req.enabled, req.trigger_type, req.trigger_args)
            return crawl_scheduler.describe(job)
        except LookupError:
            raise HTTPException(404, "Không tìm thấy lịch") from None
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None

    @app.delete("/schedules/{job_id}")
    def delete_schedule(job_id: str) -> dict:
        if storage.get_scheduled_job(job_id) is None:
            raise HTTPException(status_code=404, detail="job không tồn tại")
        crawl_scheduler.remove_job(job_id)
        return {"status": "deleted", "job_id": job_id}

    # Panel admin nội bộ ("AI gợi ý sửa lỗi") — xem docstring src/api/admin.py.
    app.include_router(
        create_admin_router(
            session_admin_check=_runner_admin_checker(runner_service),
            storage=storage,
            ai_debug_base_url=ai_debug_base_url,
            ai_debug_api_key=ai_debug_api_key,
            ai_debug_model=ai_debug_model,
            ai_debug_timeout_seconds=ai_debug_timeout_seconds,
            admin_username=admin_username,
            admin_password=admin_password,
        )
    )

    return app


def _runner_admin_checker(runner_service):
    """Đăng nhập admin chung: token phiên Runner của user role=admin dùng được cho /admin/*."""
    if runner_service is None:
        return None

    def check(token: str) -> bool:
        try:
            with runner_service.repo.transaction():
                return runner_service.authenticate(token)["role"] == "admin"
        except Exception:
            return False

    return check


def _build_default_app() -> FastAPI:
    settings = load_settings()
    # QUAN TRỌNG: LOG_LEVEL trong .env chỉ có tác dụng nếu logging được cấu
    # hình ở đây — thiếu dòng này thì MỌI logger.info() trong app (log tiến
    # trình crawl ở src/pipeline.py, cảnh báo ở các module khác) bị nuốt mất,
    # không hiện ra console/`docker compose logs` dù code đã gọi log đầy đủ.
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    storage = _build_storage(settings)
    # FETCH_RESPECT_ROBOTS_TXT=false (dev/test khi backend không tải được
    # robots.txt thật do hạn chế mạng) -> AllowAllRobotsChecker tường minh.
    # Trước đây biến này được đọc vào Settings nhưng KHÔNG BAO GIỜ dùng tới —
    # fetcher luôn fail-closed theo HttpRobotsChecker() mặc định dù người
    # dùng đã set false trong .env (xem docs/kien_audit/03 mục 2.6).
    robots_checker = None  # None = HttpRobotsChecker() mặc định (luôn kiểm tra)
    if not settings.fetch_respect_robots_txt:
        from ..fetch.base import AllowAllRobotsChecker
        logging.getLogger(__name__).warning(
            "FETCH_RESPECT_ROBOTS_TXT=false: TOÀN BỘ crawl sẽ BỎ QUA robots.txt. "
            "Chỉ dùng cho dev/test; production nên để true và bật bỏ qua theo từng "
            "request (có lý do, có log) qua ignore_robots."
        )
        robots_checker = AllowAllRobotsChecker()
    chrome_path = os.environ.get("CHROME_EXECUTABLE_PATH", "") or None
    # FETCH_ENGINE: playwright (mặc định — render JS, đúng cho site như vietstock),
    # hybrid (httpx trước, fallback Playwright khi 403/HTML rỗng) hoặc httpx.
    # Mọi engine dùng chung robots checker + rate limit theo domain.
    engine = os.environ.get("FETCH_ENGINE", "playwright").strip().lower()
    httpx_fetcher = HttpxFetcher(
        user_agent=settings.fetch_user_agent,
        delay_seconds=settings.fetch_default_delay_seconds,
        robots_checker=robots_checker,
    )
    fetcher = httpx_fetcher
    if engine in {"playwright", "hybrid"}:
        try:
            from ..fetch.playwright_fetcher import PlaywrightFetcher
            playwright_fetcher = PlaywrightFetcher(
                user_agent=settings.fetch_user_agent,
                delay_seconds=settings.fetch_default_delay_seconds,
                robots_checker=robots_checker,
                timeout_seconds=60.0,
                chrome_executable_path=chrome_path,
            )
            fetcher = (HybridFetcher(httpx_fetcher, playwright_fetcher)
                       if engine == "hybrid" else playwright_fetcher)
        except Exception:
            logging.getLogger(__name__).exception("Không khởi tạo được Playwright — dùng httpx")
    rate_limiter = ModelRateLimiter(settings.ai_model_limits)
    logging.getLogger(__name__).info(
        "Hạn mức AI theo model (AI_MODEL_LIMITS): %s", settings.ai_model_limits or "chưa cấu hình (chỉ dùng header API)"
    )
    ai_client = GreenNodeChatClient(
        base_url=settings.ai_base_url,
        api_key=settings.ai_api_key,
        model=settings.ai_model,
        timeout_seconds=settings.ai_timeout_seconds,
        rate_limiter=rate_limiter,
    )
    if not settings.admin_username or not settings.admin_password:
        logging.getLogger(__name__).warning(
            "ADMIN_USERNAME/ADMIN_PASSWORD chưa cấu hình trong .env — panel admin (/admin/*) "
            "sẽ từ chối MỌI request (401) cho tới khi cấu hình."
        )
    runner_service = None
    runner_planner = None
    if settings.runner_enabled:
        from ..runner.repository import Repository
        from ..runner.service import Service
        runner_service = Service(Repository(settings.runner_db_path,
                                           postgres_dsn=settings.runner_database_url or None),
                                 settings.runner_data_root)
        if settings.runner_ai_enabled:
            # RUNNER_AI_MODEL cho phép Runner dùng model riêng; trống = dùng chung AI_MODEL.
            runner_model = settings.runner_ai_model or settings.ai_model
            if not all((settings.ai_base_url, settings.ai_api_key, runner_model)):
                raise ValueError("Runner Describe requires AI configuration")
            from ..runner.planner import StepPlanner
            runner_planner = StepPlanner(settings.ai_base_url, settings.ai_api_key,
                                         runner_model, settings.ai_timeout_seconds)
    return create_app(
        fetcher=fetcher,
        ai_client=ai_client,
        storage=storage,
        ai_debug_base_url=settings.ai_debug_base_url,
        ai_debug_api_key=settings.ai_debug_api_key,
        ai_debug_model=settings.ai_debug_model,
        ai_debug_timeout_seconds=settings.ai_debug_timeout_seconds,
        confidence_threshold=settings.ai_confidence_threshold,
        admin_username=settings.admin_username,
        admin_password=settings.admin_password,
        runner_service=runner_service,
        runner_planner=runner_planner,
    )


def _build_storage(settings) -> StorageEngine:
    """`DB_BACKEND` chọn "sqlite" (mặc định, dev/MVP) hay "postgres"
    (production — vd. GreenNode có Postgres managed). Cả 2 cùng implement
    `StorageEngine`, tầng gọi (`create_app`) không cần biết đang dùng backend
    nào (adapter pattern, CLAUDE.md mục 6)."""
    if settings.db_backend == "postgres":
        if not settings.database_url:
            raise ValueError("DB_BACKEND=postgres nhưng thiếu DATABASE_URL trong .env")
        return PostgresStorage(settings.database_url)
    if settings.db_backend != "sqlite":
        raise ValueError(f"DB_BACKEND không hợp lệ: {settings.db_backend!r} (chỉ nhận 'sqlite' hoặc 'postgres')")
    return SQLiteStorage(settings.db_path)


app = _build_default_app()
