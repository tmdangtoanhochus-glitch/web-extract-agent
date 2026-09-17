"""Runner UI: chỉ gọi HTTP; browser UAT và credential ở máy người dùng."""
import base64
from datetime import datetime, timezone
import os

import httpx
import streamlit as st

API = os.environ.get("API_BASE_URL", "http://localhost:8000").rstrip("/")
st.set_page_config(page_title="Local Runner", page_icon="▶", layout="wide")
st.title("Local Runner")
st.caption("Đăng nhập chỉ dành cho Runner. Chức năng crawl ở trang chính dùng được không cần đăng nhập Runner.")


def api(method, path, body=None, binary=False):
    headers = {"Authorization": "Bearer " + st.session_state.get("runner_session", "")}
    try:
        with httpx.Client(base_url=API, headers=headers, timeout=30) as client:
            response = client.request(method, "/runner" + path, json=body)
        if response.status_code == 401:
            st.session_state.pop("runner_session", None)
            st.session_state.pop("runner_describe_draft", None)
            st.error("Cần đăng nhập lại.")
            return None
        if response.status_code == 404:
            st.error("Không tìm thấy tài nguyên hoặc server chưa bật RUNNER_ENABLED.")
            return None
        if response.is_error:
            st.error(f"Yêu cầu không thành công ({response.status_code}). Kiểm tra cấu hình và quyền truy cập.")
            return None
        return response.content if binary else response.json()
    except httpx.HTTPError:
        st.error("Không kết nối được backend.")
        return None


if "runner_session" not in st.session_state:
    with st.form("runner_login", clear_on_submit=True):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Đăng nhập")
    if submitted:
        result = api("POST", "/login", {"username": username, "password": password})
        if result:
            st.session_state.runner_session = result["session"]
            st.rerun()
    st.stop()

me = api("GET", "/me")
if not me:
    st.stop()
st.caption(f"{me['username']} · {me['role']}")
if st.sidebar.button("Đăng xuất Runner"):
    api("POST", "/logout")
    st.session_state.pop("runner_session", None)
    st.session_state.pop("runner_describe_draft", None)
    st.rerun()

tabs = st.tabs(["Chạy testcase", "Lịch sử & kết quả", "Agent", "Thông báo"] +
               (["Quản trị"] if me["role"] == "admin" else []) + ["Describe", "Record local", "Inspector local"])

with tabs[-3]:
    st.subheader("Mô tả flow để tạo workbook nháp")
    capabilities = api("GET", "/authoring/capabilities") or {}
    if not isinstance(capabilities, dict) or not capabilities.get("describe"):
        st.info("Describe AI chưa được bật trên backend (RUNNER_AI_ENABLED).")
    else:
        st.caption("AI chỉ tạo sheet steps và cột mẫu testcases; bạn tự nhập mọi testcase. Không sinh hoặc tự đổi settings. Website chưa được inspect. "
                   "Không nhập URL nội bộ, dữ liệu khách hàng hay credential; chỉ dùng role/placeholder.")
        with st.form("runner_describe", clear_on_submit=True):
            description = st.text_area("Mô tả testcase", max_chars=6000,
                                       placeholder="Đăng nhập bằng account, tìm theo CIF rồi đọc số tiền để kiểm tra. Chỉ tạo step và cột input/expected; tôi tự nhập testcase.")
            reviewed = st.checkbox("Tôi đã kiểm tra mô tả không chứa secret hoặc dữ liệu nhạy cảm và đồng ý gửi cho AI.")
            generate = st.form_submit_button("Tạo workbook nháp")
        if generate:
            st.session_state.pop("runner_describe_draft", None)
            if not reviewed:
                st.error("Cần kiểm tra nội dung trước khi gửi cho AI.")
            elif len(description.strip()) < 10:
                st.error("Nhập mô tả ít nhất 10 ký tự.")
            else:
                content = api("POST", "/authoring/describe", {
                    "description": description, "reviewed_no_secrets": True}, binary=True)
                if content:
                    st.session_state.runner_describe_draft = content
        if st.session_state.get("runner_describe_draft"):
            st.download_button("Tải workbook nháp", st.session_state.runner_describe_draft,
                               "Describe_Draft.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            st.info("Step chưa hoạt động (active=N); sheet testcases chỉ có header. Dùng prepare_runner.py ghép với config hiện có, "
                    "sau đó tự nhập testcase và rà soát locator. Settings chỉ đổi khi bạn duyệt từng đề xuất có giải thích.")
            if st.button("Xóa bản nháp khỏi phiên"):
                st.session_state.pop("runner_describe_draft", None)
                st.rerun()

