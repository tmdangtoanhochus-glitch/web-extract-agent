from datetime import time
import streamlit as st


def schedule_controls(job, api_patch):
    job_id = job["job_id"]
    enabled = job.get("enabled", True)
    st.caption(f"{'Đang bật' if enabled else 'Đã tạm dừng'} · Múi giờ: {job.get('timezone', 'theo backend')} · "
               f"Lần tới: {job.get('next_run_at') or 'chưa có'}")
    if st.button("Tạm dừng lịch" if enabled else "Bật lại lịch", key=f"toggle_schedule_{job_id}"):
        result = api_patch(f"/schedules/{job_id}", {"enabled": not enabled})
        if result and not result.get("_http_error"):
            st.rerun()
        else:
            st.error("Chưa đổi được trạng thái lịch")
    with st.expander("Đổi thời gian chạy", expanded=False):
        st.caption("Chỉ thay thời gian chạy; giữ nguyên nguồn, dataset/file và cấu hình bảng. "
                   "Lịch đang tạm dừng vẫn tạm dừng sau khi sửa. Lượt đã bắt đầu được chạy hết.")
        st.json(job["trigger_args"])
        with st.form(f"schedule_edit_{job_id}"):
            kind = st.radio("Kiểu lịch mới", ["Theo chu kỳ", "Hàng ngày"], index=0 if job["trigger_type"] == "interval" else 1)
            zone = job.get("timezone") or job["trigger_args"].get("timezone") or "UTC"
            choices = list(dict.fromkeys([zone, "Asia/Ho_Chi_Minh", "UTC"]))
            timezone = st.selectbox("Múi giờ lịch", choices)
            if kind == "Theo chu kỳ":
                hours = st.number_input("Chu kỳ mới (giờ)", min_value=1, max_value=8760, value=24)
                trigger_type, args = "interval", {"hours": hours, "timezone": timezone}
            else:
                hour = str(job["trigger_args"].get("hour", "8"))
                minute = str(job["trigger_args"].get("minute", "0"))
                initial = (time(int(hour), int(minute))
                           if hour.isdigit() and minute.isdigit() and int(hour) < 24 and int(minute) < 60
                           else time(8, 0))
                clock = st.time_input("Giờ chạy mới", value=initial)
                trigger_type, args = "cron", {"hour": clock.hour, "minute": clock.minute, "timezone": timezone}
            apply = st.form_submit_button("Lưu thời gian mới")
        if apply:
            result = api_patch(f"/schedules/{job_id}", {"trigger_type": trigger_type, "trigger_args": args})
            if result and not result.get("_http_error"):
                st.rerun()
            else:
                st.error(result.get("detail") if result else "Chưa lưu được thời gian mới")
