"""Implementation StorageEngine dùng PostgreSQL — lựa chọn thay thế SQLite cho
môi trường production/deploy lên GreenNode (CLAUDE.md — "SQLite cho dev/MVP,
có thể nâng lên Postgres/MySQL sau nếu cần"). Chọn qua `DB_BACKEND=postgres`
trong `.env` (xem `src/config.py`), giữ SQLite làm mặc định cho dev/local.

Cùng 1 schema dynamic-JSON như `SQLiteStorage` (CLAUDE.md mục 4) — chỉ khác
dialect SQL (JSONB thay vì TEXT cho cột JSON, TIMESTAMPTZ thay vì TEXT cho cột
thời gian, `%s` thay vì `?` cho placeholder). Không có migration tự động như
SQLiteStorage vì đây là backend mới, schema luôn được tạo đúng ngay từ đầu
(`CREATE TABLE IF NOT EXISTS`), không có DB cũ cần nâng cấp cột.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

import psycopg2
import psycopg2.extras

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
    schema_signature JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS dataset_sources (
    dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id),
    source_url TEXT NOT NULL,
    active BOOLEAN NOT NULL,
    added_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS records (
    record_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id),
    source_url TEXT NOT NULL,
    data JSONB NOT NULL,
    content_hash TEXT NOT NULL,
    evidence JSONB,
    confidence DOUBLE PRECISION,
    needs_review BOOLEAN NOT NULL DEFAULT FALSE,
    crawled_at TIMESTAMPTZ NOT NULL,
    as_of TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_records_export ON records (dataset_id, crawled_at, record_id);

CREATE TABLE IF NOT EXISTS extraction_strategies (
    domain TEXT NOT NULL,
    field_name TEXT NOT NULL,
    selector TEXT NOT NULL,
    sample_value TEXT,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (domain, field_name)
);

CREATE TABLE IF NOT EXISTS scheduled_jobs (
    job_id TEXT PRIMARY KEY,
    dataset_id TEXT REFERENCES datasets(dataset_id),
    url TEXT NOT NULL,
    field_descriptions JSONB NOT NULL,
    storage_mode TEXT NOT NULL DEFAULT 'db',
    file_path TEXT,
    write_mode TEXT,
    key_field TEXT,
    image_fields JSONB,
    crawl_options JSONB,
    trigger_type TEXT NOT NULL,
    trigger_args JSONB NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL,
    last_run_at TIMESTAMPTZ,
    last_status TEXT,
    last_error_traceback TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    job_id TEXT,
    occurred_at TIMESTAMPTZ NOT NULL,
    detail JSONB
);

CREATE TABLE IF NOT EXISTS site_credentials (
    domain TEXT PRIMARY KEY,
    cookie_header TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
"""

_TABLES_FOR_RESET = (
    "records", "dataset_sources", "scheduled_jobs", "audit_log",
    "extraction_strategies", "datasets", "site_credentials",
)


def _normalize_schema(schema_signature: list[str]) -> list[str]:
    """Chuẩn hoá schema_signature để so khớp không phân biệt thứ tự field —
    JSONB so sánh mảng theo đúng thứ tự phần tử nên 2 bên (lúc lưu/lúc so
    khớp) đều phải chuẩn hoá giống nhau."""
    return sorted(set(schema_signature))