with tabs[-2]:
    st.subheader("Ghi thao tác trên máy của bạn")
    st.write("Mở terminal tại project trên máy truy cập được website và chạy:")
    st.code("python record_runner.py --output config/Recorded_Draft.xlsx", language="bash")
    st.write("Trong browser mới, tự mở website và thao tác. Đóng các tab để xuất workbook nháp.")
    st.caption("Recorder ghi click, fill và select chuẩn bằng vị trí phần tử; không ghi giá trị input, nội dung trang hoặc URL.")
    st.write("Workbook ghi step inactive và header testcases, không sinh testcase/settings. Ghép vào config hiện có bằng lệnh bên dưới, "
             "tự nhập testcase và rà soát trước khi bật các dòng cần chạy.")
    st.info("Iframe, shadow DOM, upload, checkbox/radio và dropdown tùy biến cần cấu hình thủ công. "
            "Locator theo vị trí có thể đổi khi giao diện thay đổi. Xem tab Describe để tạo nháp bằng AI; sửa locator tự động chưa có.")
    st.subheader("Ghép step vào config trên máy local")
    st.code("python prepare_runner.py --template config/Existing.xlsx --draft config/Recorded_Draft.xlsx --output config/Prepared.xlsx", language="bash")
    st.caption("Áp dụng cho cả nháp Describe và Record. Giữ nguyên settings và testcase bạn đã nhập; chỉ bổ sung header còn thiếu. "
               "Nếu hàm Runner cần đổi screen_flow/login_screen/result_screen, terminal giải thích và hỏi từng mục; mặc định giữ nguyên.")
    st.code("python preflight_runner.py --config config/Prepared.xlsx", language="bash")
    st.caption("Sau khi tự nhập testcase: kiểm tra cấu trúc, dòng active và locator nháp, không mở browser hay đọc secret. "
               "Kết quả này chưa xác minh credential, website hoặc nghiệp vụ.")

with tabs[-1]:
    st.subheader("Kiểm tra locator trên máy local")
    st.code("python inspect_runner.py --config config/Describe_Draft.xlsx --output inspection.json", language="bash")
    st.write("Tự mở website và đăng nhập trong browser mới. Tại terminal, chọn số màn hình trong workbook "
             "và số tab browser, ví dụ 1 1. Chuyển màn hình thủ công rồi kiểm tra tiếp; nhập q để lưu báo cáo và đóng browser.")
    st.write("Inspector kiểm tra cả step inactive, dùng locator đã có trong workbook. Báo cáo chỉ có số dòng, "
             "số phần tử khớp và trạng thái; không chứa DOM, URL, locator hay giá trị input.")
    st.info("UNIQUE_VISIBLE chỉ xác nhận một phần tử đang hiển thị, chưa chứng minh đúng mục tiêu hoặc testcase pass. "
            "Locator placeholder, wait, dropdown tùy biến và cách đọc kết quả phức tạp cần rà soát thủ công.")
    st.caption("Không tự sửa workbook, chạy thao tác nghiệp vụ hoặc gửi báo cáo lên server. "
               "Sau khi sửa locator, chạy lại Inspector; AI repair chưa triển khai.")
    st.subheader("Chọn phần tử để sửa locator")
    st.code("python repair_runner.py --config config/Describe_Draft.xlsx --row 2 --output config/Repaired_Draft.xlsx", language="bash")
    st.write("Dùng số dòng Excel trong báo cáo Inspector (dòng header là 1). Trong browser mới, tự mở đúng màn hình, "
             "rê chuột lên phần tử thay thế và nhấn Ctrl+Alt+L. Xem CSS đề xuất ở terminal; nhập EXPORT để xuất bản sao hoặc q để hủy.")
    st.caption("Chỉ đổi locator_type/locator của dòng chọn, giữ các sheet và dữ liệu, đặt toàn bộ step/testcase trong bản sao về active=N. "
               "File gốc không đổi. Công cụ kiểm tra lại phần tử và hash workbook trước khi xuất; không gọi AI hay gửi DOM/input lên server.")

