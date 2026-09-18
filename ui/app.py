"""Streamlit UI — MVP: nhập nguồn + field cần lấy → chạy crawl → xem/tải kết quả.

Theme màu tham khảo phong cách từ mockup thiết kế (không dùng Postgres/Data
Lineage/visual selector — những phần đó là roadmap sau, xem CLAUDE.md mục
"Việc CHƯA làm trong MVP"). UI chỉ là client gọi qua HTTP tới FastAPI backend
(`src/api/main.py`) — không import trực tiếp `src.*` để giữ đúng ranh giới
frontend/backend (`API_BASE_URL` trong `.env`, mặc định http://localhost:8000).
"""
from __future__ import annotations

import csv
import io
import os
from html import escape
from urllib.parse import urlsplit, urlunsplit
try:
    from ui.crawl_controls import options_controls, run_controls, report_panel, retry_panel, export_controls
    from ui.crawl_jobs import submit_background, render_background
    from ui.schedule_controls import schedule_controls
except ModuleNotFoundError as exc:
    if exc.name != "ui":
        raise
    from crawl_controls import options_controls, run_controls, report_panel, retry_panel, export_controls
    from crawl_jobs import submit_background, render_background
    from schedule_controls import schedule_controls
try:
    from ui.feedback import feedback_panel
except ModuleNotFoundError as exc:
    if exc.name != "ui":
        raise
    from feedback import feedback_panel
from typing import Any, Optional

import httpx
import streamlit as st

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

st.set_page_config(page_title="Web Data Puller", page_icon="🧡", layout="wide")

_CSS = """
<style>
:root {
  --msb-orange:#FF671F; --msb-red:#ED1C24; --msb-sun:#FFB81C;
  --msb-border:#F0E2DA; --msb-green:#1BA672; --msb-blue:#2E6FE7;
}
.stApp { background:#FBF6F3; }
.mp-hero {
  background:linear-gradient(120deg,var(--msb-red) 0%, var(--msb-orange) 60%, var(--msb-sun) 100%);
  color:#fff; padding:20px 26px; border-radius:16px; margin-bottom:18px;
}
.mp-hero h1 { margin:0 0 4px 0; font-size:22px; }
.mp-hero p { margin:0; opacity:.92; font-size:13.5px; }
.mp-pill {
  display:inline-flex; align-items:center; gap:6px; background:#FFF1E8; color:var(--msb-red);
  padding:5px 12px; border-radius:20px; font-size:12.5px; font-weight:600; margin:3px 4px 3px 0;
}
.mp-card {
  background:#fff; border:1px solid var(--msb-border); border-radius:14px;
  padding:18px 20px; margin-bottom:14px;
}
.mp-section-label {
  font-size:14px; font-weight:600; color:#333; margin:12px 0 6px 0;
  padding-bottom:4px; border-bottom:2px solid var(--msb-border);
}
.mp-hint {
  background:#F0F7FF; border-left:3px solid var(--msb-blue); padding:8px 12px;
  border-radius:0 6px 6px 0; font-size:13px; color:#444; margin:8px 0;
}
div.stButton > button[kind="primary"] {
  background:linear-gradient(135deg,var(--msb-red),var(--msb-orange)); border:none;
}
div.stButton > button[kind="secondary"]:hover {
  border-color:var(--msb-orange); color:var(--msb-orange);
}
.mp-status-saved { color:var(--msb-green); font-weight:700; }
.mp-status-unchanged { color:#8a8380; font-weight:700; }
.mp-status-warn { color:var(--msb-sun); font-weight:700; }
.mp-status-error { color:var(--msb-red); font-weight:700; }
.mp-step-active {
  background:linear-gradient(135deg,var(--msb-red),var(--msb-orange)) !important;
  color:#fff !important;
}
</style>
"""
st.markdown(_CSS, unsafe_allow_html=True)


_WRITE_MODE_LABELS = {
    "Ghi thêm": "append",
    "Luôn tạo file mới": "new_file",
    "Ghi đè theo trường": "overwrite_row",
}

_FILE_FORMATS = {
    "Excel (.xlsx)": "xlsx",
    "CSV (.csv)": "csv",
    "JSON (.json)": "json",
    "Parquet (.parquet)": "parquet",
}


