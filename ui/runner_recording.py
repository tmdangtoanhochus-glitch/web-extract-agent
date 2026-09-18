"""Người dùng duyệt metadata Recorder trước khi gửi AI biên dịch cấu hình Runner."""
import hashlib
import json

import streamlit as st
from src.runner.recording_plan import RecordingTrace


def render(api, capabilities):
    st.subheader("AI chuẩn hóa bản ghi theo Runner")
    st.code("python record_runner.py --output config/Recorded_Draft.xlsx --events-output config/Recorded_Events.json")
    st.write("Bạn thao tác trong browser Inspector/Recorder. Tải JSON cấu trúc lên đây để AI chọn action "
             "và tạo đầy đủ cột theo Runner; workbook ghi thô ở trên dùng để đối chiếu.")
    if not capabilities.get("recording"):
        st.info("Backend chưa bật AI chuẩn hóa bản ghi.")
        return
    upload = st.file_uploader("Bản ghi cấu trúc Recorder (.json)", type=["json"], key="runner_recording_upload")
    trace = None
    if upload is not None:
        try:
            if upload.size > 2_000_000:
                raise ValueError()
            trace = RecordingTrace.model_validate(json.loads(upload.getvalue()))
        except (ValueError, TypeError):
            st.error("JSON không đúng định dạng Recorder hoặc quá lớn; không gửi nội dung lên AI.")
    description = st.text_area("Giải thích flow và ý nghĩa các thao tác", key="runner_recording_description",
                               max_chars=6000, placeholder="Sự kiện 1 nhập mã hồ sơ; 2–3 chọn đơn vị; 4 lưu; 5 đọc kết quả.")
    fingerprint = hashlib.sha256((trace.model_dump_json() + description).encode()).hexdigest() if trace else None
    if st.session_state.get("runner_recording_fingerprint") != fingerprint:
        st.session_state.pop("runner_recording_draft", None)
        st.session_state.runner_recording_reviewed = False
        st.session_state.runner_recording_fingerprint = fingerprint
    if trace:
        st.dataframe([{"event": e.id, "screen": e.screen, "action": e.action, "widget": e.widget} for e in trace.events])
        if trace.dropped:
            st.warning(f"Recorder đã bỏ qua {trace.dropped} sự kiện; cần kiểm tra tính đầy đủ của flow.")
    reviewed = st.checkbox("Tôi đã rà JSON và mô tả, không có dữ liệu nhạy cảm; đồng ý gửi metadata cho AI.",
                           key="runner_recording_reviewed")
    if st.button("Chuẩn hóa thành steps cho Runner", key="runner_recording_compile"):
        st.session_state.pop("runner_recording_draft", None)
        if not trace or not reviewed or len(description.strip()) < 10:
            st.error("Cần bản ghi hợp lệ, mô tả ít nhất 10 ký tự và xác nhận rà soát.")
        else:
            content = api("POST", "/authoring/recording", {"recording": trace.model_dump(),
                "description": description, "reviewed_no_secrets": True}, binary=True)
            if content:
                st.session_state.runner_recording_draft = content
    if st.session_state.get("runner_recording_draft"):
        st.download_button("Tải workbook đã chuẩn hóa", st.session_state.runner_recording_draft,
                           "Runner_Compiled_Draft.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.caption("Sheet review ghi nguồn sự kiện và mục cần kiểm tra. AI không tự thao tác trên website. "
               "Steps vẫn inactive; testcase chỉ header. Dùng prepare_runner.py để ghép với config của bạn.")
