"""Public crawl controls; contains no backend/storage imports."""
from datetime import date, timedelta
from urllib.parse import urlsplit
import streamlit as st


def options_controls(fields):
    enabled = st.checkbox("Kéo nhiều lượt / kéo bảng", key="bulk_enabled")
    if not enabled:
        st.session_state.bulk_options = None
        return None
    st.caption("URL mẫu: https://example.com/history?from={start}&to={end}&page={page}. "
               "Tên tham số phải theo website nguồn; ngày thay vào dạng YYYY-MM-DD. "
               "Chỉ lấy được lịch sử mà nguồn còn cung cấp. Tối đa 100 lượt mỗi đợt.")
    mode = st.radio("Kiểu dữ liệu", ["Trường trên mỗi trang", "Bảng HTML"], horizontal=True)
    options = {"mode": "table" if mode == "Bảng HTML" else "fields"}
    if st.checkbox("Giới hạn khoảng ngày"):
        first = st.date_input("Từ ngày (bao gồm)", value=date.today() - timedelta(days=7))
        last = st.date_input("Đến ngày (bao gồm)", value=date.today())
        options.update(start_date=first.isoformat(), end_date=last.isoformat())
        options["window_days"] = st.number_input("Số ngày mỗi lượt", min_value=1, max_value=366, value=1)
    options["page_start"] = st.number_input("Trang bắt đầu", min_value=0, max_value=100000, value=1)
    options["pages"] = st.number_input("Số trang mỗi khoảng", min_value=1, max_value=100, value=1)
    if options["mode"] == "table":
        st.caption("Mỗi dòng bảng thành một record. Chọn đúng một bảng bằng CSS (ví dụ table hoặc #history). "
                   "Đánh số cột từ 1, từ trái sang phải. Bảng JavaScript và ô gộp chưa hỗ trợ. "
                   "DB bỏ qua dòng có tất cả giá trị giống nhau; file append giữ cả dòng lặp.")
        options["table_selector"] = st.text_input("CSS chọn bảng", value="table")
        options["columns"] = {name: st.number_input(f"Cột của {name}", min_value=1, max_value=500,
                               value=index + 1, key=f"table_column_{name}") for index, name in enumerate(fields)}
        date_field = st.selectbox("Cột ngày để lọc dữ liệu", ["Không có"] + list(fields))
        if date_field != "Không có":
            options["date_field"] = date_field
            options["date_format"] = st.text_input("Định dạng ngày trong ô", value="%Y-%m-%d",
                help="Ví dụ 16/09/2026 dùng %d/%m/%Y; 2026-09-16 dùng %Y-%m-%d.")
        options["max_rows"] = st.number_input("Giới hạn dòng mỗi trang", min_value=1, max_value=10000, value=1000)
    st.session_state.bulk_options = options
    return options


def run_controls(urls, bulk_enabled=False):
    with st.form("crawl_with_cookie", clear_on_submit=True):
        with st.expander("Nguồn cần đăng nhập: dán cookie cho lượt kéo này"):
            st.markdown("""1. Mở website nguồn, tự đăng nhập bằng trình duyệt.
2. Nhấn **F12 → Network**, tải lại trang và chọn request lấy dữ liệu cần kéo.
3. Mở **Headers → Request Headers → Cookie**; sao chép **chỉ giá trị** của Cookie.
4. Chọn đúng nguồn bên dưới và dán vào ô. Không dán mật khẩu, Authorization, Set-Cookie, cURL hoặc HAR.

[Hướng dẫn Network của Chrome](https://developer.chrome.com/docs/devtools/network/reference).
Cookie chỉ dùng cho đợt kéo này, không lưu DB, không dùng cho lịch tự động.
Chỉ dùng phiên bạn được phép truy cập, qua kết nối HTTPS khi triển khai.
""")
            origins = sorted({f"{urlsplit(url).scheme}://{urlsplit(url).netloc}" for url in urls})
            origin = st.selectbox("Nguồn được dùng cookie", origins) if origins else None
            cookie = st.text_input("Cookie cho lượt kéo", type="password")
        submitted = st.form_submit_button("🚀 Chạy crawl", type="primary")
        preview = st.form_submit_button("Xem trước đợt kéo", disabled=not bulk_enabled)
        st.caption("Xem trước bảng chỉ tải trang đầu, không lưu record. Cookie được xóa sau mỗi lần gửi; cần dán lại khi chạy thật.")
    return submitted, origin, cookie, preview


