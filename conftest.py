"""Đảm bảo `src` import được khi chạy `pytest` từ thư mục gốc project
(chưa có pyproject.toml/setup.py nên cần insert path thủ công)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
