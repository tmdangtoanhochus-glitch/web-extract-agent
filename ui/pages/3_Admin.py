"""Panel admin NỘI BỘ — "AI gợi ý sửa lỗi" cho job lịch/crawl thủ công bị lỗi
+ quản lý cookie đăng nhập theo domain.

**KHÔNG dành cho người dùng cuối** — Streamlit tự thêm trang này vào sidebar
multipage (do nằm trong `ui/pages/`), tách biệt hoàn toàn khỏi luồng chính
(`ui/crawl.py`). Backend yêu cầu HTTP Basic Auth cho MỌI route `/admin/*`
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

st.set_page_config(page_title="Admin", page_icon="🛠️", layout="wide")

st.warning(
    "🛠️ **Màn nội bộ (admin/dev)** — không dành cho người dùng thường. "
    "AI ở đây chỉ ĐỌC traceback/code và GỢI Ý sửa lỗi dạng text — không tự động sửa file, "
    "không thực thi lệnh gì. Bạn tự đọc/copy và áp dụng thủ công bên ngoài (git/editor riêng)."
)
st.title("🛠️ Admin — quản lý Crawl & Automation")

# ---- Đăng nhập admin CHUNG cho Crawl + Automation ---------------------------
# Tài khoản admin của Runner (role=admin) dùng được cho cả /admin/* (crawl) lẫn
# /runner/* (automation); phiên dùng chung với trang Automation (`runner_session`).
# Đường dự phòng: ADMIN_USERNAME/ADMIN_PASSWORD trong .env (HTTP Basic) — chỉ mở
# phần Crawl, không có phiên Runner.
if "admin_auth" not in st.session_state:
    st.session_state.admin_auth = None


def _runner_admin_session_ok(token: str) -> bool:
    try:
        resp = httpx.get(f"{API_BASE_URL}/runner/me", headers={"Authorization": f"Bearer {token}"}, timeout=10.0)
        return resp.status_code == 200 and resp.json().get("role") == "admin"
    except (httpx.HTTPError, ValueError):
        return False


if st.session_state.admin_auth is None and st.session_state.get("runner_session"):
    if _runner_admin_session_ok(st.session_state.runner_session):
        st.session_state.admin_auth = {"kind": "bearer", "token": st.session_state.runner_session}

if st.session_state.admin_auth is None:
    st.subheader("Đăng nhập admin")
    st.caption("Dùng tài khoản admin Runner để quản lý cả Crawl và Automation.")
    with st.form("admin_login"):
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Đăng nhập")
    if submitted:
        try:
            login = httpx.post(f"{API_BASE_URL}/runner/login", json={"username": u, "password": p}, timeout=10.0)
            if login.status_code == 200:
                body = login.json()
                if body["user"]["role"] != "admin":
                    st.error("Tài khoản này không có quyền admin.")
                    st.stop()
                st.session_state.runner_session = body["session"]
                st.session_state.admin_auth = {"kind": "bearer", "token": body["session"]}
                st.rerun()
            resp = httpx.get(f"{API_BASE_URL}/admin/errors", auth=(u, p), timeout=10.0)
        except httpx.HTTPError as exc:
            st.error(f"Không gọi được API ({API_BASE_URL}): {exc}")
            st.stop()
        if resp.status_code == 401:
            st.error("Sai username/password (hoặc chưa có admin Runner / ADMIN_USERNAME trong .env).")
            st.stop()
        st.session_state.admin_auth = {"kind": "basic", "user": u, "pass": p}
        st.rerun()
    st.stop()

_AUTH = st.session_state.admin_auth
if st.sidebar.button("Đăng xuất"):
    if _AUTH["kind"] == "bearer":
        try:
            httpx.post(f"{API_BASE_URL}/runner/logout", headers={"Authorization": f"Bearer {_AUTH['token']}"}, timeout=10.0)
        except httpx.HTTPError:
            pass
    st.session_state.admin_auth = None
    st.session_state.pop("runner_session", None)
    st.rerun()
st.sidebar.caption("Đăng nhập: " + ("admin Runner (Crawl + Automation)" if _AUTH["kind"] == "bearer" else "admin .env (chỉ Crawl)"))


def _client() -> httpx.Client:
    if _AUTH["kind"] == "bearer":
        return httpx.Client(base_url=API_BASE_URL, headers={"Authorization": f"Bearer {_AUTH['token']}"}, timeout=60.0)
    return httpx.Client(base_url=API_BASE_URL, auth=(_AUTH["user"], _AUTH["pass"]), timeout=60.0)


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


(tab_errors, tab_credentials, tab_reports,
 tab_auto_users, tab_auto_audit) = st.tabs([
    "Crawl · Job lỗi & gợi ý sửa", "Crawl · Cookie", "Crawl · Báo lỗi từ người dùng",
    "Automation · Người dùng", "Automation · Audit",
])

# Đặt trước tab_errors vì tab đó có thể st.stop() khi API lỗi.
with st.sidebar.expander("💬 Phản hồi AI đã chuyển admin", expanded=False):
    _fb = _api_get("/admin/feedback") or []
    st.caption(f"{len(_fb)} phản hồi đang chờ xử lý (AI kết luận là lỗi hoặc không đủ chắc chắn).")
    for _item in _fb:
        st.markdown(f"**{_item.get('screen')}** · {_item.get('occurred_at', '')[:19]}\n\n{_item.get('message')}")
        st.caption(f"AI: is_bug={_item.get('ai_is_bug')} · confidence={_item.get('ai_confidence')}")
        if _item.get("ai_diagnosis"):
            st.write(_item["ai_diagnosis"])
        with st.popover("Trace"):
            st.json(_item.get("trace", {}))
        if st.button("Đã xử lý", key=f"fb_resolve_{_item['feedback_id']}"):
            _api_post(f"/admin/feedback/{_item['feedback_id']}/resolve")
            st.rerun()
        st.divider()

with tab_errors:
    if st.button("🔄 Tải lại danh sách lỗi"):
        st.rerun()

    errors = _api_get("/admin/errors") or {}

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


try:
    from ui.feedback import feedback_panel
except ModuleNotFoundError as exc:
    if exc.name != "ui":
        raise
    from feedback import feedback_panel

_admin_fb_post = lambda path, body: _api_post(path, body)
feedback_panel(_admin_fb_post, "admin")


# ---- Automation (Runner): quản lý user, yêu cầu quên mật khẩu, audit ---------
def _runner_api(method: str, path: str, body: Optional[dict] = None) -> Optional[Any]:
    try:
        with _client() as client:
            resp = client.request(method, "/runner" + path, json=body)
        if resp.status_code >= 400:
            st.error(f"Automation {resp.status_code}: {resp.text[:300]}")
            return None
        return resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        st.error(f"Không gọi được API Automation: {exc}")
        return None


from datetime import datetime, timezone

with tab_auto_users:
    if _AUTH["kind"] != "bearer":
        st.info("Đăng nhập bằng tài khoản admin Runner để quản lý Automation "
                "(đăng nhập hiện tại là admin .env, chỉ dùng cho Crawl).")
    else:
        me = _runner_api("GET", "/me") or {}
        pending = _runner_api("GET", "/password-reset-requests") or []
        if pending:
            st.warning(f"Có {len(pending)} yêu cầu quên mật khẩu đang chờ xử lý.")
            for req in pending:
                st.write(f"**{req['username']}** — yêu cầu lúc "
                         + datetime.fromtimestamp(req["created_at"], timezone.utc).isoformat())
            st.caption("Đặt lại mật khẩu cho đúng người ở danh sách bên dưới — yêu cầu tự biến mất khi xong.")
            st.markdown("---")
        with st.form("admin_new_runner_user", clear_on_submit=True):
            new_name = st.text_input("Username mới")
            new_password = st.text_input("Mật khẩu (tối thiểu 12 ký tự)", type="password")
            role = st.selectbox("Role", ["user", "admin"])
            if st.form_submit_button("Tạo user"):
                if _runner_api("POST", "/users", {"username": new_name, "password": new_password, "role": role}):
                    st.success("Đã tạo user")
        for u in _runner_api("GET", "/users") or []:
            st.write(u)
            if u["id"] != me.get("id") and st.button("Khóa" if u["is_active"] else "Mở khóa", key="active_" + u["id"]):
                _runner_api("PATCH", "/users/" + u["id"], {"is_active": not u["is_active"]})
                st.rerun()
            with st.expander(f"Đặt lại mật khẩu cho {u['username']}"):
                with st.form(f"reset_pw_{u['id']}", clear_on_submit=True):
                    new_pw = st.text_input("Mật khẩu mới (tối thiểu 12 ký tự)", type="password", key="new_pw_" + u["id"])
                    if st.form_submit_button("Đặt lại"):
                        if _runner_api("POST", f"/users/{u['id']}/reset-password", {"new_password": new_pw}):
                            st.success(f"Đã đặt mật khẩu mới cho {u['username']} — tự báo lại cho user qua kênh khác.")

with tab_auto_audit:
    if _AUTH["kind"] != "bearer":
        st.info("Cần đăng nhập bằng tài khoản admin Runner.")
    else:
        st.dataframe(_runner_api("GET", "/audit") or [])
