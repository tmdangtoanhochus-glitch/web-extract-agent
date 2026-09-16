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
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..ai.base import AIClient
from ..ai.greennode_client import GreenNodeChatClient
from ..config import load_settings
from ..fetch.base import FetchEngine
from ..fetch.httpx_fetcher import HttpxFetcher
from ..pipeline import run_crawl_job, run_file_crawl_job
from ..scheduler import CrawlScheduler
from ..storage.base import StorageEngine
from ..storage.file_writer import InvalidFilePathError, resolve_export_path
from ..storage.image_downloader import IMAGES_ROOT
from ..storage.postgres_storage import PostgresStorage
from ..storage.sqlite_storage import SQLiteStorage
from .admin import create_admin_router

_VALID_WRITE_MODES = ("append", "new_file", "overwrite_row")


class CrawlRequest(BaseModel):
    url: str
    field_descriptions: dict[str, str]
    dataset_id: Optional[str] = None
    dataset_name: Optional[str] = None
    storage_mode: str = "db"  # "db" | "file"
    file_path: Optional[str] = None
    write_mode: Optional[str] = None  # "append" | "new_file" | "overwrite_row"
    key_field: Optional[str] = None
    image_fields: list[str] = []  # field nào là ảnh cần tải về, xem image_downloader.py


class CrawlResponse(BaseModel):
    status: str
    dataset_id: Optional[str] = None
    record_id: Optional[str] = None
    file_path: Optional[str] = None
    data: Optional[dict] = None
    confidence: Optional[float] = None
    needs_review: Optional[bool] = None
    detail: Optional[str] = None


class ScheduleCreateRequest(BaseModel):
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
            if retention_scheduler is not None:
                retention_scheduler.shutdown(wait=True)
            crawl_scheduler.shutdown()

    app = FastAPI(title="Web Data Extraction & Management Platform", lifespan=_lifespan)
    if runner_service is not None:
        from .runner import create_runner_router
        from ..runner.service import RunnerError
        from fastapi.responses import JSONResponse

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

    @app.post("/crawl", response_model=CrawlResponse)
    def crawl(req: CrawlRequest) -> CrawlResponse:
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
                fetcher=fetcher,
                ai_client=ai_client,
                storage=storage,
                confidence_threshold=confidence_threshold,
                image_fields=req.image_fields,
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
            fetcher=fetcher,
            ai_client=ai_client,
            storage=storage,
            confidence_threshold=confidence_threshold,
            image_fields=req.image_fields,
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
        )

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
        )
        return dataclasses.asdict(job)

    @app.get("/schedules")
    def list_schedules() -> list[dict]:
        return [dataclasses.asdict(job) for job in storage.list_scheduled_jobs()]

    @app.delete("/schedules/{job_id}")
    def delete_schedule(job_id: str) -> dict:
        if storage.get_scheduled_job(job_id) is None:
            raise HTTPException(status_code=404, detail="job không tồn tại")
        crawl_scheduler.remove_job(job_id)
        return {"status": "deleted", "job_id": job_id}

    # Panel admin nội bộ ("AI gợi ý sửa lỗi") — xem docstring src/api/admin.py.
    app.include_router(
        create_admin_router(
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
    fetcher = HttpxFetcher(
        user_agent=settings.fetch_user_agent,
        delay_seconds=settings.fetch_default_delay_seconds,
        # Cookie đăng nhập thủ công theo domain (người dùng tự lưu qua panel
        # admin) — KHÔNG tự động đăng nhập, chỉ tra cứu + gắn header nếu đã
        # có sẵn cho domain của URL đang fetch (xem HttpxFetcher docstring).
        credential_provider=lambda domain: (
            (cred := storage.get_site_credential(domain)) and cred.cookie_header
        ),
    )
    ai_client = GreenNodeChatClient(
        base_url=settings.ai_base_url,
        api_key=settings.ai_api_key,
        model=settings.ai_model,
        timeout_seconds=settings.ai_timeout_seconds,
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
            if not all((settings.ai_base_url, settings.ai_api_key, settings.ai_model)):
                raise ValueError("Runner Describe requires AI configuration")
            from ..runner.planner import StepPlanner
            runner_planner = StepPlanner(settings.ai_base_url, settings.ai_api_key,
                                         settings.ai_model, settings.ai_timeout_seconds)
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