def _init_state() -> None:
    defaults: dict[str, Any] = {
        "step": 1,
        "storage_mode": "Lưu vào DB",  # "Lưu vào DB" | "Lưu ra file"
        "dataset_mode": "Tạo dataset mới",
        "dataset_name": "",
        "selected_dataset_id": None,
        "urls": [],
        "fields": [{"name": "", "desc": "", "is_image": False}],
        "file_name": "",
        "file_format": "Excel (.xlsx)",
        "file_path": "",
        "write_mode_label": "Ghi thêm",
        "key_field": None,
        "run_dataset_id": None,
        "run_file_paths": [],
        "run_log": [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


_init_state()


def _client() -> httpx.Client:
    return httpx.Client(base_url=API_BASE_URL, timeout=900.0)


def _api_get(path: str) -> Optional[Any]:
    try:
        with _client() as client:
            resp = client.get(path)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as exc:
        st.error(f"Không gọi được API ({API_BASE_URL}{path}): {exc}")
        return None


def _api_post(path: str, json_body: dict) -> Optional[dict]:
    try:
        with _client() as client:
            resp = client.post(path, json=json_body)
            request_id = resp.headers.get("X-Crawl-Request-ID")
            if path in {"/crawl", "/crawl/preview"} and st.session_state.get("crawl_attempts"):
                st.session_state.crawl_attempts[-1]["request_id"] = request_id
            try:
                result = resp.json()
            except ValueError:
                result = {"detail": "API returned an unreadable response"}
            if resp.status_code >= 400:
                return {"_http_error": resp.status_code, "detail": result.get("detail"), "request_id": request_id}
            return result
    except httpx.HTTPError:
        st.error("Không kết nối được API. Bạn có thể báo lượt kéo này bên dưới; nếu đã gửi request, hãy kiểm tra dữ liệu trước khi chạy lại.")
        return None



def _api_delete(path: str) -> bool:
    try:
        with _client() as client:
            resp = client.delete(path)
            if resp.status_code >= 400:
                detail = resp.json().get("detail", resp.text)
                st.error(f"Không xoá được ({API_BASE_URL}{path}): {detail}")
                return False
            return True
    except httpx.HTTPError as exc:
        st.error(f"Không gọi được API ({API_BASE_URL}{path}): {exc}")
        return False


def _api_patch(path, body):
    try:
        with _client() as client:
            response = client.patch(path, json=body)
            if response.status_code >= 400:
                return {"_http_error": response.status_code, "detail": "Không cập nhật được lịch; kiểm tra cấu hình"}
            return response.json()
    except (httpx.HTTPError, ValueError):
        st.error("Không kết nối được API để cập nhật lịch")
        return None


def _api_download(path: str) -> Optional[bytes]:
    try:
        with _client() as client:
            resp = client.get(path)
            resp.raise_for_status()
            return resp.content
    except httpx.HTTPError as exc:
        st.error(f"Không tải được file ({API_BASE_URL}{path}): {exc}")
        return None


def _list_datasets() -> list[dict]:
    return _api_get("/datasets") or []


st.markdown(
    """
    <div class="mp-hero">
      <h1>🧡 Web Data Puller</h1>
      <p>Nhập link website + mô tả field cần lấy bằng ngôn ngữ tự nhiên — hệ thống tự crawl,
      AI trích xuất, lưu vào database. Không cần viết code.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

STEP_LABELS = [
    "1. Nguồn dữ liệu",
    "2. Trường dữ liệu",
    "3. Chạy & Kết quả",
    "4. Dữ liệu đã lưu",
    "5. Lịch tự động",
]
cols = st.columns(len(STEP_LABELS))
_clicked_step: Optional[int] = None
for i, col in enumerate(cols, start=1):
    with col:
        if st.button(
            STEP_LABELS[i - 1],
            key=f"step_btn_{i}",
            type="primary" if st.session_state.step == i else "secondary",
            use_container_width=True,
        ):
            _clicked_step = i
if _clicked_step is not None:
    st.session_state.step = _clicked_step
    st.rerun()

st.divider()


# ---------------------------------------------------------------- Step 1 ----
def _render_step1() -> None:
    st.markdown('<div class="mp-card">', unsafe_allow_html=True)
    st.subheader("Bước 1 · Khai báo nguồn dữ liệu")

    st.session_state.storage_mode = st.radio(
        "Nơi lưu kết quả",
        ["Lưu vào DB", "Lưu ra file"],
        horizontal=True,
        index=0 if st.session_state.storage_mode == "Lưu vào DB" else 1,
    )
    is_file_mode = st.session_state.storage_mode == "Lưu ra file"

    if is_file_mode:
        st.caption(
            "Luồng lưu file KHÔNG tạo dataset, KHÔNG kiểm tra trùng lặp — cấu hình tên file/cách "
            "ghi sẽ hỏi ở Bước 2 sau khi khai báo field."
        )
        st.session_state.selected_dataset_id = None
    else:
        st.session_state.dataset_mode = st.radio(
            "Dataset",
            ["Tạo dataset mới", "Dùng dataset có sẵn"],
            horizontal=True,
            index=0 if st.session_state.dataset_mode == "Tạo dataset mới" else 1,
        )

        if st.session_state.dataset_mode == "Tạo dataset mới":
            st.session_state.dataset_name = st.text_input(
                "Tên dataset", value=st.session_state.dataset_name,
                placeholder="VD: Giá vàng SJC hàng ngày",
            )
            st.session_state.selected_dataset_id = None
        else:
            datasets = _list_datasets()
            if not datasets:
                st.info("Chưa có dataset nào — tạo mới ở lựa chọn bên trên.")
            else:
                options = {f"{d['dataset_name']} ({d['dataset_id'][:8]})": d for d in datasets}
                label = st.selectbox("Chọn dataset", list(options.keys()))
                chosen = options[label]
                st.session_state.selected_dataset_id = chosen["dataset_id"]
                st.caption("Schema hiện có: " + ", ".join(chosen["schema_signature"]))

    st.markdown('<div class="mp-section-label">Đường link website (URL)</div>', unsafe_allow_html=True)
    new_url = st.text_input("URL cần cào", key="new_url_input", placeholder="https://example.com/gia-vang")
    if st.button("+ Thêm link") and new_url.strip():
        if new_url.strip() not in st.session_state.urls:
            st.session_state.urls.append(new_url.strip())

    with st.expander("Phân trang — cào nhiều page liên tiếp", expanded=False):
        st.caption("Dùng `{page}` làm số trang trong URL. VD: `https://books.toscrape.com/catalogue/page-{page}.html`")
        st.markdown(
            '<div style="background:#F0F7FF;border-left:3px solid #2E6FE7;padding:6px 10px;'
            'border-radius:0 6px 6px 0;font-size:12px;margin:4px 0 8px 0;">'
            '💡 Cần khoảng ngày hoặc kéo theo batch? Bật <b>"Kéo nhiều lượt / kéo bảng"</b> '
            'ở Bước 3 để dùng date range, table mode, progress và pause.</div>',
            unsafe_allow_html=True
        )
        col_p1, col_p2, col_p3 = st.columns([6, 2, 2])
        with col_p1:
            page_url_pattern = st.text_input("URL pattern", key="page_url_pattern",
                placeholder="https://example.com/page-{page}.html")
        with col_p2:
            page_start = st.number_input("Từ page", min_value=1, value=1, key="page_start")
        with col_p3:
            page_end = st.number_input("Đến page", min_value=1, value=10, key="page_end")
        if st.button("+ Sinh URL theo page", key="gen_page_urls") and page_url_pattern.strip():
            generated = [page_url_pattern.replace("{page}", str(p))
                         for p in range(int(page_start), int(page_end) + 1)]
            added = 0
            for g in generated:
                if g not in st.session_state.urls:
                    st.session_state.urls.append(g)
                    added += 1
            if added:
                st.success(f"Đã thêm {added} URL (page {int(page_start)}–{int(page_end)}).")
                st.rerun()

    for url in list(st.session_state.urls):
        c1, c2 = st.columns([10, 1])
        c1.markdown(f'<span class="mp-pill">🔗 {url}</span>', unsafe_allow_html=True)
        if c2.button("✕", key=f"rm_{url}"):
            st.session_state.urls.remove(url)
            st.rerun()

    if st.button("Tiếp tục → Trường dữ liệu", type="primary"):
        if not is_file_mode and st.session_state.dataset_mode == "Tạo dataset mới" and not st.session_state.dataset_name.strip():
            st.warning("Cần nhập tên dataset.")
        elif not is_file_mode and st.session_state.dataset_mode == "Dùng dataset có sẵn" and not st.session_state.selected_dataset_id:
            st.warning("Cần chọn 1 dataset có sẵn.")
        elif not st.session_state.urls:
            st.warning("Cần thêm ít nhất 1 URL.")
        else:
            st.session_state.step = 2
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------- Step 2 ----
def _render_step2() -> None:
    st.markdown('<div class="mp-card">', unsafe_allow_html=True)
    st.subheader("Bước 2 · Mô tả trường dữ liệu cần lấy")
    st.caption(
        "Mô tả bằng ngôn ngữ tự nhiên — AI sẽ đọc nội dung trang đã làm sạch và trích xuất "
        "theo mô tả này (KHÔNG tự bịa giá trị không có trong trang)."
    )

    is_file_mode = st.session_state.storage_mode == "Lưu ra file"
    using_existing = (
        not is_file_mode
        and st.session_state.dataset_mode == "Dùng dataset có sẵn"
        and st.session_state.selected_dataset_id
    )
    if using_existing:
        dataset = next(
            (d for d in _list_datasets() if d["dataset_id"] == st.session_state.selected_dataset_id), None
        )
        if dataset:
            st.info("Dataset có sẵn yêu cầu đúng tên field theo schema hiện có — chỉ sửa được mô tả.")
            fixed_names = dataset["schema_signature"]
            if [f["name"] for f in st.session_state.fields] != fixed_names:
                st.session_state.fields = [{"name": name, "desc": "", "is_image": False} for name in fixed_names]

    for idx, row in enumerate(st.session_state.fields):
        row.setdefault("is_image", False)
        c1, c2, c3, c4 = st.columns([3, 5, 1, 1])
        row["name"] = c1.text_input(
            "Tên field", value=row["name"], key=f"fname_{idx}", disabled=bool(using_existing),
            placeholder="gia_ban",
        )
        row["desc"] = c2.text_input(
            "Mô tả tự nhiên", value=row["desc"], key=f"fdesc_{idx}", placeholder="Giá bán ra niêm yết trên trang",
        )
        row["is_image"] = c3.checkbox(
            "Ảnh", value=row["is_image"], key=f"fimg_{idx}",
            help="Field này là URL ảnh — tải file về data/images/ thay vì chỉ lưu URL.",
        )
        if not using_existing and c4.button("🗑", key=f"rmf_{idx}") and len(st.session_state.fields) > 1:
            st.session_state.fields.pop(idx)
            st.rerun()

    if not using_existing and st.button("＋ Thêm field"):
        st.session_state.fields.append({"name": "", "desc": "", "is_image": False})
        st.rerun()

    if is_file_mode:
        st.markdown("**Cấu hình lưu file**")
        fc1, fc2 = st.columns([3, 2])
        with fc1:
            st.session_state.file_name = st.text_input(
                "Tên file *",
                value=st.session_state.file_name,
                key="file_name_input",
                placeholder="VD: gia-vang",
            )
        with fc2:
            st.session_state.file_format = st.selectbox(
                "Định dạng",
                list(_FILE_FORMATS.keys()),
                key="file_format_select",
                index=list(_FILE_FORMATS.keys()).index(st.session_state.file_format),
            )
        fmt_ext = _FILE_FORMATS[st.session_state.file_format]
        st.session_state.file_path = f"{st.session_state.file_name.strip()}.{fmt_ext}"

        if st.session_state.file_name.strip():
            st.markdown(
                f'<div class="mp-hint">📂 Kết quả sẽ có nút tải về trình duyệt: <code>{st.session_state.file_path}</code></div>',
                unsafe_allow_html=True,
            )
        st.session_state.write_mode_label = st.selectbox(
            "Cách ghi", list(_WRITE_MODE_LABELS.keys()), key="write_mode_select",
            index=list(_WRITE_MODE_LABELS.keys()).index(st.session_state.write_mode_label),
        )
        if _WRITE_MODE_LABELS[st.session_state.write_mode_label] == "overwrite_row":
            field_names = [f["name"].strip() for f in st.session_state.fields if f["name"].strip()]
            if field_names:
                current = st.session_state.key_field if st.session_state.key_field in field_names else field_names[0]
                st.session_state.key_field = st.selectbox(
                    "Trường dùng làm khoá để ghi đè", field_names,
                    index=field_names.index(current), key="key_field_select",
                )
            else:
                st.info("Khai báo ít nhất 1 field ở trên để chọn trường khoá.")
        else:
            st.session_state.key_field = None

    b1, b2 = st.columns([1, 1])
    if b1.button("← Quay lại"):
        st.session_state.step = 1
        st.rerun()
    if b2.button("Tiếp tục → Chạy & Kết quả", type="primary"):
        cleaned = [f for f in st.session_state.fields if f["name"].strip() and f["desc"].strip()]
        if not cleaned:
            st.warning("Cần ít nhất 1 field có đủ tên và mô tả.")
        elif is_file_mode and not st.session_state.file_name.strip():
            st.warning("Cần nhập tên file.")
        elif (
            is_file_mode
            and _WRITE_MODE_LABELS[st.session_state.write_mode_label] == "overwrite_row"
            and not st.session_state.key_field
        ):
            st.warning("Cần chọn trường khoá cho cách ghi 'Ghi đè theo trường'.")
        else:
            st.session_state.fields = cleaned
            st.session_state.step = 3
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------- Step 3 ----
_STATUS_CSS_CLASS = {
    "completed": "mp-status-saved",
    "partial": "mp-status-warn",
    "saved": "mp-status-saved",
    "unchanged": "mp-status-unchanged",
    "schema_mismatch": "mp-status-warn",
    "dataset_not_found": "mp-status-warn",
    "fetch_failed": "mp-status-error",
    "extract_failed": "mp-status-error",
}


def _render_step3() -> None:
    st.markdown('<div class="mp-card">', unsafe_allow_html=True)
    st.subheader("Bước 3 · Chạy crawl & xem kết quả")

    is_file_mode = st.session_state.storage_mode == "Lưu ra file"
    field_descriptions = {f["name"]: f["desc"] for f in st.session_state.fields}
    image_fields = [f["name"] for f in st.session_state.fields if f.get("is_image")]
    if is_file_mode:
        st.markdown(f"**Lưu ra file:** {st.session_state.file_path}")
        st.markdown(f"**Cách ghi:** {st.session_state.write_mode_label}")
    else:
        st.markdown(f"**Dataset:** {st.session_state.dataset_name or '(dùng dataset có sẵn)'}")
    st.markdown("**URL:** " + ", ".join(st.session_state.urls))
    st.markdown("**Field:** " + ", ".join(field_descriptions.keys()))

    crawl_options = options_controls(field_descriptions)
    active_job = st.session_state.get("active_crawl_job")
    busy = bool(active_job and not active_job.get("handled"))
    submitted, cookie_origin, request_cookie, preview = run_controls(st.session_state.urls, bool(crawl_options), busy)
    if submitted or preview:
        st.session_state.crawl_ui_error = None
        st.session_state.crawl_previews = []
        if submitted:
            st.session_state.run_log = []
            st.session_state.run_file_paths = []
        dataset_id = st.session_state.selected_dataset_id
        pending_bodies = []
        total_urls = len(st.session_state.urls)
        status_box = st.empty()
        progress_bar = st.progress(0.0)
        for i, url in enumerate(st.session_state.urls):
            status_box.markdown(
                f'<div style="padding:8px 16px;background:#FFF1E8;border-radius:8px;'
                f'border-left:4px solid #FF671F;margin-bottom:4px;">'
                f'🔄 <b>Đang crawl</b> — URL {i+1}/{total_urls}'
                f'<br><span style="color:#666;font-size:13px;">{escape(url)}</span>'
                f'</div>', unsafe_allow_html=True
            )
            body: dict[str, Any] = {
                "url": url, "field_descriptions": field_descriptions, "image_fields": image_fields,
            }
            if is_file_mode:
                body["storage_mode"] = "file"
                body["file_path"] = st.session_state.file_path.strip()
                body["write_mode"] = _WRITE_MODE_LABELS[st.session_state.write_mode_label]
                if body["write_mode"] == "overwrite_row":
                    body["key_field"] = st.session_state.key_field
            elif dataset_id:
                body["dataset_id"] = dataset_id
            else:
                body["dataset_name"] = st.session_state.dataset_name
            if crawl_options:
                body["crawl_options"] = crawl_options
            if st.session_state.get("ignore_robots"):
                body["ignore_robots"] = True
                body["ignore_robots_reason"] = st.session_state.get("ignore_robots_reason", "")
            parts = urlsplit(url)
            attempt = {"url": urlunsplit((parts.scheme, parts.hostname or "", parts.path, "", "")),
                       "fields": list(field_descriptions), "storage_mode": "file" if is_file_mode else "db"}
            st.session_state.crawl_attempts = (st.session_state.get("crawl_attempts", []) + [attempt])[-50:]
            if request_cookie and f"{parts.scheme}://{parts.netloc}" == cookie_origin:
                body.update(cookie_header=request_cookie, cookie_origin=cookie_origin)
            if submitted and crawl_options:
                pending_bodies.append(dict(body))
                body.pop("cookie_header", None)
                continue
            try:
                result = _api_post("/crawl/preview" if preview else "/crawl", body)
            finally:
                body.pop("cookie_header", None)
            if preview:
                if result:
                    st.session_state.crawl_previews.append({"url": url, **result})
                continue
            if result and not result.get("_http_error"):
                st.session_state.last_crawl_config = {**body, "dataset_id": result.get("dataset_id")}

            if result is None:
                continue
            if result.get("_http_error"):
                st.session_state.run_log.append({"url": url, "status": "error", "detail": result["detail"]})
                continue
            if not is_file_mode and not dataset_id and result.get("dataset_id"):
                dataset_id = result["dataset_id"]
            if is_file_mode and result.get("file_path"):
                if result["file_path"] not in st.session_state.run_file_paths:
                    st.session_state.run_file_paths.append(result["file_path"])
            st.session_state.run_log.append({"url": url, **result, "_retry_config": dict(body)})
            progress_bar.progress((i + 1) / total_urls)
        _errors = sum(1 for e in st.session_state.run_log if e.get("status") in ("error", "fetch_failed", "extract_failed"))
        if _errors == 0:
            status_box.markdown(
                f'<div style="padding:8px 16px;background:#E8F5E9;border-radius:8px;'
                f'border-left:4px solid #1BA672;margin-bottom:4px;">'
                f'✅ <b>Hoàn thành</b> — {total_urls} URL đã xử lý'
                f'</div>', unsafe_allow_html=True
            )
        else:
            status_box.markdown(
                f'<div style="padding:8px 16px;background:#FFF3E0;border-radius:8px;'
                f'border-left:4px solid #FFB81C;margin-bottom:4px;">'
                f'⚠ <b>Hoàn thành với {_errors} lỗi</b> — {total_urls} URL đã xử lý'
                f'</div>', unsafe_allow_html=True
            )
        if submitted:
            st.session_state.run_dataset_id = dataset_id
            if pending_bodies:
                submit_background(_api_post, pending_bodies)

    for item in st.session_state.get("crawl_previews", []):
        with st.expander(f"Xem trước — {item['url']}", expanded=True):
            st.caption("Kết quả lần xem trước gần nhất. Nếu đổi cấu hình, hãy xem trước lại; các trang còn lại chưa được kiểm tra.")
            if item.get("_http_error"):
                st.error(item.get("detail"))
            else:
                st.write(f"Kế hoạch {item['requests']} lượt; đã tải {item['fetched_pages']} trang để xem trước.")
                st.dataframe(item["plan"])
                if item.get("sample"):
                    st.dataframe(item["sample"])
                    st.caption(f"Hiển thị tối đa 10 dòng mẫu trong {item['matched_rows']} dòng khớp của trang đầu. Chưa lưu vào dataset/file.")
                elif item.get("fetched_pages"):
                    st.info("Trang đầu không có dòng khớp khoảng ngày; kiểm tra cột ngày và bộ lọc nguồn.")

    if st.session_state.run_log:
        st.markdown("**Console log**")
        for entry in st.session_state.run_log:
            status = entry.get("status", "error")
            css_class = _STATUS_CSS_CLASS.get(status, "mp-status-error")
            detail = entry.get("detail") or ""
            confidence = entry.get("confidence")
            conf_text = f" · confidence={confidence:.2f}" if isinstance(confidence, (int, float)) else ""
            review_text = (
                ' · <span class="mp-status-warn">⚠ cần xem lại</span>' if entry.get("needs_review") else ""
            )
            st.markdown(
                f'<span class="{css_class}">● {status}</span> — {escape(str(entry["url"]))}{conf_text}{review_text} {escape(str(detail))}',
                unsafe_allow_html=True,
            )
            if "requests" in entry:
                st.write({key: entry.get(key) for key in ("requests", "saved", "skipped", "failed")})
                st.dataframe(entry.get("results", []))
            if entry.get("data") or entry.get("file_path") or entry.get("dataset_id"):
                with st.expander(f"Preview dữ liệu — {entry['url']}", expanded=True):
                    _PREVIEW_MAX = 15
                    _shown = False
                    if entry.get("file_path"):
                        content = _api_download(f"/exports/{entry['file_path']}")
                        if content:
                            try:
                                import pandas as _pd
                                import io as _io
                                ext = entry["file_path"].lower().rsplit(".", 1)[-1]
                                if ext == "json":
                                    import json as _json
                                    records = _json.loads(content.decode("utf-8"))
                                    if isinstance(records, list) and records:
                                        df = _pd.DataFrame(records)
                                        st.dataframe(df.head(_PREVIEW_MAX), use_container_width=True)
                                        if len(df) > _PREVIEW_MAX:
                                            st.caption(f"Hiển thị {_PREVIEW_MAX}/{len(df)} dòng — tải file để xem đầy đủ")
                                        _shown = True
                                elif ext == "csv":
                                    df = _pd.read_csv(_io.BytesIO(content), encoding="utf-8-sig")
                                    st.dataframe(df.head(_PREVIEW_MAX), use_container_width=True)
                                    if len(df) > _PREVIEW_MAX:
                                        st.caption(f"Hiển thị {_PREVIEW_MAX}/{len(df)} dòng — tải file để xem đầy đủ")
                                    _shown = True
                                elif ext == "xlsx":
                                    df = _pd.read_excel(_io.BytesIO(content), engine="openpyxl")
                                    st.dataframe(df.head(_PREVIEW_MAX), use_container_width=True)
                                    if len(df) > _PREVIEW_MAX:
                                        st.caption(f"Hiển thị {_PREVIEW_MAX}/{len(df)} dòng — tải file để xem đầy đủ")
                                    _shown = True
                                elif ext == "parquet":
                                    df = _pd.read_parquet(_io.BytesIO(content), engine="pyarrow")
                                    st.dataframe(df.head(_PREVIEW_MAX), use_container_width=True)
                                    if len(df) > _PREVIEW_MAX:
                                        st.caption(f"Hiển thị {_PREVIEW_MAX}/{len(df)} dòng — tải file để xem đầy đủ")
                                    _shown = True
                            except Exception:
                                pass
                    if not _shown and entry.get("dataset_id"):
                        ds_records = _api_get(f"/datasets/{entry['dataset_id']}/records?limit={_PREVIEW_MAX}") or []
                        if ds_records:
                            import pandas as _pd
                            rows = [{"source_url": r.get("source_url"), "confidence": r.get("confidence"),
                                     **r.get("data", {})} for r in ds_records]
                            st.dataframe(_pd.DataFrame(rows), use_container_width=True)
                            _shown = True
                    if not _shown and entry.get("data"):
                        import pandas as _pd
                        st.dataframe(_pd.DataFrame([entry["data"]]), use_container_width=True)

    if st.session_state.run_file_paths:
        st.markdown("**File kết quả**")
        for file_path in st.session_state.run_file_paths:
            ext = file_path.lower().rsplit(".", 1)[-1] if "." in file_path else "json"
            mime_map = {"json": "application/json", "csv": "text/csv",
                        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        "parquet": "application/octet-stream"}
            mime = mime_map.get(ext, "application/octet-stream")
            st.markdown(f"`{file_path}`")
            content = _api_download(f"/exports/{file_path}")
            if content is not None:
                _file_name = file_path.split("/")[-1]
                st.download_button(
                    f"⬇ Tải {_file_name}", data=content, file_name=_file_name,
                    mime=mime, key=f"dl_{file_path}",
                )

    retry_panel(_api_post)

    b1, b2 = st.columns([1, 1])
    if b1.button("← Quay lại"):
        st.session_state.step = 2
        st.rerun()
    if not is_file_mode and st.session_state.run_dataset_id and b2.button("Xem dữ liệu đã lưu →", type="primary"):
        st.session_state.selected_dataset_id = st.session_state.run_dataset_id
        st.session_state.step = 4
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------- Step 4 ----
def _records_to_csv(records: list[dict]) -> str:
    def text_cell(value):
        if isinstance(value, str) and value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
            return "'" + value
        return value

    data_keys: list[str] = []
    for record in records:
        for key in record.get("data", {}):
            if key not in data_keys:
                data_keys.append(key)

    fieldnames = ["record_id", "source_url", "confidence", "crawled_at"] + data_keys
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writerow({name: text_cell(name) for name in fieldnames})
    for record in records:
        row = {
            "record_id": record["record_id"],
            "source_url": record["source_url"],
            "confidence": record.get("confidence"),
            "crawled_at": record["crawled_at"],
            **record.get("data", {}),
        }
        writer.writerow({name: text_cell(value) for name, value in row.items()})
    # UTF-8 BOM để Excel mở đúng tiếng Việt không bị lỗi font (docs/kien_audit/03).
    return "﻿" + buffer.getvalue()


def _records_to_xlsx(records: list[dict]) -> bytes:
    data_keys: list[str] = []
    for record in records:
        for key in record.get("data", {}):
            if key not in data_keys:
                data_keys.append(key)

    rows = []
    for record in records:
        rows.append({
            "record_id": record["record_id"],
            "source_url": record["source_url"],
            "confidence": record.get("confidence"),
            "crawled_at": record["crawled_at"],
            **record.get("data", {}),
        })

    import pandas as pd
    df = pd.DataFrame(rows, columns=["record_id", "source_url", "confidence", "crawled_at"] + data_keys)
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False, engine="openpyxl")
    return buffer.getvalue()


def _render_step4() -> None:
    st.markdown('<div class="mp-card">', unsafe_allow_html=True)
    st.subheader("Bước 4 · Dữ liệu đã lưu")

    datasets = _list_datasets()
    if not datasets:
        st.info("Chưa có dataset nào.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    options = {f"{d['dataset_name']} ({d['dataset_id'][:8]})": d["dataset_id"] for d in datasets}
    default_id = st.session_state.selected_dataset_id
    labels = list(options.keys())
    default_index = 0
    for i, (label, dsid) in enumerate(options.items()):
        if dsid == default_id:
            default_index = i
    label = st.selectbox("Dataset", labels, index=default_index)
    dataset_id = options[label]

    export_controls(dataset_id, _api_download)

    page_size = st.selectbox("Số record mỗi trang", [100, 500, 1000])
    page = st.number_input("Trang dữ liệu", min_value=1, value=1, key=f"records_page_{dataset_id}")
    records = _api_get(f"/datasets/{dataset_id}/records?limit={page_size}&offset={(page - 1) * page_size}") or []
    st.caption("Bảng và CSV bên dưới chỉ gồm trang đang chọn. Tăng số record hoặc chuyển trang để xem tiếp.")
    if not records:
        st.info("Trang này chưa có record. Chọn trang trước hoặc chạy crawl để bổ sung dữ liệu.")
    else:
        needs_review_count = sum(1 for r in records if r.get("needs_review"))
        if needs_review_count:
            st.warning(
                f"⚠ Có {needs_review_count}/{len(records)} record confidence thấp hơn ngưỡng "
                "(AI_CONFIDENCE_THRESHOLD) — nên xem lại cột 'needs_review' bên dưới."
            )
        table_rows = [
            {
                "source_url": r["source_url"],
                "confidence": r.get("confidence"),
                "needs_review": r.get("needs_review", False),
                "crawled_at": r["crawled_at"],
                **r.get("data", {}),
            }
            for r in records
        ]
        st.dataframe(table_rows, use_container_width=True)
        st.markdown('<div class="mp-section-label">Tải dữ liệu</div>', unsafe_allow_html=True)
        dl1, dl2 = st.columns(2)
        with dl1:
            st.download_button(
                "⬇ Tải CSV",
                data=_records_to_csv(records),
                file_name=f"{dataset_id}.csv",
                mime="text/csv",
            )
        with dl2:
            st.download_button(
                "⬇ Tải XLSX",
                data=_records_to_xlsx(records),
                file_name=f"{dataset_id}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        with st.expander("Evidence (đoạn gốc AI trích xuất)"):
            for r in records:
                if r.get("evidence"):
                    st.markdown(f"**{r['source_url']}**")
                    st.json(r["evidence"])

    b1, b2 = st.columns([1, 1])
    if b1.button("← Quay lại Bước 3"):
        st.session_state.step = 3
        st.rerun()
    if b2.button("Đặt lịch tự động →", type="primary"):
        st.session_state.step = 5
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------- Step 5 ----
def _format_trigger(trigger_type: str, trigger_args: dict) -> str:
    if trigger_type == "interval":
        for unit, label in (("hours", "giờ"), ("minutes", "phút"), ("seconds", "giây")):
            if unit in trigger_args:
                return f"Mỗi {trigger_args[unit]} {label}"
        return f"interval({trigger_args})"
    if trigger_type == "cron":
        hour = trigger_args.get("hour")
        if hour is not None:
            minute = trigger_args.get("minute", 0)
            return f"Hàng ngày lúc {int(hour):02d}:{int(minute):02d}"
        return f"cron({trigger_args})"
    return f"{trigger_type}({trigger_args})"


def _render_step5() -> None:
    st.markdown('<div class="mp-card">', unsafe_allow_html=True)
    st.subheader("Bước 5 · Lịch tự động")
    st.caption(
        "Cấu hình crawl lặp lại theo lịch — chạy nền ở backend (APScheduler), "
        "tiếp tục chạy đúng lịch kể cả khi đóng UI này."
    )

    previous = st.session_state.get("last_crawl_config")
    if previous and previous.get("crawl_options"):
        with st.expander("Đặt lịch append từ đợt vừa kéo", expanded=True):
            st.caption("Dùng lại nguồn, ánh xạ cột và dataset của đợt vừa kéo. Khoảng ngày gần nhất tính theo UTC. "
                       "Lịch không giữ cookie của lượt kéo thủ công. Nếu nguồn bắt buộc đăng nhập, lịch này chưa hỗ trợ.")
            st.write({key: previous.get(key) for key in ("url", "dataset_id", "file_path")})
            lookback = st.number_input("Số ngày gần nhất mỗi lần chạy lịch", min_value=1, max_value=366, value=7)
            every = st.number_input("Chạy mỗi bao nhiêu giờ", min_value=1, max_value=720, value=24)
            if st.button("Tạo lịch append theo cấu hình này"):
                options = dict(previous["crawl_options"])
                had_dates = bool(options.pop("start_date", None))
                options.pop("end_date", None)
                if had_dates:
                    options["lookback_days"] = lookback
                body = {key: value for key, value in previous.items()
                        if key not in {"cookie_header", "cookie_origin", "dataset_name"}}
                body.update(crawl_options=options, trigger_type="interval", trigger_args={"hours": every})
                if body.get("storage_mode") == "file":
                    body["write_mode"] = "append"
                result = _api_post("/schedules", body)
                if result and not result.get("_http_error"):
                    st.success("Đã tạo lịch append")
                else:
                    st.error("Chưa tạo được lịch; kiểm tra lại cấu hình đợt vừa kéo")

    datasets = _list_datasets()
    dataset_by_id = {d["dataset_id"]: d for d in datasets}

    st.markdown("**Lịch đã tạo**")
    schedules = _api_get("/schedules") or []
    if not schedules:
        st.info("Chưa có lịch tự động nào.")
    else:
        for job in schedules:
            if job.get("storage_mode") == "file":
                target_label = f"📄 file: {job.get('file_path')}"
            else:
                dataset = dataset_by_id.get(job["dataset_id"])
                target_label = dataset["dataset_name"] if dataset else str(job["dataset_id"])[:8]
            trigger_text = _format_trigger(job["trigger_type"], job["trigger_args"])
            last_status = job.get("last_status") or "chưa chạy lần nào"
            last_run = job.get("last_run_at") or "—"

            c1, c2 = st.columns([10, 1])
            c1.markdown(
                f"**{target_label}** — {job['url']}  \n"
                f"⏱ {trigger_text} · lần chạy gần nhất: {last_run} · trạng thái: {last_status}"
            )
            if c2.button("🗑", key=f"del_job_{job['job_id']}"):
                if _api_delete(f"/schedules/{job['job_id']}"):
                    st.rerun()
            schedule_controls(job, _api_patch)
            st.divider()

    st.markdown("**Tạo lịch mới**")
    schedule_storage_mode = st.radio(
        "Nơi lưu kết quả của lịch", ["Lưu vào DB", "Lưu ra file"], horizontal=True, key="schedule_storage_mode",
    )
    is_schedule_file_mode = schedule_storage_mode == "Lưu ra file"

    chosen_dataset = None
    if not is_schedule_file_mode:
        if not datasets:
            st.info("Cần có ít nhất 1 dataset (chạy crawl thủ công ở Bước 1-3 trước) mới tạo được lịch lưu DB.")
        else:
            options = {f"{d['dataset_name']} ({d['dataset_id'][:8]})": d for d in datasets}
            label = st.selectbox("Dataset", list(options.keys()), key="schedule_dataset_select")
            chosen_dataset = options[label]

    url = st.text_input(
        "URL cần cào theo lịch", key="schedule_url_input", placeholder="https://example.com/gia-vang"
    )
    if chosen_dataset is not None:
        known_records = _api_get(f"/datasets/{chosen_dataset['dataset_id']}/records") or []
        known_urls = sorted({r["source_url"] for r in known_records})
        if known_urls:
            st.caption("URL đã từng cào cho dataset này: " + ", ".join(known_urls))

    st.markdown("**Mô tả field**")
    field_descriptions: dict[str, str] = {}
    schedule_image_fields: list[str] = []
    if is_schedule_file_mode:
        # Luồng file không có dataset -> tự khai báo field tự do (giống Bước 2 khi tạo dataset mới).
        if "schedule_fields" not in st.session_state:
            st.session_state.schedule_fields = [{"name": "", "desc": "", "is_image": False}]
        for idx, row in enumerate(st.session_state.schedule_fields):
            row.setdefault("is_image", False)
            c1, c2, c3, c4 = st.columns([3, 5, 1, 1])
            row["name"] = c1.text_input("Tên field", value=row["name"], key=f"sched_fname_{idx}", placeholder="gia_ban")
            row["desc"] = c2.text_input(
                "Mô tả tự nhiên", value=row["desc"], key=f"sched_fdesc_{idx}", placeholder="Giá bán ra niêm yết"
            )
            row["is_image"] = c3.checkbox(
                "Ảnh", value=row["is_image"], key=f"sched_fimg_{idx}",
                help="Field này là URL ảnh — tải file về data/images/ thay vì chỉ lưu URL.",
            )
            if c4.button("🗑", key=f"sched_rmf_{idx}") and len(st.session_state.schedule_fields) > 1:
                st.session_state.schedule_fields.pop(idx)
                st.rerun()
        if st.button("＋ Thêm field", key="sched_add_field"):
            st.session_state.schedule_fields.append({"name": "", "desc": "", "is_image": False})
            st.rerun()
        field_descriptions = {
            f["name"].strip(): f["desc"].strip()
            for f in st.session_state.schedule_fields
            if f["name"].strip() and f["desc"].strip()
        }
        schedule_image_fields = [
            f["name"].strip() for f in st.session_state.schedule_fields if f.get("is_image") and f["name"].strip()
        ]
    elif chosen_dataset is not None:
        st.caption("Dataset có sẵn yêu cầu đúng tên field theo schema hiện có.")
        for name in chosen_dataset["schema_signature"]:
            dc1, dc2 = st.columns([5, 1])
            field_descriptions[name] = dc1.text_input(
                f"Mô tả cho '{name}'",
                key=f"schedule_desc_{chosen_dataset['dataset_id']}_{name}",
                placeholder="Mô tả tự nhiên để AI hiểu field này",
            )
            is_image = dc2.checkbox(
                "Ảnh", key=f"schedule_img_{chosen_dataset['dataset_id']}_{name}",
                help="Field này là URL ảnh — tải file về data/images/ thay vì chỉ lưu URL.",
            )
            if is_image:
                schedule_image_fields.append(name)

    file_path, write_mode, key_field = "", "append", None
    if is_schedule_file_mode:
        st.markdown("**Cấu hình lưu file**")
        sfc1, sfc2 = st.columns([3, 2])
        with sfc1:
            sched_file_name = st.text_input(
                "Tên file", key="schedule_file_name", placeholder="VD: gia-vang"
            )
        with sfc2:
            sched_file_format_label = st.selectbox(
                "Định dạng", list(_FILE_FORMATS.keys()), key="schedule_file_format_select"
            )
        file_path = f"{sched_file_name.strip()}.{_FILE_FORMATS[sched_file_format_label]}"
        write_mode_label = st.selectbox(
            "Cách ghi", list(_WRITE_MODE_LABELS.keys()), key="schedule_write_mode_select"
        )
        write_mode = _WRITE_MODE_LABELS[write_mode_label]
        if write_mode == "overwrite_row":
            field_names = list(field_descriptions.keys())
            if field_names:
                key_field = st.selectbox("Trường dùng làm khoá", field_names, key="schedule_key_field_select")
            else:
                st.info("Khai báo ít nhất 1 field ở trên để chọn trường khoá.")

    st.markdown("**Tần suất chạy**")
    freq_mode = st.selectbox(
        "Chọn tần suất",
        ["Hàng giờ", "Mỗi N giờ (tuỳ chỉnh)", "Hàng ngày lúc giờ:phút"],
        key="schedule_freq_mode",
    )
    if freq_mode == "Hàng giờ":
        trigger_type, trigger_args = "interval", {"hours": 1}
    elif freq_mode == "Mỗi N giờ (tuỳ chỉnh)":
        n_hours = st.number_input(
            "Số giờ giữa mỗi lần chạy", min_value=1, max_value=168, value=6, key="schedule_n_hours"
        )
        trigger_type, trigger_args = "interval", {"hours": int(n_hours)}
    else:
        run_time = st.time_input("Giờ chạy hàng ngày", key="schedule_time")
        trigger_type, trigger_args = "cron", {"hour": run_time.hour, "minute": run_time.minute}

    if st.button("+ Tạo lịch", type="primary"):
        missing = [name for name, desc in field_descriptions.items() if not desc.strip()]
        if not url.strip():
            st.warning("Cần nhập URL.")
        elif not field_descriptions:
            st.warning("Cần khai báo ít nhất 1 field có đủ tên và mô tả.")
        elif missing:
            st.warning("Cần mô tả cho field: " + ", ".join(missing))
        elif is_schedule_file_mode and not sched_file_name.strip():
            st.warning("Cần nhập tên file.")
        elif is_schedule_file_mode and write_mode == "overwrite_row" and not key_field:
            st.warning("Cần chọn trường khoá cho cách ghi 'Ghi đè theo trường'.")
        elif not is_schedule_file_mode and chosen_dataset is None:
            st.warning("Cần chọn 1 dataset.")
        else:
            body: dict[str, Any] = {
                "url": url.strip(),
                "field_descriptions": field_descriptions,
                "trigger_type": trigger_type,
                "trigger_args": trigger_args,
                "image_fields": schedule_image_fields,
            }
            if is_schedule_file_mode:
                body["storage_mode"] = "file"
                body["file_path"] = file_path.strip()
                body["write_mode"] = write_mode
                if write_mode == "overwrite_row":
                    body["key_field"] = key_field
            else:
                body["dataset_id"] = chosen_dataset["dataset_id"]

            result = _api_post("/schedules", body)
            if result is not None and not result.get("_http_error"):
                st.success("Đã tạo lịch tự động.")
                if is_schedule_file_mode:
                    st.session_state.schedule_fields = [{"name": "", "desc": ""}]
                st.rerun()
            elif result is not None:
                st.error(f"Lỗi tạo lịch: {result['detail']}")

    if st.button("← Quay lại Bước 4"):
        st.session_state.step = 4
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


_RENDERERS = {
    1: _render_step1,
    2: _render_step2,
    3: _render_step3,
    4: _render_step4,
    5: _render_step5,
}
try:
    _RENDERERS[st.session_state.step]()
except Exception as exc:
    frames = []
    tb = exc.__traceback__
    while tb:
        if tb.tb_frame.f_code.co_filename.replace("\\", "/").endswith("ui/app.py"):
            frames.append({"file": "ui/app.py", "line": tb.tb_lineno})
        tb = tb.tb_next
    kind = type(exc).__name__
    allowed = {"TypeError", "ValueError", "KeyError", "IndexError", "AttributeError", "HTTPError", "RuntimeError"}
    st.session_state.crawl_ui_error = {"error_type": kind if kind in allowed else "Other", "frames": frames[-12:]}
    st.error("Không hiển thị được bước này. Bạn vẫn có thể báo lỗi cho admin bên dưới.")
render_background(_client)
report_panel(_api_post)
_last_attempt = (st.session_state.get("crawl_attempts") or [{}])[-1]
feedback_panel(_api_post, f"crawl-buoc-{st.session_state.get('step', 1)}", _last_attempt.get("request_id"))
