"""Runner UI: chỉ gọi HTTP; browser UAT và credential ở máy người dùng."""
import sys
from pathlib import Path

# `streamlit run` chỉ thêm thư mục của script vào sys.path; cần thư mục gốc để import `ui.*`, `src.*`.
_PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import base64
from datetime import datetime, timezone
import os

import httpx
import streamlit as st
from ui.theme import apply_theme, hero

API = os.environ.get("API_BASE_URL", "http://localhost:8000").rstrip("/")
apply_theme("Automation")
hero("Automation", "Mô tả flow, ghi thao tác và chạy testcase — thao tác trình duyệt chạy trên máy của bạn, kết quả lưu ngay tại máy.")
st.caption("Đăng nhập chỉ dành cho Runner. Chức năng crawl ở trang chính dùng được không cần đăng nhập Runner.")


def api(method, path, body=None, binary=False):
    session = st.session_state.get("runner_session", "")
    headers = {"Authorization": f"Bearer {session}"} if session else {}
    try:
        with httpx.Client(base_url=API, headers=headers, timeout=300) as client:
            response = client.request(method, "/runner" + path, json=body)
        if response.status_code == 401:
            for key in list(st.session_state):
                if key.startswith("runner_recording_"):
                    st.session_state.pop(key, None)
            st.session_state.pop("runner_session", None)
            st.session_state.pop("runner_describe_draft", None)
            st.session_state.pop("runner_locator_draft", None)
            st.session_state.runner_discovery_generation = st.session_state.get("runner_discovery_generation", 0) + 1
            st.error("Cần đăng nhập lại.")
            return None
        if response.status_code == 404:
            st.error("Không tìm thấy tài nguyên hoặc server chưa bật RUNNER_ENABLED.")
            return None
        if response.is_error:
            st.error(f"Yêu cầu không thành công ({response.status_code}). Kiểm tra cấu hình và quyền truy cập.")
            try:
                st.caption(f"Chi tiết: {response.text[:500]}")
            except Exception:
                pass
            return None
        return response.content if binary else response.json()
    except httpx.HTTPError as exc:
        st.error(f"Lỗi kết nối backend: {type(exc).__name__}: {exc}")
        st.caption(f"API: {API} | Endpoint: /runner{path}")
        return None
    except Exception as exc:
        st.error(f"Lỗi không xác định: {type(exc).__name__}: {exc}")
        return None


def _feedback_post(path, body):
    try:
        with httpx.Client(base_url=API, timeout=60) as client:
            response = client.post(path, json=body)
        data = response.json()
        if response.status_code >= 400:
            return {"_http_error": response.status_code, "detail": data.get("detail")}
        return data
    except (httpx.HTTPError, ValueError):
        return None


try:
    from ui.feedback import feedback_panel
except ModuleNotFoundError as exc:
    if exc.name != "ui":
        raise
    from feedback import feedback_panel
try:
    from ui.runner_setup_guide import render as render_setup_guide
    from ui.runner_overview import render as render_overview
except ModuleNotFoundError as exc:
    if exc.name != "ui":
        raise
    from runner_setup_guide import render as render_setup_guide
    from runner_overview import render as render_overview
with st.sidebar:
    feedback_panel(_feedback_post, "runner")


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

    with st.expander("Quên mật khẩu?"):
        st.caption(
            "Gửi yêu cầu tới admin — admin sẽ đặt lại mật khẩu mới cho bạn và báo lại qua kênh khác "
            "(hệ thống chưa gửi email tự động)."
        )
        with st.form("runner_forgot_password", clear_on_submit=True):
            forgot_username = st.text_input("Username của bạn")
            forgot_submitted = st.form_submit_button("Gửi yêu cầu tới admin")
        if forgot_submitted:
            result = api("POST", "/forgot-password", {"username": forgot_username})
            if result:
                st.success(result["detail"])
    st.stop()

# Hiện sau khi đăng nhập: mở sẵn ở lần đầu của phiên, các lần sau thu gọn (vẫn nằm ngay đầu trang).
render_overview(expanded=not st.session_state.get("runner_guide_seen", False))
render_setup_guide(expanded=not st.session_state.get("runner_guide_seen", False))
st.session_state.runner_guide_seen = True

me = api("GET", "/me")
if not me:
    st.stop()
st.caption(f"{me['username']} · {me['role']}")
if st.sidebar.button("Đăng xuất Runner"):
    for key in list(st.session_state):
        if key.startswith("runner_recording_"):
            st.session_state.pop(key, None)
    api("POST", "/logout")
    st.session_state.pop("runner_session", None)
    st.session_state.pop("runner_describe_draft", None)
    st.session_state.pop("runner_locator_draft", None)
    st.session_state.runner_discovery_generation = st.session_state.get("runner_discovery_generation", 0) + 1
    st.rerun()

