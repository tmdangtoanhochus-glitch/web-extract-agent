"""Implementation StorageEngine dùng SQLite — mặc định cho dev/MVP
(CLAUDE.md — nâng lên Postgres/MySQL sau nếu cần, không bắt buộc ngay)."""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime
from typing import Any, Optional

from .base import (
    AuditLogEntry,
    Dataset,
    DatasetSource,
    ExtractionStrategy,
    Record,
    ScheduledJob,
    SiteCredential,
    StorageEngine,
    utcnow,
)

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS datasets (
    dataset_id TEXT PRIMARY KEY,
    dataset_name TEXT NOT NULL,
    schema_signature TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dataset_sources (
    dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id),
    source_url TEXT NOT NULL,
    active INTEGER NOT NULL,
    added_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS records (
    record_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id),
    source_url TEXT NOT NULL,
    data TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    evidence TEXT,
    confidence REAL,
    needs_review INTEGER NOT NULL DEFAULT 0,
    crawled_at TEXT NOT NULL,
    as_of TEXT
);

CREATE TABLE IF NOT EXISTS extraction_strategies (
    domain TEXT NOT NULL,
    field_name TEXT NOT NULL,
    selector TEXT NOT NULL,
    sample_value TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (domain, field_name)
);

CREATE TABLE IF NOT EXISTS scheduled_jobs (
    job_id TEXT PRIMARY KEY,
    dataset_id TEXT REFERENCES datasets(dataset_id),
    url TEXT NOT NULL,
    field_descriptions TEXT NOT NULL,
    storage_mode TEXT NOT NULL DEFAULT 'db',
    file_path TEXT,
    write_mode TEXT,
    key_field TEXT,
    image_fields TEXT,
    trigger_type TEXT NOT NULL,
    trigger_args TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    last_run_at TEXT,
    last_status TEXT,
    last_error_traceback TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    job_id TEXT,
    occurred_at TEXT NOT NULL,
    detail TEXT
);

