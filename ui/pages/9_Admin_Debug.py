"""Panel admin NỘI BỘ — "AI gợi ý sửa lỗi" cho job lịch bị lỗi.

**KHÔNG dành cho người dùng cuối** — Streamlit tự thêm trang này vào sidebar
multipage (do nằm trong `ui/pages/`), tách biệt hoàn toàn khỏi luồng chính
(`ui/app.py`). MVP hiện tại KHÔNG có authentication (chấp nhận được cho
demo/hackathon) nhưng route backend cũng nằm dưới prefix `/admin` riêng — chỉ
người biết URL/trang này mới vào được, không có link dẫn từ luồng người dùng
thường.

Ràng buộc bảo mật: AI CHỈ trả về text gợi ý (chẩn đoán + patch đề xuất + rủi
ro) — trang này CHỈ hiển thị bằng `st.code()` để người dùng tự đọc/copy, KHÔNG
có nút "Áp dụng"/"Merge" nào cả (giới hạn cố ý, xem `src/ai/debug_assistant.py`
và `src/api/admin.py`).
"""
from __future__ import annotations

import os
from typing import Any, Optional

import httpx
import streamlit as st

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

st.set_page_config(page_title="Admin Debug", page_icon="🛠️", layout="wide")

st.warning(
    "🛠️ **Màn nội bộ (admin/dev)** — không dành cho người dùng thường. "
    "AI ở đây chỉ ĐỌC traceback/code và GỢI Ý sửa lỗi dạng text — không tự động sửa file, "
    "không thực thi lệnh gì. Bạn tự đọc/copy và áp dụng thủ công bên ngoài (git/editor riêng)."
)
st.title("🛠️ Admin Debug — Job lỗi & gợi ý sửa từ AI")


def _client() -> httpx.Client:
    return httpx.Client(base_url=API_BASE_URL, timeout=60.0)


def _api_get(path: str) -> Optional[Any]:
    try:
        with _client() as client:
            resp = client.get(path)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as exc:
        st.error(f"Không gọi được API ({API_BASE_URL}{path}): {exc}")
        return None


def _api_post(path: str) -> Optional[dict]:
    try:
        with _client() as client:
            resp = client.post(path)
            if resp.status_code >= 400:
                detail = resp.json().get("detail", resp.text)
                return {"_http_error": resp.status_code, "detail": detail}
            return resp.json()
    except httpx.HTTPError as exc:
        st.error(f"Không gọi được API ({API_BASE_URL}{path}): {exc}")
        return None


if st.button("🔄 Tải lại danh sách lỗi"):
    st.rerun()

error_jobs = _api_get("/admin/errors")

if error_jobs is None:
    st.stop()  # lỗi gọi API đã hiển thị ở _api_get, không render tiếp

if not error_jobs:
    st.success("Không có job nào đang lỗi. ✅")
else:
    st.caption(f"Có {len(error_jobs)} job đang ở trạng thái lỗi.")

    for job in error_jobs:
        target = (
            f"file: {job.get('file_path')}"
            if job.get("storage_mode") == "file"
            else f"dataset_id: {job.get('dataset_id')}"
        )
        with st.expander(f"❌ {job['url']}  ·  {target}  ·  job_id={job['job_id'][:8]}"):
            st.markdown(
                f"**job_id:** `{job['job_id']}`  \n"
                f"**URL:** {job['url']}  \n"
                f"**storage_mode:** {job.get('storage_mode')}  \n"
                f"**Lần chạy gần nhất:** {job.get('last_run_at') or '—'}"
            )

            st.markdown("**Traceback đầy đủ:**")
            st.code(job.get("last_error_traceback") or "(không có traceback lưu lại)", language="text")

            suggestion_key = f"suggestion_{job['job_id']}"
            if st.button("🤖 Hỏi AI gợi ý sửa", key=f"ask_{job['job_id']}"):
                with st.spinner("Đang hỏi AI..."):
                    result = _api_post(f"/admin/errors/{job['job_id']}/suggest-fix")
                if result is None:
                    pass  # lỗi mạng đã hiển thị ở _api_post
                elif result.get("_http_error"):
                    st.error(f"AI gợi ý thất bại: {result['detail']}")
                else:
                    st.session_state[suggestion_key] = result["content"]

            if suggestion_key in st.session_state:
                st.markdown("**Gợi ý từ AI** (chỉ đọc — tự copy/áp dụng thủ công, không có nút Áp dụng):")
                st.code(st.session_state[suggestion_key], language="diff")
