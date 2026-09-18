"""Test PostgresStorage bằng Postgres THẬT (CLAUDE.md mục 6: test bằng
instance thật, không mock) — cần service `postgres` trong docker-compose
đang chạy:

    docker compose --profile postgres up -d postgres

Tự động BỎ QUA (skip) toàn bộ file nếu không kết nối được — không chặn
`pytest tests/` chạy bình thường trên máy chưa bật Postgres. Test hành vi
chung của interface `StorageEngine` nằm ở `storage_contract.py` (dùng chung
với `test_sqlite_storage.py`, import qua `*` bên dưới)."""
import os

import psycopg2
import pytest

from src.storage.postgres_storage import PostgresStorage
from storage_contract import *  # noqa: F401,F403 — test hành vi chung StorageEngine

_TEST_DSN = os.environ.get(
    "POSTGRES_TEST_DSN",
    "postgresql://web_extract_agent:web_extract_agent_dev_only@localhost:5432/web_extract_agent",
)


def _postgres_available() -> bool:
    try:
        conn = psycopg2.connect(_TEST_DSN, connect_timeout=2)
        conn.close()
        return True
    except psycopg2.OperationalError:
        return False


pytestmark = pytest.mark.skipif(
    not _postgres_available(),
    reason=(
        "Cần Postgres thật để chạy (docker compose --profile postgres up -d postgres) "
        "— tự bỏ qua vì không kết nối được tới " + _TEST_DSN
    ),
)


@pytest.fixture
def storage():
    store = PostgresStorage(_TEST_DSN)
    store.reset_for_tests()  # mỗi test bắt đầu từ DB sạch, cùng 1 instance Postgres
    yield store
    store.close()
