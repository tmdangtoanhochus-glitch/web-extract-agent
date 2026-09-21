"""Khung "Automation là gì và dùng thế nào" — mô tả kỹ thuật cho người dùng mới, hiện sau khi đăng nhập."""
from __future__ import annotations

import streamlit as st

try:
    from ui.notices import blocking_notice
except ModuleNotFoundError as exc:
    if exc.name != "ui":
        raise
    from notices import blocking_notice


def render(expanded: bool = True) -> None:
    with st.expander("📘 Automation là gì? Dùng như thế nào?", expanded=expanded):
        st.markdown(
            """
**Automation là bộ chạy kiểm thử giao diện (UI test) theo dữ liệu**: mô tả flow bằng workbook `.xlsx`, agent cục bộ chạy
Playwright trên trình duyệt thật của máy bạn, so giá trị đọc được với `expected_*` và ghi PASS / FAIL / UNVERIFIED cho từng ca.
Server chỉ soạn workbook, điều phối và lưu tóm tắt; **thao tác trình duyệt và thông tin đăng nhập không đi qua server**.

**Kiến trúc**
- **Workbook** gồm sheet `steps` (mỗi dòng: `screen`, `step`, `action`, `locator_type`, `locator`, `value_source`, `wait_selector`,
  `read_method`, `group`…) và sheet `testcases` (`tc_id`, `mo_ta`, `active`, cột dữ liệu theo từng `step` và cột `expected_*`).
  `action` thuộc tập cố định: `fill`, `click`, `select_antd`, `radio`, `upload`, `wait`, `read_result*`…; `locator` là CSS selector.
- **Agent** (`local_runner_agent.py`) là tiến trình trên máy bạn: xác thực bằng **Bearer token một lần**, gọi `POST /claim` để nhận run,
  gửi heartbeat khi đang chạy, ghi journal cục bộ để không chạy lại run sau khi crash, rồi gửi lại **chỉ metadata kết quả** (số ca PASS/FAIL/lỗi, thời gian).
- **Executor** chạy Playwright (Chrome / Edge / Firefox), thực thi từng `step` theo `testcase`, đọc kết quả bằng `read_method`
  (`css_input`, `label_input`, `sibling_span`…), so **chính xác** với `expected_*`, chụp ảnh khi lỗi (`screenshot_on_error`).
  Nhóm bản ghi lặp dùng cột `group` và các cột `expected_<field>_<n>`.
- **`runner.env`** giữ `PREFIX_USERNAME` / `PREFIX_PASSWORD` của hệ thống được test, chỉ nằm trên máy bạn; workbook tham chiếu bằng `value_source=account`.
- **AI (server)** chỉ sinh hoặc sửa `steps` theo schema đóng (validator từ chối field lạ, `locator` chỉ được là placeholder để bạn điền/repair);
  không nhận mật khẩu, không nhận dữ liệu trên trang, không tự đặt `testcases` hay kết quả mong đợi.

**Các tab**

| Tab | Chức năng kỹ thuật | Chạy ở đâu |
|---|---|---|
| **Describe** | Mô tả flow bằng văn bản → AI sinh sheet `steps` nháp đúng schema, khung `testcases` suy ra từ `steps`. | Server (AI) |
| **Record local** | Recorder (`recorder.js`) ghi thao tác và selector thật trên trang; upload bản ghi để AI chuẩn hóa thành `steps`. | Máy bạn → server |
| **Inspector local** | `inspect_runner.py` kiểm tra từng `locator` còn khớp đúng 1 phần tử hiển thị không; `repair_runner.py` cho bạn rê chuột chọn phần tử thay thế (Ctrl+Alt+L) rồi xuất bản sao đã đổi locator; `try_step_runner.py` chạy thử 1 step thật có xác nhận. | Máy bạn (báo cáo chỉ là metadata) |
| **Agent** | Tạo agent, nhận token một lần để cấu hình `local_runner_agent.py`. | Server + máy bạn |
| **Chạy testcase** | Tạo run (agent + workbook); agent claim và thực thi. | Server giao, máy bạn chạy |
| **Lịch sử & kết quả** | Tổng hợp trạng thái từng run: PASS / FAIL / ERROR, thời gian. Run lỗi có nút **Gợi ý sửa** (gợi ý cố định theo mã lỗi kiểm tra tĩnh + AI, chỉ dựa trên metadata) và **Báo lỗi cho admin**. Báo cáo chi tiết và ảnh nằm ở `data/local-runner` trên máy bạn. | Server |
| **Thông báo** | Nhắc khi báo cáo sắp hết hạn (lưu tối đa 7 ngày). | Server |

**Quy trình**
1. Tạo workbook bằng *Describe* hoặc *Record local*, điền các dòng `testcases` (giá trị nhập và `expected_*`).
2. *Inspector local*: xác nhận các `locator` còn khớp; sửa những locator hỏng.
3. Chạy agent trên máy (cài Python theo phần hướng dẫn bên dưới), cấu hình `runner.env` và token.
4. *Chạy testcase*: chọn agent + workbook → xem PASS/FAIL ở *Lịch sử & kết quả*; đối chiếu chi tiết trong file kết quả cục bộ.

**Ranh giới bảo mật:** server không mở trình duyệt; mọi phiên Playwright chạy trên máy bạn. `runner.env`, cookie và dữ liệu trang không được tải lên.
            """
        )
    blocking_notice()  # luôn hiện, không nằm trong khung thu gọn