class PostgresStorage(StorageEngine):
    def __init__(self, dsn: str) -> None:
        self._conn = psycopg2.connect(dsn)
        with self._conn.cursor() as cur:
            cur.execute(_SCHEMA_SQL)
            cur.execute("ALTER TABLE scheduled_jobs ADD COLUMN IF NOT EXISTS crawl_options JSONB")
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def reset_for_tests(self) -> None:
        """CHỈ dùng trong test — xoá sạch dữ liệu, giữ nguyên schema, để mỗi
        test bắt đầu từ trạng thái sạch trên cùng 1 database Postgres thật
        (CLAUDE.md mục 6: test bằng DB thật, không mock)."""
        with self._conn.cursor() as cur:
            cur.execute(f"TRUNCATE {', '.join(_TABLES_FOR_RESET)} CASCADE")
        self._conn.commit()

    def _cursor(self):
        return self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # -- datasets ------------------------------------------------------
    def create_dataset(self, dataset_name: str, schema_signature: list[str]) -> Dataset:
        dataset_id = uuid.uuid4().hex
        created_at = utcnow()
        normalized = _normalize_schema(schema_signature)
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO datasets (dataset_id, dataset_name, schema_signature, created_at) "
                "VALUES (%s, %s, %s, %s)",
                (dataset_id, dataset_name, psycopg2.extras.Json(normalized), created_at),
            )
        self._conn.commit()
        return Dataset(
            dataset_id=dataset_id,
            dataset_name=dataset_name,
            schema_signature=normalized,
            created_at=created_at,
        )

    def find_dataset_by_schema(self, schema_signature: list[str]) -> Optional[Dataset]:
        normalized = _normalize_schema(schema_signature)
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM datasets WHERE schema_signature = %s ORDER BY created_at LIMIT 1",
                (psycopg2.extras.Json(normalized),),
            )
            row = cur.fetchone()
        return _row_to_dataset(row) if row else None

    def get_dataset(self, dataset_id: str) -> Optional[Dataset]:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM datasets WHERE dataset_id = %s", (dataset_id,))
            row = cur.fetchone()
        return _row_to_dataset(row) if row else None

    def list_datasets(self) -> list[Dataset]:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM datasets ORDER BY created_at")
            rows = cur.fetchall()
        return [_row_to_dataset(row) for row in rows]

    # -- dataset_sources -------------------------------------------------
    def add_source(self, dataset_id: str, source_url: str) -> DatasetSource:
        added_at = utcnow()
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO dataset_sources (dataset_id, source_url, active, added_at) "
                "VALUES (%s, %s, TRUE, %s)",
                (dataset_id, source_url, added_at),
            )
        self._conn.commit()
        return DatasetSource(
            dataset_id=dataset_id, source_url=source_url, active=True, added_at=added_at
        )

    def replace_source(
        self, dataset_id: str, old_source_url: str, new_source_url: str
    ) -> DatasetSource:
        with self._cursor() as cur:
            cur.execute(
                "UPDATE dataset_sources SET active = FALSE "
                "WHERE dataset_id = %s AND source_url = %s AND active = TRUE",
                (dataset_id, old_source_url),
            )
            added_at = utcnow()
            cur.execute(
                "INSERT INTO dataset_sources (dataset_id, source_url, active, added_at) "
                "VALUES (%s, %s, TRUE, %s)",
                (dataset_id, new_source_url, added_at),
            )
        self._conn.commit()
        return DatasetSource(
            dataset_id=dataset_id, source_url=new_source_url, active=True, added_at=added_at
        )

    def list_sources(self, dataset_id: str, active_only: bool = False) -> list[DatasetSource]:
        query = "SELECT * FROM dataset_sources WHERE dataset_id = %s"
        params: list[Any] = [dataset_id]
        if active_only:
            query += " AND active = TRUE"
        query += " ORDER BY added_at"
        with self._cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
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
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO records (record_id, dataset_id, source_url, data, content_hash, "
                "evidence, confidence, needs_review, crawled_at, as_of) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    record_id,
                    dataset_id,
                    source_url,
                    psycopg2.extras.Json(data),
                    content_hash,
                    psycopg2.extras.Json(evidence),
                    confidence,
                    needs_review,
                    crawled_at,
                    as_of,
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
        # `ctid` (vị trí vật lý của dòng, luôn có sẵn) dùng làm tiebreaker
        # thay vì `record_id` (uuid4 ngẫu nhiên, KHÔNG phản ánh thứ tự chèn) —
        # 2 lần save_record() liên tiếp có thể trùng `crawled_at` tới độ phân
        # giải microsecond khi chạy nhanh (vd. trong test), giống lý do dùng
        # `rowid` ở SQLiteStorage. An toàn vì bảng `records` chỉ INSERT, không
        # bao giờ UPDATE tại chỗ.
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM records WHERE dataset_id = %s AND source_url = %s "
                "ORDER BY crawled_at DESC, ctid DESC LIMIT 1",
                (dataset_id, source_url),
            )
            row = cur.fetchone()
        return _row_to_record(row) if row else None

    def list_records(self, dataset_id: str, limit: int = 100, offset: int = 0) -> list[Record]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM records WHERE dataset_id = %s "
                "ORDER BY crawled_at DESC, ctid DESC LIMIT %s OFFSET %s",
                (dataset_id, limit, offset),
            )
            rows = cur.fetchall()
        return [_row_to_record(row) for row in rows]

    def export_record_page(self, dataset_id, cutoff, after=None, limit=500):
        query = "SELECT * FROM records WHERE dataset_id = %s AND crawled_at <= %s"
        args = [dataset_id, cutoff]
        if after:
            query += " AND (crawled_at < %s OR (crawled_at = %s AND record_id < %s))"
            args.extend([after[0], after[0], after[1]])
        query += " ORDER BY crawled_at DESC, record_id DESC LIMIT %s"
        args.append(limit)
        with self._cursor() as cur:
            cur.execute(query, args)
            rows = cur.fetchall()
        return [_row_to_record(row) for row in rows]

    # -- extraction_strategies (cache CLAUDE.md mục 5) ----------------------
    def get_extraction_strategy(self, domain: str, field_name: str) -> Optional[ExtractionStrategy]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM extraction_strategies WHERE domain = %s AND field_name = %s",
                (domain, field_name),
            )
            row = cur.fetchone()
        return _row_to_strategy(row) if row else None

    def save_extraction_strategy(
        self, domain: str, field_name: str, selector: str, sample_value: Optional[str] = None
    ) -> ExtractionStrategy:
        updated_at = utcnow()
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO extraction_strategies (domain, field_name, selector, sample_value, updated_at) "
                "VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT (domain, field_name) DO UPDATE SET "
                "selector = EXCLUDED.selector, sample_value = EXCLUDED.sample_value, "
                "updated_at = EXCLUDED.updated_at",
                (domain, field_name, selector, sample_value, updated_at),
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
        crawl_options: Optional[dict] = None,
    ) -> ScheduledJob:
        job_id = uuid.uuid4().hex
        created_at = utcnow()
        image_fields = image_fields or []
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO scheduled_jobs (job_id, dataset_id, url, field_descriptions, "
                "storage_mode, file_path, write_mode, key_field, image_fields, crawl_options, "
                "trigger_type, trigger_args, enabled, created_at, last_run_at, last_status, "
                "last_error_traceback) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s, NULL, NULL, NULL)",
                (
                    job_id,
                    dataset_id,
                    url,
                    psycopg2.extras.Json(field_descriptions),
                    storage_mode,
                    file_path,
                    write_mode,
                    key_field,
                    psycopg2.extras.Json(image_fields),
                    psycopg2.extras.Json(crawl_options) if crawl_options else None,
                    trigger_type,
                    psycopg2.extras.Json(trigger_args),
                    created_at,
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
            crawl_options=crawl_options,
            trigger_type=trigger_type,
            trigger_args=trigger_args,
            enabled=True,
            created_at=created_at,
        )

    def get_scheduled_job(self, job_id: str) -> Optional[ScheduledJob]:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM scheduled_jobs WHERE job_id = %s", (job_id,))
            row = cur.fetchone()
        return _row_to_scheduled_job(row) if row else None

    def list_scheduled_jobs(self, enabled_only: bool = False) -> list[ScheduledJob]:
        query = "SELECT * FROM scheduled_jobs"
        if enabled_only:
            query += " WHERE enabled = TRUE"
        query += " ORDER BY created_at"
        with self._cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
        return [_row_to_scheduled_job(row) for row in rows]

    def update_scheduled_job_run(
        self, job_id: str, status: str, traceback_text: Optional[str] = None
    ) -> None:
        with self._cursor() as cur:
            cur.execute(
                "UPDATE scheduled_jobs SET last_run_at = %s, last_status = %s, "
                "last_error_traceback = %s WHERE job_id = %s",
                (utcnow(), status, traceback_text, job_id),
            )
        self._conn.commit()

    def configure_scheduled_job(self, job_id, enabled, trigger_type, trigger_args):
        with self._cursor() as cur:
            cur.execute(
                "UPDATE scheduled_jobs SET enabled = %s, trigger_type = %s, trigger_args = %s WHERE job_id = %s",
                (enabled, trigger_type, psycopg2.extras.Json(trigger_args), job_id),
            )
        self._conn.commit()

    def delete_scheduled_job(self, job_id: str) -> None:
        with self._cursor() as cur:
            cur.execute("DELETE FROM scheduled_jobs WHERE job_id = %s", (job_id,))
        self._conn.commit()

    # -- audit_log (panel admin "AI gợi ý sửa lỗi") --------------------------
    def add_audit_log(
        self, event_type: str, job_id: Optional[str] = None, detail: Optional[dict[str, Any]] = None
    ) -> AuditLogEntry:
        entry_id = uuid.uuid4().hex
        occurred_at = utcnow()
        detail = detail or {}
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO audit_log (id, event_type, job_id, occurred_at, detail) "
                "VALUES (%s, %s, %s, %s, %s)",
                (entry_id, event_type, job_id, occurred_at, psycopg2.extras.Json(detail)),
            )
        self._conn.commit()
        return AuditLogEntry(
            id=entry_id, event_type=event_type, job_id=job_id, occurred_at=occurred_at, detail=detail
        )

    def list_audit_log(self, job_id: Optional[str] = None, limit: int = 100) -> list[AuditLogEntry]:
        query = "SELECT * FROM audit_log"
        params: list[Any] = []
        if job_id is not None:
            query += " WHERE job_id = %s"
            params.append(job_id)
        # `ctid` tiebreaker — lý do giống `list_records` (`id` là uuid4 ngẫu
        # nhiên, không phản ánh thứ tự chèn).
        query += " ORDER BY occurred_at DESC, ctid DESC LIMIT %s"
        params.append(limit)
        with self._cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
        return [_row_to_audit_log(row) for row in rows]

    # -- site_credentials (cookie đăng nhập thủ công theo domain) -----------
    def save_site_credential(self, domain: str, cookie_header: str) -> SiteCredential:
        updated_at = utcnow()
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO site_credentials (domain, cookie_header, updated_at) "
                "VALUES (%s, %s, %s) "
                "ON CONFLICT (domain) DO UPDATE SET "
                "cookie_header = EXCLUDED.cookie_header, updated_at = EXCLUDED.updated_at",
                (domain, cookie_header, updated_at),
            )
        self._conn.commit()
        return SiteCredential(domain=domain, cookie_header=cookie_header, updated_at=updated_at)

    def get_site_credential(self, domain: str) -> Optional[SiteCredential]:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM site_credentials WHERE domain = %s", (domain,))
            row = cur.fetchone()
        return _row_to_site_credential(row) if row else None

    def list_site_credentials(self) -> list[SiteCredential]:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM site_credentials ORDER BY domain")
            rows = cur.fetchall()
        return [_row_to_site_credential(row) for row in rows]

    def delete_site_credential(self, domain: str) -> None:
        with self._cursor() as cur:
            cur.execute("DELETE FROM site_credentials WHERE domain = %s", (domain,))
        self._conn.commit()


