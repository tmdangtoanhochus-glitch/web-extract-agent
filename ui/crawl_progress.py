"""Hai thanh tiến độ tách biệt cho màn Crawl: ① CODE (tải + làm sạch trang) và ② AI (từng đoạn model xử lý).

Mục đích: người dùng biết lúc này đang là CODE chạy hay MODEL AI đang xử lý, hay đang CHỜ hạn mức AI (delay có chủ đích
để không vượt rate limit — không phải lỗi/treo).

- `phase_view()` là hàm thuần (nhận dict tiến độ từ API, trả nhãn + giá trị 0..1) nên test được không cần Streamlit.
- `run_with_progress()` chạy request /crawl trong luồng nền còn luồng chính hỏi `GET /crawl-progress/{id}` mỗi ~1 giây để
  cập nhật thanh (Streamlit chỉ cho vẽ từ luồng chính; luồng nền KHÔNG được gọi `st.*`)."""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, Optional

import streamlit as st

_POLL_SECONDS = 0.8


def _dots(number: int) -> str:
    return f"{number:,}".replace(",", ".")


def phase_view(progress: Optional[dict]) -> dict[str, Any]:
    p = progress or {}
    phase = p.get("phase")
    total = int(p.get("ai_chunks_total") or 0)
    done = int(p.get("ai_chunks_done") or 0)
    failed = int(p.get("ai_chunks_failed") or 0)
    calling = int(p.get("ai_calling") or 0)
    waiting = int(p.get("ai_waiting") or 0)
    wait = int(p.get("ai_wait_seconds") or 0)
    retries = int(p.get("ai_retries") or 0)
    current = p.get("ai_current_chunk")
    model = p.get("ai_model") or "model"
    chars = int(p.get("markdown_chars") or 0)
    ai_skipped = bool(p.get("ai_skipped")) or phase == "ai_skipped"

    # ---- ① Crawl (code)
    if phase is None:
        crawl_value, crawl_label = 0.0, "① Crawl — đang khởi động…"
    elif phase == "fetch":
        crawl_value, crawl_label = 0.25, "① Crawl — đang tải trang (code chạy, chưa gọi AI)"
    elif phase == "clean":
        crawl_value, crawl_label = 0.7, "① Crawl — đang làm sạch HTML → Markdown (code chạy)"
    else:
        size = f" ({_dots(chars)} ký tự gửi AI)" if chars else ""
        crawl_value, crawl_label = 1.0, f"① Crawl — xong: đã tải và làm sạch{size}"

    # ---- ② AI (model)
    if ai_skipped:
        reason = "nội dung không đổi" if p.get("unchanged") else "lấy được từ dữ liệu có sẵn/cache"
        ai_value, ai_label = 1.0, f"② AI — không cần gọi ({reason})"
    elif total > 0:
        ai_value = min(done / total, 1.0)
        extras = []
        if calling:
            where = f" đoạn {current}/{total}" if current and calling == 1 else f" {calling} đoạn"
            extras.append(f"🤖 {model} đang xử lý{where}")
        if waiting:
            extras.append(f"⏳ {waiting} đoạn chờ hạn mức (~{wait}s)")
        if retries:
            extras.append(f"🔁 thử lại {retries} lần")
        if failed:
            extras.append(f"⚠ {failed} đoạn lỗi")
        if p.get("ai_truncated"):
            extras.append("trang quá dài: chỉ xử lý các đoạn đầu")
        ai_label = f"② AI — {done}/{total} đoạn xong" + (" · " + " · ".join(extras) if extras else "")
    elif phase in ("save", "done"):
        ai_value, ai_label = 1.0, "② AI — xong"
    elif phase == "cleaned":
        ai_value, ai_label = 0.0, "② AI — sắp gửi cho model…"
    else:
        ai_value, ai_label = 0.0, "② AI — chờ tới bước này"

    # ---- Ai đang làm việc?
    if phase is None:
        who = "⚙️ **CODE đang chạy** — khởi động, gửi yêu cầu"
    elif phase == "fetch":
        who = "⚙️ **CODE đang chạy** — tải trang"
    elif phase == "clean":
        who = "⚙️ **CODE đang chạy** — làm sạch trang"
    elif phase == "cleaned":
        who = "⚙️ **CODE đang chạy** — chuẩn bị gửi cho AI"
    elif phase == "ai" and calling:
        who = f"🤖 **MODEL AI đang xử lý** ({model})"
    elif phase == "ai" and waiting:
        who = f"⏳ **Đang chờ hạn mức AI** ~{wait}s (delay có chủ đích để không vượt rate limit — không phải lỗi)"
    elif phase == "ai":
        who = "⚙️ **CODE đang chạy** — xử lý kết quả AI / chuẩn bị đoạn tiếp theo"
    elif phase == "ai_skipped":
        who = "⚙️ **CODE đang chạy** — dữ liệu có sẵn, bỏ qua AI"
    elif phase == "save":
        who = "💾 **CODE đang lưu** dữ liệu"
    elif phase == "done":
        who = "✅ **Hoàn tất**"
    else:
        who = "⚙️ **CODE đang chạy**"
    return {"who": who, "crawl_value": crawl_value, "crawl_label": crawl_label,
            "ai_value": ai_value, "ai_label": ai_label, "phase": phase}


class ProgressPanel:
    """Vùng hiển thị 1 dòng "ai đang chạy" + 2 thanh tiến độ; tạo placeholder 1 lần rồi cập nhật tại chỗ."""

    def __init__(self) -> None:
        self._title = st.empty()
        self._who = st.empty()
        self._crawl = st.empty()
        self._ai = st.empty()
        self._start = time.monotonic()

    def reset(self, title: str) -> None:
        self._start = time.monotonic()
        self._title.markdown(f"**{title}**")
        self.update(None)

    def update(self, progress: Optional[dict]) -> None:
        view = phase_view(progress)
        elapsed = int(time.monotonic() - self._start)
        self._who.markdown(f"{view['who']} · ⏱ {elapsed}s")
        self._crawl.progress(view["crawl_value"], text=view["crawl_label"])
        self._ai.progress(view["ai_value"], text=view["ai_label"])


def render_static(progress: Optional[dict]) -> None:
    """Cho fragment tự làm mới (job nền): vẽ thẳng, không cần placeholder."""
    view = phase_view(progress)
    st.markdown(view["who"])
    st.progress(view["crawl_value"], text=view["crawl_label"])
    st.progress(view["ai_value"], text=view["ai_label"])


def run_with_progress(
    job: Callable[[], Any],
    fetch_progress: Callable[[], Optional[dict]],
    panel: ProgressPanel,
    interval: float = _POLL_SECONDS,
) -> Any:
    """Chạy `job` (request /crawl chặn) ở luồng nền; luồng chính vẽ tiến độ đến khi xong. `job` và `fetch_progress`
    KHÔNG được gọi `st.*`. Lỗi của `job` được ném lại ở luồng chính."""
    box: dict[str, Any] = {}

    def target() -> None:
        try:
            box["value"] = job()
        except BaseException as exc:  # noqa: BLE001 - ném lại ở luồng chính
            box["error"] = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()

    def poll() -> None:
        try:
            data = fetch_progress()
        except Exception:  # noqa: BLE001 - không lấy được tiến độ thì thôi, không phá crawl
            data = None
        if isinstance(data, dict):
            panel.update(data)

    while True:
        poll()
        thread.join(interval)
        if not thread.is_alive():
            break
    poll()  # trạng thái cuối cùng
    if "error" in box:
        raise box["error"]
    return box.get("value")