tabs = st.tabs(["Chạy testcase", "Lịch sử & kết quả", "Agent", "Thông báo", "Describe", "Record local", "Inspector local"])

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
            result_blocks = st.number_input("Số khối kết quả cần cột expected (chỉ cho read_result_group)",
                                            min_value=1, max_value=100, value=1, step=1)
            st.caption("Nhóm nhập lặp: nêu rõ trong mô tả; bạn tự nhập danh sách giá trị phân cách bằng dấu ;. "
                       "Số khối chỉ thêm cột trống, không đổi settings hoặc số lần thực thi.")
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
                    "description": description, "reviewed_no_secrets": True, "result_blocks": result_blocks}, binary=True)
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
    st.caption("Recorder ghi click, fill, select, check/uncheck và upload bằng vị trí phần tử, hỗ trợ iframe/shadow DOM mở; không ghi giá trị input, nội dung file hoặc URL.")
    st.write("Ctrl+Alt+N: bắt đầu màn hình kế tiếp trước khi thao tác trên màn hình đó. "
             "Ctrl+Alt+P: tạm dừng/tiếp tục ghi. Trạng thái và số màn hình hiện ở góc browser.")
    st.write("Rê chuột lên phần tử rồi Ctrl+Alt+W để thêm bước chờ hiển thị. "
             "Ctrl+Alt+A trên input/textarea/select để thêm bước đọc kết quả và cột expected trống; "
             "bạn tự nhập giá trị kỳ vọng. Chỉ đánh dấu đọc kết quả trên một màn hình cuối.")
    st.write("Workbook ghi step inactive và header testcases, không sinh testcase/settings. Ghép vào config hiện có bằng lệnh bên dưới, "
             "tự nhập testcase và rà soát trước khi bật các dòng cần chạy.")
    st.info("Recorder hỗ trợ iframe, shadow DOM mở, chọn file và checkbox/radio. "
            "Không thu tên/nội dung file; bạn tự nhập đường dẫn file trong testcase. Shadow DOM đóng cần cấu hình riêng. "
            "Recorder không tự nhận diện chuyển màn hình hoặc thu URL; dùng phím tắt để chia màn hình. "
            "Locator theo vị trí có thể đổi khi giao diện thay đổi. Xem Inspector để kiểm tra và đề xuất repair có xác nhận.")
    from ui.runner_recording import render as render_recording
    render_recording(api, capabilities if isinstance(capabilities, dict) else {})
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
               "Sau khi sửa locator, chạy lại Inspector trước khi tạo run mới.")
    st.subheader("Chọn phần tử để sửa locator")
    st.code("python repair_runner.py --config config/Describe_Draft.xlsx --row 2 --output config/Repaired_Draft.xlsx", language="bash")
    st.write("Dùng số dòng Excel trong báo cáo Inspector (dòng header là 1). Trong browser mới, tự mở đúng màn hình, "
             "rê chuột lên phần tử thay thế và nhấn Ctrl+Alt+L. Xem CSS đề xuất ở terminal; nhập EXPORT để xuất bản sao hoặc q để hủy.")
    st.caption("Chỉ đổi locator_type/locator của dòng chọn, giữ các sheet và dữ liệu, đặt toàn bộ step/testcase trong bản sao về active=N. "
               "File gốc không đổi. Công cụ kiểm tra lại phần tử và hash workbook trước khi xuất; không gọi AI hay gửi DOM/input lên server.")
    from ui.runner_discovery import render as render_discovery
    render_discovery(api, capabilities if isinstance(capabilities, dict) else {})
    st.subheader("Chạy thử một step có xác nhận")
    st.code("python try_step_runner.py --config config/Prepared.xlsx --row 2 --output trial.json", language="bash")
    st.write("Lệnh này thực hiện một thao tác thật trên website. Tự mở đúng màn hình trong browser mới, chọn tab, "
             "kiểm tra phần tử được highlight và nhập EXECUTE 2 tại terminal để chạy dòng 2 đúng một lần.")
    st.caption("Hỗ trợ fill/click/check/select trực tiếp và wait CSS cấu trúc; fill/select hỏi giá trị thử bằng đầu vào ẩn. "
               "Không dùng testcase/credential file để lấy giá trị, không sửa workbook hay bật active. "
               "Step có group, prefill hoặc wait phức tạp cần chạy qua Runner đầy đủ.")
    st.info("ACTION_COMPLETED chỉ nghĩa là thao tác đã hoàn tất, không phải testcase PASS. "
            "Nếu báo OUTCOME_UNKNOWN hoặc còn EXECUTION_STARTED sau khi bị ngắt, kiểm tra website trước khi tự tạo lần thử mới; "
            "công cụ không retry. Báo cáo local chỉ chứa metadata.")