def report_panel(api_post):
    with st.expander("Báo lỗi cho admin", expanded=bool(st.session_state.get("crawl_ui_error"))):
        attempts = st.session_state.get("crawl_attempts", [])
        if not attempts:
            st.caption("Sau khi thử kéo dữ liệu, bạn có thể báo lỗi ở đây, kể cả lỗi hiển thị kết quả.")
            return
        index = st.selectbox("Lượt kéo cần báo", range(len(attempts)), index=len(attempts)-1,
                             format_func=lambda i: f"Lượt {i+1} · {attempts[i].get('request_id') or 'chưa có mã từ server'}")
        error = st.session_state.get("crawl_ui_error") or {}
        st.caption("Gửi mã lượt kéo, nguồn đã bỏ query, tên field, trạng thái và vị trí lỗi. "
                   "Không gửi cookie, nội dung trang, giá trị dữ liệu hoặc thông báo lỗi thô.")
        kind = st.selectbox("Loại vấn đề", ["Lỗi khi chạy hoặc hiển thị", "Dữ liệu không đúng"])
        if st.button("Gửi báo lỗi", key="send_crawl_report"):
            payload = {**attempts[index], "ui_step": st.session_state.step,
                       "error_type": "WrongResult" if kind == "Dữ liệu không đúng" else error.get("error_type", "Other"),
                       "frames": error.get("frames", [])}
            result = api_post("/crawl-reports", payload)
            if result and not result.get("_http_error"):
                st.success(f"Admin đã nhận báo lỗi: {result['report_id']}")
            else:
                st.error("Chưa gửi được báo lỗi. Bạn có thể thử lại.")


def retry_panel(api_post):
    candidates = [entry for entry in st.session_state.get("run_log", [])
                  if entry.get("failed") and entry.get("_retry_config") and not entry.get("retried_by")
                  and entry["_retry_config"].get("storage_mode", "db") == "db"
                  and entry["_retry_config"].get("crawl_options", {}).get("mode") == "table"
                  and not entry["_retry_config"]["crawl_options"].get("lookback_days")]
    if not candidates:
        return
    with st.form("retry_failed_bulk", clear_on_submit=True):
        st.subheader("Chạy lại riêng các lượt lỗi")
        index = st.selectbox("Đợt cần chạy lại", range(len(candidates)),
                             format_func=lambda i: f"{candidates[i]['request_id']} · {candidates[i]['failed']} lượt lỗi")
        st.caption("Giữ nguyên cấu hình và dataset. Chỉ kéo lại số thứ tự đã lỗi; dòng đã lưu được kiểm tra trùng. "
                   "Nếu cần sửa cấu hình, hãy chạy đợt mới với dataset có sẵn.")
        st.write("Nguồn:", candidates[index]["url"])
        cookie = st.text_input("Cookie mới cho nguồn này (nếu cần)", type="password")
        retry = st.form_submit_button("Chạy lại lượt lỗi")
    if retry:
        entry = candidates[index]
        body = {**entry["_retry_config"], "retry_of": entry["request_id"], "dataset_id": entry["dataset_id"]}
        parts = urlsplit(body["url"])
        st.session_state.crawl_attempts = (st.session_state.get("crawl_attempts", []) + [{
            "url": f"{parts.scheme}://{parts.hostname}{parts.path}",
            "fields": list(body["field_descriptions"]), "storage_mode": "db"}])[-50:]
        if cookie:
            body.update(cookie_header=cookie, cookie_origin=f"{parts.scheme}://{parts.netloc}")
        try:
            result = api_post("/crawl", body)
        finally:
            body.pop("cookie_header", None)
        if result and not result.get("_http_error"):
            entry["retried_by"] = result["request_id"]
            body.pop("retry_of", None)
            st.session_state.run_log.append({"url": body["url"], **result, "_retry_config": body})
            st.success(f"Đã chạy lại {result['requests']} lượt: lưu {result['saved']}, còn lỗi {result['failed']}.")
            st.dataframe(result["results"])
        else:
            st.error(result.get("detail") if result else "Chưa nhận được kết quả; kiểm tra dataset trước khi chạy lại.")