with tabs[0]:
    st.info("Runner chạy trên máy của bạn. Chỉ dùng testcase có dữ liệu giả hoặc placeholder; credential UAT được resolve local.")
    agents = [a for a in api("GET", "/agents") or [] if a["active"]]
    if not agents:
        st.warning("Tạo agent tại tab Agent rồi khởi động local_runner_agent.py trên máy của bạn.")
    else:
        selected = st.selectbox("Agent", [a["id"] for a in agents])
        mode = st.radio("Nguồn testcase", ["File có sẵn trên máy agent", "Upload tạm"], horizontal=True)
        if mode == "File có sẵn trên máy agent":
            st.caption("Nhập tên file nằm trong thư mục --configs của agent. Nội dung không upload lên server.")
            name = st.text_input("Tên file", placeholder="UAT_Login.xlsx")
            if st.button("Tạo run", type="primary", disabled=not name):
                result = api("POST", "/runs", {"agent_id": selected, "config_name": name, "local_ref": name})
                if result:
                    st.success("Đã tạo run: " + result["run_id"])
        else:
            st.caption("Workbook sẽ được lưu tạm tới khi run kết thúc hoặc hết hạn chờ. Không upload runner.env.")
            generation = st.session_state.get("runner_upload_generation", 0)
            upload = st.file_uploader("Testcase Excel", type=["xlsx"], key=f"runner_upload_{generation}")
            if st.button("Upload & tạo run", type="primary", disabled=upload is None):
                if upload.size > 10 * 1024 * 1024:
                    st.error("Giới hạn 10 MB.")
                else:
                    result = api("POST", "/runs", {"agent_id": selected, "config_name": upload.name,
                                 "config_base64": base64.b64encode(upload.getvalue()).decode()})
                    if result:
                        st.session_state.runner_upload_generation = generation + 1
                        st.session_state.runner_last_created = result["run_id"]
                        st.rerun()
            if st.session_state.get("runner_last_created"):
                st.success("Đã tạo run: " + st.session_state.runner_last_created)

with tabs[1]:
    st.button("Làm mới", key="refresh_runner")
    st.caption("Cloud lưu báo cáo tổng hợp. Excel chi tiết và screenshot đã mask nằm trong thư mục runs của agent local.")
    for r in api("GET", "/runs") or []:
        with st.expander(r["run_id"] + " · " + r["status"]):
            st.write({k: r[k] for k in ("passed", "failed", "errors", "unverified", "duration")})
            if r["expires_at"]:
                expiry = datetime.fromtimestamp(r["expires_at"], timezone.utc)
                st.caption("Hạn artifact: " + expiry.isoformat())
            if r["deleted_at"]:
                st.info("Artifact đã xóa theo retention; metadata được giữ lại.")
            elif r["status"] not in ("QUEUED", "RUNNING"):
                if st.button("Chuẩn bị tải báo cáo", key="fetch_"+r["run_id"]):
                    content = api("GET", f"/runs/{r['run_id']}/artifacts/summary.json", binary=True)
                    if content:
                        st.download_button("Tải JSON", data=content, file_name=r["run_id"]+".json",
                                           mime="application/json", key="dl_"+r["run_id"])
            if r["status"] == "QUEUED" and st.button("Hủy run đang chờ", key="cancel_"+r["run_id"]):
                api("POST", f"/runs/{r['run_id']}/cancel")
                st.rerun()

with tabs[2]:
    st.write("Tạo agent, nhận token một lần rồi nhập vào chương trình local. Token này chỉ xác thực agent với API.")
    if st.button("Tạo agent mới"):
        result = api("POST", "/agents")
        if result:
            st.write("Agent ID:", result["agent_id"])
            st.code(result["agent_token"], language="text")
            st.warning("Lưu token tại máy của bạn. Khi rời trang, token không được hiển thị lại.")
    st.code("python local_runner_agent.py --api <API_URL> --configs <CONFIG_FOLDER> --env-path <LOCAL_ENV_PATH>")
    for a in api("GET", "/agents") or []:
        st.write(a)
        if a["active"] and st.button("Thu hồi agent", key="revoke_"+a["id"]):
            api("DELETE", "/agents/"+a["id"])
            st.rerun()

with tabs[3]:
    for n in api("GET", "/notifications") or []:
        st.warning(f"Artifact {n['run_id']} sẽ hết hạn. Hãy tải báo cáo trước hạn xóa: " +
                   datetime.fromtimestamp(n["delete_after"], timezone.utc).isoformat())

if me["role"] == "admin":
    with tabs[4]:
        with st.form("new_runner_user", clear_on_submit=True):
            new_name = st.text_input("Username mới")
            new_password = st.text_input("Mật khẩu (tối thiểu 12 ký tự)", type="password")
            role = st.selectbox("Role", ["user", "admin"])
            if st.form_submit_button("Tạo user"):
                if api("POST", "/users", {"username": new_name, "password": new_password, "role": role}):
                    st.success("Đã tạo user")
        for u in api("GET", "/users") or []:
            st.write(u)
            if u["id"] != me["id"] and st.button("Khóa" if u["is_active"] else "Mở khóa", key="active_"+u["id"]):
                api("PATCH", "/users/"+u["id"], {"is_active": not u["is_active"]})
                st.rerun()
        with st.expander("Audit Runner"):
            st.dataframe(api("GET", "/audit") or [])
