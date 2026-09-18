"""Panel admin NỘI BỘ — "AI gợi ý sửa lỗi" cho job lịch/crawl thủ công bị lỗi
+ quản lý cookie đăng nhập theo domain.

**KHÔNG dành cho người dùng cuối** — Streamlit tự thêm trang này vào sidebar
multipage (do nằm trong `ui/pages/`), tách biệt hoàn toàn khỏi luồng chính
(`ui/app.py`). Backend yêu cầu HTTP Basic Auth cho MỌI route `/admin/*`
(`ADMIN_USERNAME`/`ADMIN_PASSWORD` trong `.env`, xem `src/api/admin.py`) —
trang này tự xin username/password rồi gắn vào MỌI request gọi API.

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
st.title("🛠️ Admin Debug")

# ---- Đăng nhập (HTTP Basic Auth — backend bắt buộc, xem src/api/admin.py) --
if "admin_auth" not in st.session_state:
    st.session_state.admin_auth = None

if st.session_state.admin_auth is None:
    st.subheader("Đăng nhập")
    with st.form("admin_login"):
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Đăng nhập")
    if submitted:
        try:
            resp = httpx.get(f"{API_BASE_URL}/admin/errors", auth=(u, p), timeout=10.0)
        except httpx.HTTPError as exc:
            st.error(f"Không gọi được API ({API_BASE_URL}): {exc}")
            st.stop()
        if resp.status_code == 401:
            st.error("Sai username/password, hoặc server chưa cấu hình ADMIN_USERNAME/ADMIN_PASSWORD trong .env.")
            st.stop()
        st.session_state.admin_auth = (u, p)
        st.rerun()
    st.stop()

_AUTH = st.session_state.admin_auth
if st.sidebar.button("Đăng xuất"):
    st.session_state.admin_auth = None
    st.rerun()


def _client() -> httpx.Client:
    return httpx.Client(base_url=API_BASE_URL, auth=_AUTH, timeout=60.0)


def _api_get(path: str) -> Optional[Any]:
    try:
        with _client() as client:
            resp = client.get(path)
            if resp.status_code == 401:
                st.session_state.admin_auth = None
                st.error("Phiên đăng nhập hết hạn hoặc sai — đăng nhập lại.")
                st.rerun()
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as exc:
        st.error(f"Không gọi được API ({API_BASE_URL}{path}): {exc}")
        return None


def _api_post(path: str, json_body: Optional[dict] = None) -> Optional[dict]:
    try:
        with _client() as client:
            resp = client.post(path, json=json_body)
            if resp.status_code >= 400:
                detail = resp.json().get("detail", resp.text)
                return {"_http_error": resp.status_code, "detail": detail}
            return resp.json()
    except httpx.HTTPError as exc:
        st.error(f"Không gọi được API ({API_BASE_URL}{path}): {exc}")
        return None


def _api_delete(path: str) -> Optional[dict]:
    try:
        with _client() as client:
            resp = client.delete(path)
            if resp.status_code >= 400:
                detail = resp.json().get("detail", resp.text)
                return {"_http_error": resp.status_code, "detail": detail}
            return resp.json()
    except httpx.HTTPError as exc:
        st.error(f"Không gọi được API ({API_BASE_URL}{path}): {exc}")
        return None


tab_errors, tab_credentials, tab_reports = st.tabs(["❌ Job lỗi & gợi ý sửa", "🔑 Cookie cũ", "Báo lỗi từ người dùng"])

with tab_errors:
    if st.button("🔄 Tải lại danh sách lỗi"):
        st.rerun()

    errors = _api_get("/admin/errors")
    if errors is None:
        st.stop()

    scheduled_errors = errors.get("scheduled_job_errors", [])
    manual_errors = errors.get("manual_crawl_errors", [])

    if not scheduled_errors and not manual_errors:
        st.success("Không có lỗi nào. ✅")

    if scheduled_errors:
        st.caption(f"Có {len(scheduled_errors)} job lịch đang ở trạng thái lỗi.")
        for job in scheduled_errors:
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
                if job.get("bulk_results"):
                    st.dataframe(job["bulk_results"])

                suggestion_key = f"suggestion_{job['job_id']}"
                if st.button("🤖 Hỏi AI gợi ý sửa", key=f"ask_{job['job_id']}"):
                    with st.spinner("Đang hỏi AI..."):
                        result = _api_post(f"/admin/errors/{job['job_id']}/suggest-fix")
                    if result is None:
                        pass
                    elif result.get("_http_error"):
                        st.error(f"AI gợi ý thất bại: {result['detail']}")
                    else:
                        st.session_state[suggestion_key] = result["content"]

                if suggestion_key in st.session_state:
                    st.markdown("**Gợi ý từ AI** (chỉ đọc — tự copy/áp dụng thủ công, không có nút Áp dụng):")
                    st.code(st.session_state[suggestion_key], language="diff")

    if manual_errors:
        st.markdown("---")
        st.caption(
            f"Có {len(manual_errors)} lần \"Chạy crawl\" thủ công gần đây bị lỗi (không thuộc job lịch nào) — "
            "chỉ để tra cứu, KHÔNG hỏi AI gợi ý sửa được ở đây (không có traceback đầy đủ như job lịch)."
        )
        for entry in manual_errors:
            detail = entry.get("detail", {})
            st.markdown(
                f"- `{entry.get('occurred_at', '')[:19]}` — **{detail.get('url', '?')}** "
                f"— trạng thái `{detail.get('status')}` — lỗi: `{detail.get('error')}`"
            )

with tab_credentials:
    st.info("Nhập cookie đã chuyển sang Bước 3 của luồng crawl. Cookie cũ dưới đây không còn được crawler hoặc lịch dùng tự động. Bạn có thể xóa các mục cũ.")
    credentials = _api_get("/admin/site-credentials")
    if credentials:
        for cred in credentials:
            c1, c2, c3 = st.columns([3, 3, 1])
            c1.markdown(f"**{cred['domain']}**")
            c2.caption(f"{cred['cookie_length']} ký tự · cập nhật lúc {cred['updated_at'][:19]}")
            if c3.button("🗑", key=f"del_cred_{cred['domain']}"):
                del_result = _api_delete(f"/admin/site-credentials/{cred['domain']}")
                if del_result and not del_result.get("_http_error"):
                    st.rerun()
    else:
        st.info("Chưa lưu cookie cho domain nào.")

with tab_reports:
    reports = _api_get("/admin/crawl-reports") or []
    st.caption("Báo lỗi crawl/UI từ người dùng. AI chỉ nhận metadata đã giới hạn, không nhận cookie hay nội dung trang.")
    for report in reports:
        with st.expander(f"Report {report['id']} - {report['occurred_at']}"):
            st.json(report["detail"])
            for diagnosis in report.get("diagnoses", []):
                st.code(diagnosis["detail"].get("content", ""), language="text")
            if st.button("AI chẩn đoán", key=f"diagnose_{report['id']}"):
                result = _api_post(f"/admin/crawl-reports/{report['id']}/diagnose")
                if result and not result.get("_http_error"):
                    st.code(result["content"], language="text")
                else:
                    st.error("Chưa chẩn đoán được; báo lỗi vẫn được lưu.")
