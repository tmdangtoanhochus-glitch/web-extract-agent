"""Public crawl controls; contains no backend/storage imports."""
from datetime import date, timedelta
from urllib.parse import urlsplit, urlencode
import streamlit as st


def export_controls(dataset_id, api_download):
    with st.expander("Xuất toàn bộ dataset", expanded=False):
        st.caption("CSV lấy toàn bộ record trước lúc bắt đầu xuất, không giới hạn theo trang đang xem. "
                   "Bộ lọc bên dưới chỉ áp dụng cho file này; ngày tính theo UTC.")
        query = {}
        if st.checkbox("Lọc khoảng ngày khi xuất", key=f"export_filter_{dataset_id}"):
            basis = st.selectbox("Loại ngày", ["Ngày crawl", "Ngày dữ liệu (as_of)"], key=f"export_basis_{dataset_id}")
            first = st.date_input("Xuất từ ngày", key=f"export_start_{dataset_id}")
            last = st.date_input("Xuất đến ngày", key=f"export_end_{dataset_id}")
            query = {"date_basis": "crawled_at" if basis == "Ngày crawl" else "as_of",
                     "start": first.isoformat(), "end": last.isoformat()}
            st.caption("Hai đầu ngày đều bao gồm. Lọc theo as_of sẽ bỏ qua record chưa có ngày dữ liệu.")
            if first > last:
                st.warning("Ngày bắt đầu phải trước ngày kết thúc.")
                return
        path = f"/datasets/{dataset_id}/export.csv" + ("?" + urlencode(query) if query else "")
        if st.button("Chuẩn bị CSV toàn bộ", key=f"prepare_export_{dataset_id}"):
            st.session_state.pop("dataset_csv_download", None)
            with st.spinner("Đang xuất dữ liệu..."):
                data = api_download(path)
            if data is not None:
                st.session_state.dataset_csv_download = {"path": path, "data": data}
        cached = st.session_state.get("dataset_csv_download")
        if cached and cached["path"] == path:
            st.download_button("Tải CSV toàn bộ", data=cached["data"], file_name=f"{dataset_id}-export.csv",
                               mime="text/csv", key=f"download_export_{dataset_id}")
            st.caption("File đã chuẩn bị không tự cập nhật theo lịch crawl. Bấm chuẩn bị lại để lấy dữ liệu mới. "
                       "Nội dung giống công thức bảng tính được xuất dạng văn bản.")
        if cached and st.button("Xóa file đã chuẩn bị khỏi phiên", key=f"clear_export_{dataset_id}"):
            st.session_state.pop("dataset_csv_download", None)
            st.rerun()


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
    if options["mode"] == "fields":
        st.markdown(
            '<div style="background:#FFF3E0;border-left:3px solid #FFB81C;padding:8px 12px;'
            'border-radius:0 6px 6px 0;font-size:13px;margin:8px 0;">'
            '💡 <b>Đề xuất:</b> Nếu trang có bảng HTML (table), chọn <b>"Bảng HTML"</b> để kéo '
            'đầy đủ tất cả bảng nhanh hơn (không cần AI). AI mode có thể bỏ sót records '
            'trên trang có nhiều bảng ẩn (tabs).</div>', unsafe_allow_html=True
        )
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


_COOKIE_HOWTO = """
1. Mở website cần lấy dữ liệu và **tự đăng nhập** bằng trình duyệt của bạn (Chrome, Edge hoặc Firefox).
2. Nhấn **F12** (hoặc chuột phải → *Kiểm tra / Inspect*) rồi chọn tab **Network** (Mạng).
3. Tải lại trang (**F5**), bấm vào request **đầu tiên** trong danh sách (loại *document*, tên trùng với trang).
4. Ở khung bên phải chọn **Headers** → kéo xuống **Request Headers** → tìm dòng **Cookie**. Bấm chuột phải vào giá trị → **Copy value**
   (hoặc bôi đen và copy **phần sau chữ `Cookie:`**).
5. Chọn đúng nguồn bên dưới và **dán vào ô Cookie**.

⚠️ Chỉ dán **giá trị Cookie**. Không dán mật khẩu, `Authorization`, `Set-Cookie`, lệnh cURL hoặc file HAR.
Cookie giống như chìa khóa đăng nhập của bạn: chỉ dùng phiên bạn được phép truy cập, và khi bạn đăng xuất hoặc cookie hết hạn thì phải lấy lại.
"""


