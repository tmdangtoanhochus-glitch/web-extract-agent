"""Background crawl progress and cooperative controls for one browser session."""
import httpx
import streamlit as st

try:
    from ui.crawl_progress import render_static
except ModuleNotFoundError as exc:
    if exc.name != "ui":
        raise
    from crawl_progress import render_static


def submit_background(api_post, bodies):
    try:
        result = api_post("/crawl-jobs", {"requests": bodies})
    finally:
        for body in bodies:
            body.pop("cookie_header", None)
    if result and not result.get("_http_error"):
        st.session_state.active_crawl_job = {**result, "configs": bodies, "handled": False}
        st.success("Đã đưa đợt kéo vào hàng đợi. Bạn có thể tạm dừng ở phần tiến độ bên dưới.")
    else:
        st.error(result.get("detail") if result else "Chưa gửi được đợt kéo")


@st.fragment(run_every=2)
def render_background(client_factory):
    job = st.session_state.get("active_crawl_job")
    if not job:
        return
    headers = {"X-Crawl-Control": job["control"]}
    path = f"/crawl-jobs/{job['id']}"
    try:
        with client_factory() as client:
            response = client.get(path, headers=headers)
            if response.status_code == 404:
                st.warning("Không còn trạng thái đợt kéo: backend có thể đã khởi động lại hoặc kết quả hết hạn. Dữ liệu đã lưu vẫn còn.")
                if st.button("Bỏ theo dõi đợt cũ"):
                    st.session_state.pop("active_crawl_job", None)
                    st.rerun()
                return
            response.raise_for_status()
            status = response.json()
    except (httpx.HTTPError, ValueError):
        st.warning("Chưa cập nhật được tiến độ; không tự gửi lại đợt kéo. Hãy thử cập nhật sau.")
        return
    state = status["state"]
    labels = {"queued": "Đang chờ", "running": "Đang kéo", "pause_requested": "Đang chờ tạm dừng",
              "paused": "Đã tạm dừng", "cancel_requested": "Đang chờ dừng", "cancelled": "Đã dừng",
              "completed": "Đã kết thúc", "failed": "Gặp lỗi"}
    st.subheader("Tiến độ đợt crawl")
    st.write(labels.get(state, state))
    progress = status.get("progress") or {}
    st.write({key: progress.get(key) for key in ("source_index", "sources", "processed", "requests", "saved", "skipped", "failed")})
    if progress.get("requests"):
        st.progress(min(progress.get("processed", 0) / progress["requests"], 1.0))
    if progress.get("phase"):
        st.caption("Nguồn đang xử lý: ① code tải/làm sạch trang, ② AI từng đoạn (mỗi nguồn đặt lại từ đầu).")
        render_static(progress)
    attempts = st.session_state.get("crawl_attempts", [])
    position = len(attempts) - len(job["configs"]) + progress.get("source_index", 1) - 1
    if progress.get("request_id") and 0 <= position < len(attempts):
        attempts[position]["request_id"] = progress["request_id"]
    terminal = state in {"completed", "failed", "cancelled"}
    st.caption("Tạm dừng/dừng có hiệu lực sau request hiện tại; không ngắt cưỡng bức HTTP/AI hoặc xóa dữ liệu đã lưu. "
               "Sau 15 phút tạm dừng, đợt tự dừng. Mất phiên trình duyệt sẽ mất mã điều khiển.")
    action = None
    left, middle, right = st.columns(3)
    if left.button("Tạm dừng crawl", disabled=terminal or state in {"paused", "pause_requested", "cancel_requested"}):
        action = "pause"
    if middle.button("Tiếp tục crawl", disabled=state not in {"paused", "pause_requested"}):
        action = "resume"
    if right.button("Dừng hẳn đợt kéo", disabled=terminal or state == "cancel_requested"):
        action = "cancel"
    if action:
        try:
            with client_factory() as client:
                response = client.post(path + "/control", json={"action": action}, headers=headers)
                response.raise_for_status()
            st.rerun()
        except httpx.HTTPError:
            st.error("Chưa gửi được yêu cầu điều khiển")
    if terminal and not job["handled"]:
        result = status.get("result") or {}
        for index, item in enumerate(result.get("items", [])):
            config = job["configs"][index]
            attempt_index = len(attempts) - len(job["configs"]) + index
            if item.get("request_id") and 0 <= attempt_index < len(attempts):
                attempts[attempt_index]["request_id"] = item["request_id"]
            st.session_state.run_log.append({**item, "_retry_config": config})
            if item.get("file_path") and item["file_path"] not in st.session_state.run_file_paths:
                st.session_state.run_file_paths.append(item["file_path"])
            if item.get("dataset_id"):
                st.session_state.run_dataset_id = item["dataset_id"]
                st.session_state.last_crawl_config = {**config, "dataset_id": item["dataset_id"]}
            elif item.get("file_path"):
                st.session_state.last_crawl_config = dict(config)
        if status.get("error"):
            st.session_state.run_log.append({"url": "Đợt crawl nền", "status": "error", "detail": status["error"]["detail"]})
        job["handled"] = True
        st.rerun()
    if terminal:
        st.caption("Chi tiết kết quả được ghi ở Console log. Dừng hẳn không tự chạy lại phần chưa kéo.")
