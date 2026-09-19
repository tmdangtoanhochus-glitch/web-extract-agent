"""Hướng dẫn cài môi trường Python để chạy Automation trên máy người dùng.

Hiển thị NGAY trên trang Automation (cả màn đăng nhập) vì người dùng web không mở được file `docs/`.
Nội dung tương ứng `docs/RUNNER_LOCAL_SETUP.md` — khi sửa một nơi, sửa cả nơi kia.
"""
from __future__ import annotations

import os

import streamlit as st


def render(expanded: bool = True) -> None:
    api = os.environ.get("API_BASE_URL", "http://localhost:8000").rstrip("/")
    with st.expander("🛠️ Cài môi trường Python để chạy Automation trên máy bạn (làm một lần)", expanded=expanded):
        st.markdown(
            """
**Trang web này chỉ là bảng điều khiển.** Ghi thao tác, xem cấu trúc trang và chạy testcase đều chạy **trên máy của bạn**
(cần điều khiển trình duyệt thật). User/pass của **trang được test** chỉ nằm trong file `runner.env` trên máy bạn,
**không bao giờ tải lên server**.

| Việc | Lệnh chạy trên máy bạn |
|---|---|
| Ghi thao tác (Record) | `python record_runner.py` |
| Xem cấu trúc trang (Inspector) | `python inspect_runner.py` |
| Chạy testcase (Agent) | `python local_runner_agent.py` |

Cần: Windows 10/11 (hoặc macOS/Linux), khoảng **3 GB** ổ đĩa trống, và máy truy cập được trang cần test.
Các lệnh dưới đây chạy trong **PowerShell**, từ thư mục gốc của dự án.
            """
        )
        st.markdown("**Bước 1. Cài Python 3.12** tại [python.org/downloads](https://www.python.org/downloads/windows/). "
                    "Khi cài, **tick ô “Add python.exe to PATH”**. Mở PowerShell mới và kiểm tra:")
        st.code("python --version   # phải hiện Python 3.12.x", language="powershell")

        st.markdown("**Bước 2. Lấy mã nguồn dự án** (nhận từ quản trị viên: `git clone` hoặc file ZIP, giải nén rồi mở PowerShell trong thư mục đó):")
        st.code("git clone <địa-chỉ-repo-do-quản-trị-viên-cấp>\ncd web-extract-agent", language="powershell")

        st.markdown("**Bước 3. Tạo môi trường ảo** để thư viện của dự án không lẫn với Python hệ thống:")
        st.code("python -m venv .venv\n.\\.venv\\Scripts\\Activate.ps1", language="powershell")
        st.caption("Thành công khi đầu dòng có `(.venv)`. Mỗi lần mở PowerShell mới phải chạy lại dòng Activate. "
                   "Nếu báo “running scripts is disabled”: chạy `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` rồi kích hoạt lại.")

        st.markdown("**Bước 4. Cài thư viện** (mất vài phút):")
        st.code(
            '$env:PYTHONUTF8 = "1"\n'
            "python -m pip install --upgrade pip\n"
            "python -m pip install -r requirements.txt -r requirements-auth.txt -r requirements-runner.txt",
            language="powershell",
        )

        st.markdown("**Bước 5. Cài trình duyệt Chromium cho Playwright:**")
        st.code("python -m playwright install chromium", language="powershell")

        st.markdown("**Bước 6. Kiểm tra môi trường đã đủ** (cả hai dòng phải in `OK`):")
        st.code(
            "python -c \"import playwright, pandas, openpyxl, dotenv, httpx, pydantic; print('Thu vien OK')\"\n"
            "python -c \"from playwright.sync_api import sync_playwright as s; p=s().start(); b=p.chromium.launch(); "
            "print('Chromium OK', b.version); b.close(); p.stop()\"",
            language="powershell",
        )

        st.markdown("**Bước 7. Tạo file thông tin đăng nhập của trang cần test** (chỉ trên máy bạn, không gửi cho ai):")
        st.code("Copy-Item runner.env.example runner.env\nnotepad runner.env", language="powershell")

        st.markdown("**Bước 8. Chạy** (đăng nhập trang này → tab **Agent** → tạo agent và copy token, chỉ hiện một lần):")
        st.code(
            f"python local_runner_agent.py --api {api} --configs config --state data/local-runner --env-path runner.env",
            language="powershell",
        )
        st.caption("Agent hỏi token bằng ô nhập ẩn: gõ hoặc dán sẽ không thấy gì, bấm Enter là được. "
                   "Giữ cửa sổ PowerShell mở để agent nhận việc. Log, ảnh chụp và file Excel kết quả lưu trong `data/local-runner` trên máy bạn.")

        with st.expander("Lỗi thường gặp"):
            st.markdown(
                """
| Triệu chứng | Cách xử lý |
|---|---|
| `python` không được nhận diện | Cài lại Python và tick “Add python.exe to PATH”, mở PowerShell mới (hoặc dùng `py -3.12`). |
| `UnicodeDecodeError ... charmap` khi pip | Chạy `$env:PYTHONUTF8 = "1"` rồi cài lại. |
| `No module named 'src'` hoặc `runner_agent` | Đang đứng sai thư mục: `cd` về thư mục gốc dự án (có `requirements.txt`). |
| `No module named 'playwright'` (hoặc pandas...) | Chưa kích hoạt venv (thiếu `(.venv)`) hoặc chưa cài thư viện: chạy lại Bước 3–4. |
| `Executable doesn't exist ... chromium` | Chạy `python -m playwright install chromium`. |
| Agent báo `401` | Token agent sai hoặc hết hạn: tạo agent mới và dán token mới. |
| Không kết nối được API | Mở `""" + api + """/health` trên trình duyệt, phải thấy `{"status":"ok"}`. |
                """
            )
        st.caption("macOS/Linux: dùng `python3.12 -m venv .venv`, `source .venv/bin/activate`, `export PYTHONUTF8=1` và `cp runner.env.example runner.env`. "
                   "Trên Linux có thể cần `python -m playwright install --with-deps chromium`.")