CREATE TABLE IF NOT EXISTS site_credentials (
    domain TEXT PRIMARY KEY,
    cookie_header TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

# Cột thêm sau này cho các bảng đã tồn tại — dùng để migrate nhẹ các DB cục bộ
# tạo TRƯỚC khi có tính năng liên quan (CREATE TABLE IF NOT EXISTS không tự
# thêm cột mới cho bảng đã tồn tại). LƯU Ý: ràng buộc NOT NULL cũ (vd.
# `scheduled_jobs.dataset_id` trên DB tạo trước tính năng "Lưu ra file") KHÔNG
# được nới lỏng bởi migration này — SQLite không hỗ trợ ALTER COLUMN mà không
# dựng lại bảng; đây là dev DB cục bộ (`.gitignore` chặn `data/*.db`), nếu cần
# xoá file `.db` để tạo lại theo schema mới.
_MIGRATION_COLUMNS: dict[str, dict[str, str]] = {
    "scheduled_jobs": {
        "storage_mode": "TEXT NOT NULL DEFAULT 'db'",
        "file_path": "TEXT",
        "write_mode": "TEXT",
        "key_field": "TEXT",
        "image_fields": "TEXT",
        "last_error_traceback": "TEXT",
    },
    "records": {
        "needs_review": "INTEGER NOT NULL DEFAULT 0",
    },
}


def _normalize_schema(schema_signature: list[str]) -> list[str]:
    """Chuẩn hoá schema_signature để so khớp không phân biệt thứ tự field."""
    return sorted(set(schema_signature))


class SQLiteStorage(StorageEngine):
    def __init__(self, db_path: str = ":memory:") -> None:
        self._db_path = db_path
        if db_path != ":memory:":
            parent_dir = os.path.dirname(db_path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA_SQL)
        self._migrate_columns()
        self._conn.commit()

    def _migrate_columns(self) -> None:
        for table, columns in _MIGRATION_COLUMNS.items():
            existing_columns = {row["name"] for row in self._conn.execute(f"PRAGMA table_info({table})")}
            for column, ddl in columns.items():
                if column not in existing_columns:
                    self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    def close(self) -> None:
        self._conn.close()

    # -- datasets ------------------------------------------------------
    def create_dataset(self, dataset_name: str, schema_signature: list[str]) -> Dataset:
        dataset_id = uuid.uuid4().hex
        created_at = utcnow()
        normalized = _normalize_schema(schema_signature)
        self._conn.execute(
            "INSERT INTO datasets (dataset_id, dataset_name, schema_signature, created_at) "
            "VALUES (?, ?, ?, ?)",
            (dataset_id, dataset_name, json.dumps(normalized), created_at.isoformat()),
        )
        self._conn.commit()
        return Dataset(
            dataset_id=dataset_id,
            dataset_name=dataset_name,
            schema_signature=normalized,
            created_at=created_at,
        )

    def find_dataset_by_schema(self, schema_signature: list[str]) -> Optional[Dataset]:
        normalized = json.dumps(_normalize_schema(schema_signature))
        row = self._conn.execute(
            "SELECT * FROM datasets WHERE schema_signature = ? ORDER BY created_at LIMIT 1",
            (normalized,),
        ).fetchone()
        return _row_to_dataset(row) if row else None

    def get_dataset(self, dataset_id: str) -> Optional[Dataset]:
        row = self._conn.execute(
            "SELECT * FROM datasets WHERE dataset_id = ?", (dataset_id,)
        ).fetchone()
        return _row_to_dataset(row) if row else None

    def list_datasets(self) -> list[Dataset]:
        rows = self._conn.execute("SELECT * FROM datasets ORDER BY created_at").fetchall()
        return [_row_to_dataset(row) for row in rows]

    # -- dataset_sources -------------------------------------------------
    def add_source(self, dataset_id: str, source_url: str) -> DatasetSource:
        added_at = utcnow()
        self._conn.execute(
            "INSERT INTO dataset_sources (dataset_id, source_url, active, added_at) "
            "VALUES (?, ?, 1, ?)",
            (dataset_id, source_url, added_at.isoformat()),
        )
        self._conn.commit()
        return DatasetSource(
            dataset_id=dataset_id, source_url=source_url, active=True, added_at=added_at
        )

    def replace_source(
        self, dataset_id: str, old_source_url: str, new_source_url: str
    ) -> DatasetSource:
        self._conn.execute(
            "UPDATE dataset_sources SET active = 0 "
            "WHERE dataset_id = ? AND source_url = ? AND active = 1",
            (dataset_id, old_source_url),
        )
        added_at = utcnow()
        self._conn.execute(
            "INSERT INTO dataset_sources (dataset_id, source_url, active, added_at) "
            "VALUES (?, ?, 1, ?)",
            (dataset_id, new_source_url, added_at.isoformat()),
        )
        self._conn.commit()
        return DatasetSource(
            dataset_id=dataset_id, source_url=new_source_url, active=True, added_at=added_at
        )

    def list_sources(self, dataset_id: str, active_only: bool = False) -> list[DatasetSource]:
        query = "SELECT * FROM dataset_sources WHERE dataset_id = ?"
        params: list[Any] = [dataset_id]
        if active_only:
            query += " AND active = 1"
        query += " ORDER BY added_at"
        rows = self._conn.execute(query, params).fetchall()
        return [_row_to_source(row) for row in rows]

    # -- records -----------------------------------------------------------
    def save_record(
        self,
        dataset_id: str,
        source_url: str,
        data: dict[str, Any],
        content_hash: str,
        evidence: Optional[dict[str, Any]] = None,
        confidence: Optional[float] = None,
        needs_review: bool = False,
        as_of: Optional[datetime] = None,
    ) -> Record:
        record_id = uuid.uuid4().hex
        crawled_at = utcnow()
        evidence = evidence or {}
        self._conn.execute(
            "INSERT INTO records (record_id, dataset_id, source_url, data, content_hash, "
            "evidence, confidence, needs_review, crawled_at, as_of) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record_id,
                dataset_id,
                source_url,
                json.dumps(data),
                content_hash,
                json.dumps(evidence),
                confidence,
                int(needs_review),
                crawled_at.isoformat(),
                as_of.isoformat() if as_of else None,
            ),
        )
        self._conn.commit()
        return Record(
            record_id=record_id,
            dataset_id=dataset_id,
            source_url=source_url,
            data=data,
            content_hash=content_hash,
            evidence=evidence,
            confidence=confidence,
            needs_review=needs_review,
            crawled_at=crawled_at,
            as_of=as_of,
        )

    def get_latest_record_for_source(self, dataset_id: str, source_url: str) -> Optional[Record]:
        # `rowid` (ngầm định, do TEXT PRIMARY KEY không thay thế nó) dùng làm
        # tiebreaker vì 2 lần save_record() liên tiếp có thể trùng crawled_at
        # (độ phân giải datetime không đủ mịn), khiến ORDER BY crawled_at DESC
        # một mình không xác định thứ tự chèn.
        row = self._conn.execute(
            "SELECT * FROM records WHERE dataset_id = ? AND source_url = ? "
            "ORDER BY crawled_at DESC, rowid DESC LIMIT 1",
            (dataset_id, source_url),
        ).fetchone()
        return _row_to_record(row) if row else None

    def list_records(self, dataset_id: str, limit: int = 100, offset: int = 0) -> list[Record]:
        rows = self._conn.execute(
            "SELECT * FROM records WHERE dataset_id = ? "
            "ORDER BY crawled_at DESC, rowid DESC LIMIT ? OFFSET ?",
            (dataset_id, limit, offset),
        ).fetchall()
        return [_row_to_record(row) for row in rows]

    # -- extraction_strategies (cache CLAUDE.md mục 5) ----------------------
    def get_extraction_strategy(self, domain: str, field_name: str) -> Optional[ExtractionStrategy]:
        row = self._conn.execute(
            "SELECT * FROM extraction_strategies WHERE domain = ? AND field_name = ?",
            (domain, field_name),
        ).fetchone()
        return _row_to_strategy(row) if row else None

    def save_extraction_strategy(
        self, domain: str, field_name: str, selector: str, sample_value: Optional[str] = None
    ) -> ExtractionStrategy:
        updated_at = utcnow()
        self._conn.execute(
            "INSERT INTO extraction_strategies (domain, field_name, selector, sample_value, updated_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(domain, field_name) DO UPDATE SET "
            "selector = excluded.selector, sample_value = excluded.sample_value, "
            "updated_at = excluded.updated_at",
            (domain, field_name, selector, sample_value, updated_at.isoformat()),
        )
        self._conn.commit()
        return ExtractionStrategy(
            domain=domain,
            field_name=field_name,
            selector=selector,
            sample_value=sample_value,
            updated_at=updated_at,
        )

    # -- scheduled_jobs (APScheduler — xem src/scheduler.py) ----------------
    def create_scheduled_job(
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
    ) -> ScheduledJob:
        job_id = uuid.uuid4().hex
        created_at = utcnow()
        image_fields = image_fields or []
        self._conn.execute(
            "INSERT INTO scheduled_jobs (job_id, dataset_id, url, field_descriptions, "
            "storage_mode, file_path, write_mode, key_field, image_fields, "
            "trigger_type, trigger_args, enabled, created_at, last_run_at, last_status, "
            "last_error_traceback) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, NULL, NULL, NULL)",
            (
                job_id,
                dataset_id,
                url,
                json.dumps(field_descriptions),
                storage_mode,
                file_path,
                write_mode,
                key_field,
                json.dumps(image_fields),
                trigger_type,
                json.dumps(trigger_args),
                created_at.isoformat(),
            ),
        )
        self._conn.commit()
        return ScheduledJob(
            job_id=job_id,
            dataset_id=dataset_id,
            url=url,
            field_descriptions=field_descriptions,
            storage_mode=storage_mode,
            file_path=file_path,
            write_mode=write_mode,
            key_field=key_field,
            image_fields=image_fields,
            trigger_type=trigger_type,
            trigger_args=trigger_args,
            enabled=True,
            created_at=created_at,
        )

    def get_scheduled_job(self, job_id: str) -> Optional[ScheduledJob]:
        row = self._conn.execute(
            "SELECT * FROM scheduled_jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        return _row_to_scheduled_job(row) if row else None

    def list_scheduled_jobs(self, enabled_only: bool = False) -> list[ScheduledJob]:
        query = "SELECT * FROM scheduled_jobs"
        if enabled_only:
            query += " WHERE enabled = 1"
        query += " ORDER BY created_at"
        rows = self._conn.execute(query).fetchall()
        return [_row_to_scheduled_job(row) for row in rows]

    def update_scheduled_job_run(
        self, job_id: str, status: str, traceback_text: Optional[str] = None
    ) -> None:
        self._conn.execute(
            "UPDATE scheduled_jobs SET last_run_at = ?, last_status = ?, "
            "last_error_traceback = ? WHERE job_id = ?",
            (utcnow().isoformat(), status, traceback_text, job_id),
        )
        self._conn.commit()

    def delete_scheduled_job(self, job_id: str) -> None:
        self._conn.execute("DELETE FROM scheduled_jobs WHERE job_id = ?", (job_id,))
        self._conn.commit()

    # -- audit_log (panel admin "AI gợi ý sửa lỗi") --------------------------
    def add_audit_log(
        self, event_type: str, job_id: Optional[str] = None, detail: Optional[dict[str, Any]] = None
    ) -> AuditLogEntry:
        entry_id = uuid.uuid4().hex
        occurred_at = utcnow()
        detail = detail or {}
        self._conn.execute(
            "INSERT INTO audit_log (id, event_type, job_id, occurred_at, detail) VALUES (?, ?, ?, ?, ?)",
            (entry_id, event_type, job_id, occurred_at.isoformat(), json.dumps(detail)),
        )
        self._conn.commit()
        return AuditLogEntry(
            id=entry_id, event_type=event_type, job_id=job_id, occurred_at=occurred_at, detail=detail
        )

    def list_audit_log(self, job_id: Optional[str] = None, limit: int = 100) -> list[AuditLogEntry]:
        # `rowid DESC` tiebreaker: 2 lần add_audit_log() liên tiếp có thể trùng
        # occurred_at (độ phân giải datetime không đủ mịn), giống lý do dùng ở
        # `get_latest_record_for_source`/`list_records`.
        query = "SELECT * FROM audit_log"
        params: list[Any] = []
        if job_id is not None:
            query += " WHERE job_id = ?"
            params.append(job_id)
        query += " ORDER BY occurred_at DESC, rowid DESC LIMIT ?"
        params.append(limit)
        rows = self._conn.execute(query, params).fetchall()
        return [_row_to_audit_log(row) for row in rows]

    # -- site_credentials (cookie đăng nhập thủ công theo domain) -----------
    def save_site_credential(self, domain: str, cookie_header: str) -> SiteCredential:
        updated_at = utcnow()
        self._conn.execute(
            "INSERT INTO site_credentials (domain, cookie_header, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(domain) DO UPDATE SET cookie_header = excluded.cookie_header, "
            "updated_at = excluded.updated_at",
            (domain, cookie_header, updated_at.isoformat()),
        )
        self._conn.commit()
        return SiteCredential(domain=domain, cookie_header=cookie_header, updated_at=updated_at)

    def get_site_credential(self, domain: str) -> Optional[SiteCredential]:
        row = self._conn.execute(
            "SELECT * FROM site_credentials WHERE domain = ?", (domain,)
        ).fetchone()
        return _row_to_site_credential(row) if row else None

    def list_site_credentials(self) -> list[SiteCredential]:
        rows = self._conn.execute("SELECT * FROM site_credentials ORDER BY domain").fetchall()
        return [_row_to_site_credential(row) for row in rows]

    def delete_site_credential(self, domain: str) -> None:
        self._conn.execute("DELETE FROM site_credentials WHERE domain = ?", (domain,))
        self._conn.commit()


def _row_to_scheduled_job(row: sqlite3.Row) -> ScheduledJob:
    return ScheduledJob(
        job_id=row["job_id"],
        dataset_id=row["dataset_id"],
        url=row["url"],
        field_descriptions=json.loads(row["field_descriptions"]),
        storage_mode=row["storage_mode"],
        file_path=row["file_path"],
        write_mode=row["write_mode"],
        key_field=row["key_field"],
        image_fields=json.loads(row["image_fields"]) if row["image_fields"] else [],
        trigger_type=row["trigger_type"],
        trigger_args=json.loads(row["trigger_args"]),
        enabled=bool(row["enabled"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        last_run_at=datetime.fromisoformat(row["last_run_at"]) if row["last_run_at"] else None,
        last_status=row["last_status"],
        last_error_traceback=row["last_error_traceback"],
    )


def _row_to_audit_log(row: sqlite3.Row) -> AuditLogEntry:
    return AuditLogEntry(
        id=row["id"],
        event_type=row["event_type"],
        job_id=row["job_id"],
        occurred_at=datetime.fromisoformat(row["occurred_at"]),
        detail=json.loads(row["detail"]) if row["detail"] else {},
    )


def _row_to_dataset(row: sqlite3.Row) -> Dataset:
    return Dataset(
        dataset_id=row["dataset_id"],
        dataset_name=row["dataset_name"],
        schema_signature=json.loads(row["schema_signature"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _row_to_source(row: sqlite3.Row) -> DatasetSource:
    return DatasetSource(
        dataset_id=row["dataset_id"],
        source_url=row["source_url"],
        active=bool(row["active"]),
        added_at=datetime.fromisoformat(row["added_at"]),
    )


def _row_to_strategy(row: sqlite3.Row) -> ExtractionStrategy:
    return ExtractionStrategy(
        domain=row["domain"],
        field_name=row["field_name"],
        selector=row["selector"],
        sample_value=row["sample_value"],
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _row_to_site_credential(row: sqlite3.Row) -> SiteCredential:
    return SiteCredential(
        domain=row["domain"],
        cookie_header=row["cookie_header"],
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _row_to_record(row: sqlite3.Row) -> Record:
    return Record(
        record_id=row["record_id"],
        dataset_id=row["dataset_id"],
        source_url=row["source_url"],
        data=json.loads(row["data"]),
        content_hash=row["content_hash"],
        evidence=json.loads(row["evidence"]) if row["evidence"] else {},
        confidence=row["confidence"],
        needs_review=bool(row["needs_review"]),
        crawled_at=datetime.fromisoformat(row["crawled_at"]),
        as_of=datetime.fromisoformat(row["as_of"]) if row["as_of"] else None,
    )
