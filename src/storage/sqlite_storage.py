"""Implementation StorageEngine dùng SQLite — mặc định cho dev/MVP
(CLAUDE.md — nâng lên Postgres/MySQL sau nếu cần, không bắt buộc ngay)."""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime
from typing import Any, Optional

from .base import Dataset, DatasetSource, Record, StorageEngine, utcnow

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
    crawled_at TEXT NOT NULL,
    as_of TEXT
);
"""


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
        self._conn.commit()

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
        as_of: Optional[datetime] = None,
    ) -> Record:
        record_id = uuid.uuid4().hex
        crawled_at = utcnow()
        evidence = evidence or {}
        self._conn.execute(
            "INSERT INTO records (record_id, dataset_id, source_url, data, content_hash, "
            "evidence, confidence, crawled_at, as_of) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record_id,
                dataset_id,
                source_url,
                json.dumps(data),
                content_hash,
                json.dumps(evidence),
                confidence,
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


def _row_to_record(row: sqlite3.Row) -> Record:
    return Record(
        record_id=row["record_id"],
        dataset_id=row["dataset_id"],
        source_url=row["source_url"],
        data=json.loads(row["data"]),
        content_hash=row["content_hash"],
        evidence=json.loads(row["evidence"]) if row["evidence"] else {},
        confidence=row["confidence"],
        crawled_at=datetime.fromisoformat(row["crawled_at"]),
        as_of=datetime.fromisoformat(row["as_of"]) if row["as_of"] else None,
    )
