"""Metadata riêng cho Runner, transaction tuần tự; không đụng bảng crawler."""
import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

KINDS = {"users", "sessions", "agents", "runs", "audit", "notifications"}


class Repository:
    def __init__(self, path=":memory:", postgres_dsn=None):
        self.lock = threading.RLock()
        self.postgres = bool(postgres_dsn)
        if self.postgres:
            import psycopg2
            self.conn = psycopg2.connect(postgres_dsn)
        else:
            if path != ":memory:":
                Path(path).parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(path, check_same_thread=False)
        with self.transaction():
            for kind in KINDS:
                self.execute(f"CREATE TABLE IF NOT EXISTS runner_{kind} (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")

    def execute(self, sql, params=()):
        cur = self.conn.cursor()
        cur.execute(sql.replace("?", "%s") if self.postgres else sql, params)
        return cur

    @contextmanager
    def transaction(self):
        with self.lock:
            try:
                if self.postgres:
                    self.execute("SELECT pg_advisory_xact_lock(73192615)").close()
                else:
                    self.execute("BEGIN IMMEDIATE").close()
                yield self
                self.conn.commit()
            except BaseException:
                self.conn.rollback()
                raise

    def get(self, kind, key):
        assert kind in KINDS
        cur = self.execute(f"SELECT payload FROM runner_{kind} WHERE id=?", (key,))
        row = cur.fetchone()
        cur.close()
        return json.loads(row[0]) if row else None

    def all(self, kind):
        assert kind in KINDS
        cur = self.execute(f"SELECT payload FROM runner_{kind}")
        rows = cur.fetchall()
        cur.close()
        return [json.loads(r[0]) for r in rows]

    def put(self, kind, key, value):
        assert kind in KINDS
        if kind == "audit" and self.get(kind, key):
            raise ValueError("Audit is append-only")
        self.execute(f"INSERT INTO runner_{kind} (id,payload) VALUES (?,?) "
                     "ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                     (key, json.dumps(value, ensure_ascii=False))).close()

    def delete(self, kind, key):
        assert kind in KINDS and kind != "audit"
        self.execute(f"DELETE FROM runner_{kind} WHERE id=?", (key,)).close()

    def close(self):
        self.conn.close()
