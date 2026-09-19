"""`streamlit run ui/Crawl.py` (như trong container) chỉ thêm thư mục ui/ vào sys.path. Mỗi trang phải tự thêm thư mục gốc
TRƯỚC khi import `ui.*`/`src.*`, nếu không trang Automation lỗi `No module named 'ui'` trên bản deploy."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGES = ["ui/Crawl.py", "ui/pages/2_Automation.py", "ui/pages/3_Admin.py"]


def test_pages_put_project_root_on_sys_path_before_project_imports():
    for name in PAGES:
        text = (ROOT / name).read_text(encoding="utf-8").replace("\r\n", "\n")
        root_pos = text.find("sys.path.insert(0, _PROJECT_ROOT)")
        assert root_pos != -1, name
        first_import = re.search(r"^\s*(from|import)\s+(ui|src)\b", text, re.MULTILINE)
        assert first_import is None or first_import.start() > root_pos, name


def test_ui_image_sets_pythonpath():
    dockerfile = (ROOT / "Dockerfile.ui").read_text(encoding="utf-8")
    assert "ENV PYTHONPATH=/app" in dockerfile