def _row_to_dataset(row: dict) -> Dataset:
    return Dataset(
        dataset_id=row["dataset_id"],
        dataset_name=row["dataset_name"],
        schema_signature=list(row["schema_signature"]),
        created_at=row["created_at"],
    )


def _row_to_source(row: dict) -> DatasetSource:
    return DatasetSource(
        dataset_id=row["dataset_id"],
        source_url=row["source_url"],
        active=bool(row["active"]),
        added_at=row["added_at"],
    )


def _row_to_strategy(row: dict) -> ExtractionStrategy:
    return ExtractionStrategy(
        domain=row["domain"],
        field_name=row["field_name"],
        selector=row["selector"],
        sample_value=row["sample_value"],
        updated_at=row["updated_at"],
    )


def _row_to_site_credential(row: dict) -> SiteCredential:
    return SiteCredential(
        domain=row["domain"], cookie_header=row["cookie_header"], updated_at=row["updated_at"]
    )


def _row_to_record(row: dict) -> Record:
    return Record(
        record_id=row["record_id"],
        dataset_id=row["dataset_id"],
        source_url=row["source_url"],
        data=dict(row["data"]),
        content_hash=row["content_hash"],
        evidence=dict(row["evidence"]) if row["evidence"] else {},
        confidence=row["confidence"],
        needs_review=bool(row["needs_review"]),
        crawled_at=row["crawled_at"],
        as_of=row["as_of"],
    )


def _row_to_scheduled_job(row: dict) -> ScheduledJob:
    return ScheduledJob(
        job_id=row["job_id"],
        dataset_id=row["dataset_id"],
        url=row["url"],
        field_descriptions=dict(row["field_descriptions"]),
        storage_mode=row["storage_mode"],
        file_path=row["file_path"],
        write_mode=row["write_mode"],
        key_field=row["key_field"],
        image_fields=list(row["image_fields"]) if row["image_fields"] else [],
        crawl_options=row["crawl_options"],
        trigger_type=row["trigger_type"],
        trigger_args=dict(row["trigger_args"]),
        enabled=bool(row["enabled"]),
        created_at=row["created_at"],
        last_run_at=row["last_run_at"],
        last_status=row["last_status"],
        last_error_traceback=row["last_error_traceback"],
    )


def _row_to_audit_log(row: dict) -> AuditLogEntry:
    return AuditLogEntry(
        id=row["id"],
        event_type=row["event_type"],
        job_id=row["job_id"],
        occurred_at=row["occurred_at"],
        detail=dict(row["detail"]) if row["detail"] else {},
    )
