"""Anonymous write-only reports, linked to server crawl audits. No raw exceptions or cookies."""
import re
from typing import Annotated, Literal
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field


def safe_url(url):
    try:
        parts = urlsplit(url)
        path = re.sub(r"[A-Za-z0-9_-]{24,}", "[REDACTED]", parts.path)
        return urlunsplit((parts.scheme, parts.hostname or "", path[:500], "", ""))
    except ValueError:
        return "invalid_url"


def context(url, fields, mode):
    return {"url": safe_url(url), "fields": [re.sub(r"[^\w -]", "_", str(key))[:80] for key in list(fields)[:50]],
            "storage_mode": mode if mode in {"db", "file"} else "unknown"}


def exception_frames(error):
    frames = []
    traceback = error.__traceback__
    while traceback and len(frames) < 12:
        name = traceback.tb_frame.f_code.co_filename.replace("\\", "/")
        # No source lines, locals or exception text.
        for prefix in ("/src/", "/ui/"):
            if prefix in name:
                frames.append({"file": prefix[1:] + name.rsplit(prefix, 1)[1], "line": traceback.tb_lineno})
                break
        traceback = traceback.tb_next
    return frames


class Frame(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file: Literal["ui/crawl.py"]
    line: int = Field(ge=1, le=100000)


class Report(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID | None = None
    error_type: Literal["TypeError", "ValueError", "KeyError", "IndexError", "AttributeError", "HTTPError", "RuntimeError", "Other", "WrongResult"] = "Other"
    ui_step: int = Field(ge=1, le=5)
    frames: list[Frame] = Field(default_factory=list, max_length=12)
    url: str = Field(default="", max_length=2000)
    fields: list[Annotated[str, Field(max_length=80)]] = Field(default_factory=list, max_length=50)
    storage_mode: Literal["db", "file"] = "db"


def create_report_router(storage):
    router = APIRouter()
    @router.post("/crawl-reports", status_code=201)
    def report(req: Report):
        request_id = str(req.request_id) if req.request_id else None
        entries = storage.list_audit_log(job_id=request_id, limit=20) if request_id else []
        requests = [entry for entry in entries if entry.event_type == "crawl_request"]
        if request_id and not requests:
            raise HTTPException(404, "Không tìm thấy lượt crawl; hãy báo lỗi không kèm mã lượt kéo.")
        detail = {"request_id": request_id, "context": requests[0].detail if requests else context(req.url, req.fields, req.storage_mode),
                  "client_error_type": req.error_type, "ui_step": req.ui_step,
                  "client_frames": [frame.model_dump() for frame in req.frames],
                  "outcomes": [entry.detail for entry in entries if entry.event_type == "crawl_outcome"],
                  "client_claim_unverified": True}
        saved = storage.add_audit_log("user_crawl_report", job_id=request_id, detail=detail)
        return {"report_id": saved.id, "status": "received"}
    return router
