"""Lưu ý dùng chung: rủi ro khi dán cookie, và các loại chặn tự động mà một số website áp dụng (Crawl + Automation)."""
from __future__ import annotations

import streamlit as st

COOKIE_CONSENT_LABEL = "Tôi hiểu các rủi ro trên và chấp nhận dùng cookie của mình cho lượt này"

COOKIE_RISK_TEXT = """
**⚠️ Rủi ro khi dùng cookie đăng nhập — đọc trước khi dán:**
- Cookie giống **chìa khóa đăng nhập**: ai có nó đều có thể thao tác như bạn trên website đó cho tới khi cookie hết hạn hoặc bạn đăng xuất.
- Cookie được gửi tới server của hệ thống này để tải trang. Hệ thống chỉ giữ trong bộ nhớ, **không ghi DB hay log**, nhưng người quản trị hạ tầng về nguyên tắc có thể truy cập bộ nhớ máy chủ.
  Vì vậy chỉ dùng phiên bạn **được phép** dùng, ưu tiên tài khoản riêng chỉ-đọc; **đừng dùng tài khoản quản trị hoặc tài khoản chứa dữ liệu nhạy cảm**.
- Website có thể coi việc dùng cookie để thu thập tự động là **vi phạm điều khoản sử dụng** và khóa hoặc cảnh báo tài khoản của bạn.
- Dữ liệu sau đăng nhập có thể chứa **thông tin cá nhân**; chỉ thu thập khi bạn có quyền và mục đích hợp lệ.
- Sau khi kéo xong, hãy **đăng xuất khỏi website** để cookie mất hiệu lực, và không chia sẻ ảnh chụp có chứa cookie.

Nếu bạn tiếp tục, tức là bạn **chấp nhận các rủi ro trên** và tự chịu trách nhiệm về việc dùng cookie này.
"""

BLOCKING_SUMMARY = (
    "Một số website **chặn hoặc không cho phép truy cập tự động** (CAPTCHA, tường bảo vệ bot, giới hạn IP...). "
    "Với những trang này, hệ thống có thể không lấy được dữ liệu. Xem chi tiết bên dưới."
)

BLOCKING_DETAILS = """
**Những thứ thường chặn công cụ tự động:**
1. **CAPTCHA / kiểm tra "bạn là người"**: reCAPTCHA, hCaptcha, Cloudflare Turnstile, ô kéo hoặc ghép hình.
2. **Tường bảo vệ bot (WAF)**: Cloudflare, Akamai, Imperva, DataDome, HUMAN (PerimeterX), AWS WAF. Dấu hiệu: lỗi `403`/`429`, trang "Checking your browser", HTML gần như rỗng.
3. **Giới hạn tốc độ và chặn IP**: gửi quá nhiều yêu cầu bị chặn; IP của trung tâm dữ liệu hoặc đám mây (như server của hệ thống này) hay bị chặn hơn IP mạng gia đình/công ty.
4. **Nhận diện trình duyệt tự động** (headless, dấu vân tay trình duyệt) và hành vi bất thường (thao tác quá nhanh, không cuộn, không di chuột).
5. **Đăng nhập nhiều lớp**: OTP/SMS, 2FA, xác thực sinh trắc, "thiết bị tin cậy", cookie hết hạn rất nhanh hoặc gắn với IP/thiết bị.
6. **Dữ liệu khó lấy**: nạp bằng JavaScript phức tạp, API có token thay đổi liên tục, nội dung trong iframe khác miền, canvas hoặc ảnh, cuộn vô hạn.
7. **Quy định của website**: `robots.txt` cấm, điều khoản sử dụng cấm thu thập tự động, yêu cầu pháp lý về dữ liệu cá nhân.
8. **Giới hạn địa lý hoặc mạng**: chỉ cho IP trong nước, danh sách IP được phép, ứng dụng chỉ truy cập được trong mạng nội bộ/VPN.
9. **Bẫy và thay đổi liên tục**: liên kết ẩn (honeypot), giao diện đổi cấu trúc thường xuyên làm hỏng locator/selector.

**Hệ thống này không giải CAPTCHA và không cố vượt qua các cơ chế bảo vệ trên** — gặp thì lượt kéo sẽ báo lỗi hoặc trả dữ liệu rỗng.

**Cách xử lý hợp lệ:** dùng **API chính thức** hoặc nguồn dữ liệu công khai của website; **xin phép chủ website** (hoặc nhờ họ cho phép IP của bạn); giảm tốc độ và tăng độ trễ giữa các lượt kéo;
dùng tài khoản của chính bạn; với Automation, chạy trên máy trong mạng bạn được phép truy cập; nếu website yêu cầu con người xác nhận thì thực hiện thủ công.
"""


def cookie_risk_panel() -> None:
    """Cảnh báo rủi ro cookie (dùng ngay trong khung dán cookie)."""
    st.warning(COOKIE_RISK_TEXT)


def blocking_notice(expanded: bool = False) -> None:
    """Lưu ý website có thể chặn tự động, kèm danh sách chi tiết."""
    st.warning(BLOCKING_SUMMARY)
    with st.expander("Xem chi tiết: website có thể chặn bằng cách nào và nên làm gì", expanded=expanded):
        st.markdown(BLOCKING_DETAILS)