with tabs[0]:
    st.info("Runner chạy trên máy của bạn. Chỉ dùng testcase có dữ liệu giả hoặc placeholder; credential UAT được resolve local.")
    st.caption("Agent mới tự kiểm tra preflight trước khi mở browser. Nếu bị chặn, xem mã lỗi/sheet/dòng trong Lịch sử, "
               "sửa workbook local rồi tạo run mới. Không tự sửa settings, sinh testcase hoặc bật active.")
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
            late_result = r.get("late_result")
            if r["status"] == "LOST":
                st.warning("Backend đã mất theo dõi run. Không tạo run khác để thay thế trước khi kiểm tra máy local; "
                           "thao tác trên website có thể đã xảy ra.")
            if late_result:
                st.info("Agent đã gửi kết quả sau khi run bị đánh dấu LOST. Đây là kết quả nhận muộn, không phải một lần chạy lại.")
                st.write({"kết quả agent báo": late_result["status"], **{k: late_result[k]
                          for k in ("passed", "failed", "errors", "unverified", "duration")}})
                st.caption("Nhận lúc " + datetime.fromtimestamp(late_result["received_at"], timezone.utc).isoformat() +
                           ". Giữ trạng thái LOST và hạn lưu ban đầu để bảo toàn lịch sử mất kết nối.")
            report = r.get("preflight") or (late_result or {}).get("preflight")
            if report:
                if report["status"] == "blocked":
                    st.error("Bị chặn trước khi mở browser: cần sửa workbook local.")
                else:
                    st.info("Đã qua kiểm tra tĩnh. Kết quả này không xác nhận locator, đăng nhập hoặc hành vi UAT đúng.")
                st.write({"step active": report["active_steps"], "testcase active": report["active_testcases"]})
                if report.get("issues"):
                    st.dataframe(report["issues"], use_container_width=True)
                if report.get("warnings"):
                    st.warning("Có mục cần rà soát thêm")
                    st.dataframe(report["warnings"], use_container_width=True)
                if report.get("truncated"):
                    st.caption("Chỉ hiển thị tối đa 100 lỗi và 100 cảnh báo; kiểm tra toàn bộ bằng preflight_runner.py ở local.")
                st.caption("UNRESOLVED_LOCATOR/WAIT: kiểm tra locator nháp. SCREEN_NOT_IN_FLOW/RESULT_SCREEN_MISMATCH: "
                           "đối chiếu màn hình với settings; chỉ sửa settings khi cần và do người dùng quyết định. "
                           "ENTER_AND_ACTIVATE_USER_TESTCASES: tự nhập testcase và chọn active. "
                           "INVALID_WORKBOOK: kiểm tra định dạng và các sheet bắt buộc bằng công cụ local.")
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
    with st.expander("Gửi lại kết quả cũ sau khi cập nhật API"):
        st.write("Dùng khi journal đã REPORTED nhưng API cũ từng bỏ qua kết quả vì run LOST. "
                 "Chờ agent hết run rồi dừng vòng polling; dùng đúng token agent và thư mục state cũ.")
        st.code("python local_runner_agent.py --api <API_URL> --state <STATE_FOLDER> --resend-run <RUN_ID>")
        st.caption("Chỉ gửi lại metrics/preflight đã có trong journal, không nhận job hoặc chạy testcase. "
                   "Không chỉnh journal thủ công. Sau đó khởi động lại agent bình thường và làm mới lịch sử.")
    with st.expander("Kiểm tra journal tại máy local"):
        st.write("Journal lưu dấu vết để tránh chạy testcase hai lần. Lệnh kiểm tra chỉ đọc "
                 "metadata, không cần token và không kết nối API.")
        st.code("python local_runner_agent.py --state <STATE_FOLDER> --journal-status")
        st.code("python local_runner_agent.py --state <STATE_FOLDER> --journal-status --run-id <RUN_ID>")
        st.caption("Dùng Run ID trong lịch sử để kiểm tra riêng. REVIEW_REQUIRED hoặc mã thoát 2 "
                   "nghĩa là cần kiểm tra local, không phải kết luận testcase thất bại. "
                   "Kết quả có thể thay đổi khi agent đang ghi; không xóa journal/pending để ép chạy lại.")
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
    st.sidebar.info("Quản lý user, yêu cầu quên mật khẩu và audit ở trang **Admin** (đăng nhập chung).")
