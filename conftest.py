"""Đảm bảo `src` import được khi chạy `pytest` từ thư mục gốc project
(chưa có pyproject.toml/setup.py nên cần insert path thủ công)."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Chặn dotenv NGAY khi collection, trước khi test import src.api.main.
# Không dùng cấu hình/DB thật trong bất kỳ test mặc định nào.
import dotenv
dotenv.load_dotenv = lambda *args, **kwargs: False
for _key in list(os.environ):
    if _key.startswith(("AI_", "ADMIN_", "DB_", "DATABASE_", "RUNNER_")):
        del os.environ[_key]
os.environ["DB_BACKEND"] = "sqlite"
os.environ["DB_PATH"] = ":memory:"


def pytest_addoption(parser):
    parser.addoption("--postgres-integration", action="store_true", default=False,
                     help="Chỉ dùng với PostgreSQL test riêng do người vận hành chuẩn bị")


def pytest_ignore_collect(collection_path, config):
    return (collection_path.name == "test_postgres_storage.py"
            and not config.getoption("--postgres-integration"))


@pytest.fixture(autouse=True)
def isolated_working_directory(tmp_path, monkeypatch):
    """Mọi export/ảnh tương đối của test chỉ nằm trong thư mục test mới."""
    monkeypatch.chdir(tmp_path)
