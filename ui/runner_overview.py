"""Khung "Automation là gì và dùng thế nào" — giải thích ngắn gọn cho người dùng mới, hiện sau khi đăng nhập."""
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
**Automation giúp bạn kiểm thử tự động một trang web**: ví dụ đăng nhập, tìm khách hàng, đọc số tiền, rồi so với kết quả mong đợi.
Mọi thao tác trên trình duyệt chạy **trên máy của bạn**; trang web này chỉ dùng để soạn, giao việc và xem tóm tắt kết quả.

Hình dung như một nhà hàng nhỏ:
- **File Excel (workbook)** là *công thức nấu ăn*: sheet `steps` liệt kê các bước (mở trang, nhập, bấm, đọc), sheet `testcases` liệt kê các ca cần thử và kết quả mong đợi.
- **Agent** là *đầu bếp* chạy trong máy bạn: thao tác trên trình duyệt thật theo công thức.
- **Trang web này** là *quầy nhận đơn*: bạn soạn công thức, giao việc cho đầu bếp và xem kết quả tổng hợp.
- **File `runner.env`** là *chìa khóa két* của trang được test (user/pass): nằm trong máy bạn, không bao giờ tải lên server.

**Các tab bên dưới dùng để làm gì**

| Tab | Việc bạn làm | Chạy ở đâu |
|---|---|---|
| **Describe** | Kể bằng lời flow cần test; AI viết file Excel **nháp** (sheet `steps` + khung `testcases`). Bạn tự điền các ca test. | Web (AI ở server) |
| **Record local** | Tự thao tác thật trên trang; hệ thống ghi lại. Tải file ghi lên để AI chuẩn hóa thành Excel đúng chuẩn. | Máy bạn, rồi web |
| **Inspector local** | Kiểm tra các phần tử trên trang (nút, ô nhập) còn tìm thấy không, và nhờ AI sửa khi trang đổi giao diện. | Máy bạn, rồi web |
| **Agent** | Đăng ký "đầu bếp": tạo agent, nhận **token một lần**, dán vào chương trình `local_runner_agent.py` trên máy. | Web + máy bạn |
| **Chạy testcase** | Giao việc: chọn agent và file Excel rồi bấm chạy; agent trên máy bạn nhận việc và thực hiện. | Web giao, máy bạn chạy |
| **Lịch sử & kết quả** | Xem tóm tắt từng lần chạy: bao nhiêu ca PASS/FAIL/lỗi, thời gian. File chi tiết và ảnh chụp nằm trong máy bạn. | Web |
| **Thông báo** | Nhắc khi báo cáo sắp bị xóa (lưu trên server tối đa 7 ngày). | Web |

**Luồng thường dùng**
1. **Soạn:** dùng *Describe* (kể bằng lời) hoặc *Record local* (thao tác thật) để có file Excel.
2. **Kiểm tra:** chạy *Inspector local* cho chắc các phần tử vẫn còn.
3. **Giao việc:** mở agent trên máy (xem phần cài môi trường bên dưới), rồi ở tab *Chạy testcase* chọn agent và file.
4. **Xem kết quả:** tóm tắt ở *Lịch sử & kết quả*; chi tiết trong thư mục `data/local-runner` trên máy bạn.

**Lưu ý:** không có tab nào mở trình duyệt trên server — trình duyệt hiện ra khi bạn bấm Record hay Chạy testcase chính là trình duyệt trên máy bạn.
AI chỉ nhận **cấu trúc** (tên bước, vị trí phần tử), không nhận mật khẩu hay dữ liệu trên trang.
            """
        )
    blocking_notice()  # luôn hiện, không nằm trong khung thu gọn
