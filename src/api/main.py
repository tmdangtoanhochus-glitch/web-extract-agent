"""FastAPI backend — MVP tối giản: 1 endpoint crawl + 2 endpoint xem kết quả
(CLAUDE.md: "ưu tiên chạy được bản MVP tối giản — crawl 1 site tĩnh, lưu DB,
xem log — trước khi mở rộng").

`create_app()` nhận sẵn fetcher/ai_client/storage (dependency injection) để
test được mà không cần chạy thật (CLAUDE.md mục 6) — `app` ở cuối file mới là
instance thật, dùng khi chạy `uvicorn src.api.main:app`.
"""
from __future__ import annotations

import dataclasses
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ..ai.base import AIClient
from ..ai.greennode_client import GreenNodeChatClient
from ..config import load_settings
from ..fetch.base import FetchEngine
from ..fetch.httpx_fetcher import HttpxFetcher
from ..pipeline import run_crawl_job
from ..storage.base import StorageEngine
from ..storage.sqlite_storage import SQLiteStorage


class CrawlRequest(BaseModel):
    url: str
    field_descriptions: dict[str, str]
    dataset_id: Optional[str] = None
    dataset_name: Optional[str] = None


class CrawlResponse(BaseModel):
    status: str
    dataset_id: Optional[str] = None
    record_id: Optional[str] = None
    data: Optional[dict] = None
    confidence: Optional[float] = None
    detail: Optional[str] = None


def create_app(fetcher: FetchEngine, ai_client: AIClient, storage: StorageEngine) -> FastAPI:
    app = FastAPI(title="Web Data Extraction & Management Platform")

    @app.post("/crawl", response_model=CrawlResponse)
    def crawl(req: CrawlRequest) -> CrawlResponse:
        if not req.field_descriptions:
            raise HTTPException(status_code=422, detail="field_descriptions không được rỗng")
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
        )

        if result.status == "dataset_not_found":
            raise HTTPException(status_code=404, detail=result.detail)
        if result.status == "schema_mismatch":
            raise HTTPException(status_code=409, detail=result.detail)
        if result.status in ("fetch_failed", "extract_failed"):
            raise HTTPException(status_code=502, detail=result.detail or result.status)

        return CrawlResponse(
            status=result.status,
            dataset_id=result.dataset.dataset_id if result.dataset else None,
            record_id=result.record.record_id if result.record else None,
            data=result.record.data if result.record else None,
            confidence=result.record.confidence if result.record else None,
        )

    @app.get("/datasets")
    def list_datasets() -> list[dict]:
        return [dataclasses.asdict(d) for d in storage.list_datasets()]

    @app.get("/datasets/{dataset_id}/records")
    def list_records(dataset_id: str, limit: int = 100, offset: int = 0) -> list[dict]:
        if storage.get_dataset(dataset_id) is None:
            raise HTTPException(status_code=404, detail="dataset không tồn tại")
        return [dataclasses.asdict(r) for r in storage.list_records(dataset_id, limit, offset)]

    return app


def _build_default_app() -> FastAPI:
    settings = load_settings()
    fetcher = HttpxFetcher(user_agent=settings.fetch_user_agent)
    ai_client = GreenNodeChatClient(
        base_url=settings.ai_base_url,
        api_key=settings.ai_api_key,
        model=settings.ai_model,
        timeout_seconds=settings.ai_timeout_seconds,
    )
    storage = SQLiteStorage(settings.db_path)
    return create_app(fetcher=fetcher, ai_client=ai_client, storage=storage)


app = _build_default_app()
