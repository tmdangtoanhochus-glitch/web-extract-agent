"""CSV export of append-only datasets, bounded memory and no temporary files."""
import csv
import io
import json
from datetime import date, datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse


def csv_cell(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    text = str(value)
    # Untrusted web content must remain text when opened in a spreadsheet.
    if isinstance(value, str) and text.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def export_csv(storage, dataset, cutoff, date_basis="crawled_at", start=None, end=None, page_size=500):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    fields = dataset.schema_signature

    def row(values):
        buffer.seek(0)
        buffer.truncate(0)
        writer.writerow([csv_cell(value) for value in values])
        return buffer.getvalue().encode("utf-8")

    after = None
    count = 0
    complete = False
    try:
        yield b"\xef\xbb\xbf" + row(["meta.record_id", "meta.source_url", "meta.crawled_at",
            "meta.as_of", "meta.confidence", "meta.needs_review"] + [f"data.{field}" for field in fields])
        while True:
            records = storage.export_record_page(dataset.dataset_id, cutoff, after, page_size)
            if not records:
                break
            chunk = []
            for record in records:
                timestamp = getattr(record, date_basis)
                if start or end:
                    if timestamp is None:
                        continue
                    day = timestamp.astimezone(timezone.utc).date()
                    if (start and day < start) or (end and day > end):
                        continue
                count += 1
                chunk.append(row([record.record_id, record.source_url, record.crawled_at.isoformat(),
                    record.as_of.isoformat() if record.as_of else None, record.confidence, record.needs_review]
                    + [record.data.get(field) for field in fields]))
            if chunk:
                yield b"".join(chunk)
            last = records[-1]
            after = (last.crawled_at, last.record_id)
            if len(records) < page_size:
                break
        complete = True
    finally:
        storage.add_audit_log("dataset_csv_export", detail={"dataset_id": dataset.dataset_id,
            "cutoff": cutoff.isoformat(), "date_basis": date_basis,
            "start": start.isoformat() if start else None, "end": end.isoformat() if end else None,
            "records": count, "complete": complete})


def create_export_router(storage):
    router = APIRouter()

    @router.get("/datasets/{dataset_id}/export.csv")
    def download(dataset_id: str, date_basis: Literal["crawled_at", "as_of"] = "crawled_at",
                 start: date | None = None, end: date | None = None):
        dataset = storage.get_dataset(dataset_id)
        if dataset is None:
            raise HTTPException(404, "Dataset không tồn tại")
        if start and end and start > end:
            raise HTTPException(400, "Ngày bắt đầu phải trước ngày kết thúc")
        cutoff = datetime.now(timezone.utc)
        return StreamingResponse(export_csv(storage, dataset, cutoff, date_basis, start, end),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="dataset.csv"',
                     "X-Export-Cutoff": cutoff.isoformat(), "Cache-Control": "no-store"})

    return router
