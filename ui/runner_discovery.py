"""Reviewed structural discovery and repair proposals, no workbook upload."""
import streamlit as st
from src.runner.discovery import Snapshot


def render(api, capabilities):
    st.subheader("AI hỗ trợ chọn locator từ Inspector")
    st.code("python discover_runner.py --output discovery.json", language="bash")
    st.write("Tự mở màn hình trong browser local. Chọn số tab; nhập c1, c2… để highlight và nhận diện phần tử. "
             "Nhập EXPORT để xuất snapshot. Chỉ có vị trí và loại phần tử; không có text, URL hay giá trị input.")
    st.caption("Mỗi snapshot là một màn hình. Trong mô tả, chỉ rõ ID và thao tác, ví dụ: "
               "c1 là tài khoản, c2 là mật khẩu, điền từ account rồi click c3. "
               "Không gửi credential hoặc dữ liệu khách hàng. AI chỉ chọn trong các ID bạn đã chỉ định.")
    st.write("Với flow nhiều màn hình, xuất nháp riêng từng màn hình, nêu tên screen và tên step khác nhau trong mô tả. "
             "Ghép nháp theo thứ tự thực hiện rồi dùng prepare_runner.py ghép với config hiện có:")
    st.code("python compose_runner.py --draft config/Login_Draft.xlsx --draft config/Search_Draft.xlsx "
            "--output config/Flow_Draft.xlsx", language="bash")
    if not capabilities.get("discovery"):
        st.info("Discovery/repair AI chưa được bật trên backend.")
        return
    generation = st.session_state.get("runner_discovery_generation", 0)
    upload = st.file_uploader("Snapshot cấu trúc đã rà soát", type=["json"], key=f"runner_snapshot_{generation}")
    snapshot = None
    if upload:
        try:
            if upload.size > 250000:
                raise ValueError()
            snapshot = Snapshot.model_validate_json(upload.getvalue())
            st.dataframe([c.model_dump() for c in snapshot.candidates], use_container_width=True)
            if snapshot.truncated:
                st.warning("Snapshot chỉ chứa 100 phần tử đầu; đổi màn hình hoặc dùng picker local cho phần tử khác.")
        except ValueError:
            st.error("Snapshot không đúng định dạng. Chỉ chọn JSON từ discover_runner.py.")
    with st.form("runner_discovery", clear_on_submit=True):
        mode = st.radio("Loại đề xuất", ["Tạo steps cho màn hình", "Sửa một locator"])
        description = st.text_area("Mô tả thao tác và ID phần tử", max_chars=6000)
        action = st.selectbox("Action của dòng cần sửa (chỉ dùng khi sửa locator)",
            ["click", "fill", "force_fill", "fill_enter", "select", "click_if_exists", "read_result_single"])
        read_method = st.selectbox("Read method của dòng cần sửa", ["", "css_input", "css_disabled"])
        reviewed = st.checkbox("Tôi đã rà soát snapshot và mô tả, đồng ý gửi cấu trúc này cho AI.")
        submit = st.form_submit_button("Tạo đề xuất locator")
    if submit:
        st.session_state.pop("runner_locator_draft", None)
        if snapshot is None or not reviewed or len(description.strip()) < 10:
            st.error("Cần snapshot hợp lệ, mô tả đủ rõ và xác nhận rà soát.")
        else:
            body = {"snapshot": snapshot.model_dump(), "description": description, "reviewed_no_secrets": True}
            repairing = mode == "Sửa một locator"
            if repairing:
                body.update(action=action, read_method=read_method)
            content = api("POST", "/authoring/repair" if repairing else "/authoring/discover", body, binary=True)
            if content:
                st.session_state.runner_locator_draft = {
                    "content": content, "repair": repairing, "fingerprint": snapshot.fingerprint()}
    draft = st.session_state.get("runner_locator_draft")
    if draft and snapshot and draft["fingerprint"] == snapshot.fingerprint():
        st.download_button("Tải đề xuất locator", draft["content"],
            "Repair_Proposal.json" if draft["repair"] else "Discovered_Draft.xlsx",
            "application/json" if draft["repair"] else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        st.info("Chưa chạy testcase hoặc xác minh đúng nghiệp vụ. Nháp chỉ có steps inactive và header testcases; "
                "đề xuất sửa phải được highlight và xác nhận lại tại máy local.")
    st.code("python repair_runner.py --config config/Existing.xlsx --row 2 --snapshot discovery.json "
            "--proposal Repair_Proposal.json --output config/Repaired_Draft.xlsx", language="bash")
    st.caption("Tự mở đúng màn hình, chọn tab, kiểm tra phần tử được highlight rồi nhập EXPORT. "
               "Nguồn giữ nguyên; bản sao giữ dữ liệu/settings và đặt steps/testcases inactive. "
               "Không tự chạy lại run đã lỗi. Sau khi rà soát, bạn quyết định tạo run mới.")
    if st.button("Xóa snapshot và đề xuất khỏi phiên"):
        st.session_state.pop("runner_locator_draft", None)
        st.session_state.runner_discovery_generation = generation + 1
        st.rerun()