def cookie_section(urls):
    """Khối dán cookie ở Bước 1 (cho nguồn cần đăng nhập). Cookie CHỈ nằm trong bộ nhớ phiên làm việc này: không ghi DB, không ghi file,
    không dùng cho lịch tự động, tự xóa ngay sau khi bấm Chạy crawl (xem `ui/Crawl.py`) hoặc khi bấm Xóa."""
    st.markdown('<div class="mp-section-label">Trang cần đăng nhập? Dán cookie (tùy chọn)</div>', unsafe_allow_html=True)
    with st.expander("📖 Cách lấy cookie từ trình duyệt", expanded=True):
        st.markdown(_COOKIE_HOWTO)
    origins = sorted({f"{urlsplit(url).scheme}://{urlsplit(url).netloc}" for url in urls})
    if not origins:
        st.caption("Thêm ít nhất một link ở trên, rồi chọn nguồn dùng cookie tại đây.")
        return
    saved_origin = st.session_state.get("cookie_origin")
    origin = st.selectbox("Nguồn được dùng cookie", origins,
                          index=origins.index(saved_origin) if saved_origin in origins else 0)
    cookie = st.text_input("Cookie", value=st.session_state.get("cookie_value", ""), type="password", key="cookie_input",
                           placeholder="Dán giá trị Cookie vào đây (bỏ trống nếu trang không cần đăng nhập)")
    st.session_state.cookie_origin = origin
    st.session_state.cookie_value = cookie.strip()
    if st.session_state.cookie_value:
        st.success(f"Đã nhận cookie cho {origin}. Chỉ giữ trong phiên này, dùng cho lượt chạy tiếp theo rồi **tự xóa**; "
                   "không lưu vào DB, không dùng cho lịch tự động.")
        st.button("Xóa cookie đã dán", key="clear_cookie", on_click=clear_cookie)


def clear_cookie():
    st.session_state.cookie_value = ""
    st.session_state.cookie_input = ""  # xóa cả nội dung ô nhập
    st.session_state.cookie_origin = None


def run_controls(urls, bulk_enabled=False, busy=False):
    with st.form("crawl_with_cookie", clear_on_submit=True):
        origin = st.session_state.get("cookie_origin")
        cookie = st.session_state.get("cookie_value", "")
        if cookie:
            st.caption(f"🔐 Sẽ dùng cookie đã dán ở Bước 1 cho {origin}. Cookie tự xóa sau lượt chạy này.")
        else:
            st.caption("Trang cần đăng nhập? Quay lại Bước 1 để dán cookie (có hướng dẫn cách lấy).")
        with st.expander("robots.txt (mặc định: luôn tôn trọng)"):
            st.warning("Hệ thống mặc định KIỂM TRA robots.txt và bỏ qua trang bị chặn. Chỉ bật bỏ qua khi "
                       "bạn là chủ website hoặc có sự cho phép. Hành động này chỉ áp dụng cho lượt kéo này, "
                       "và được ghi log kèm lý do.")
            st.checkbox("Bỏ qua robots.txt cho lượt kéo này", key="ignore_robots")
            st.text_input("Lý do bỏ qua (bắt buộc nếu bật)", key="ignore_robots_reason")
        submitted = st.form_submit_button("🚀 Chạy crawl", type="primary", disabled=busy)
        preview = st.form_submit_button("Xem trước đợt kéo", disabled=not bulk_enabled or busy)
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
    active = st.session_state.get("active_crawl_job")
    if active and not active.get("handled"):
        return
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
