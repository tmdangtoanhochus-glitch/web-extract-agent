"""Ô "Phản hồi / báo lỗi" dùng chung cho mọi màn hình.

Người dùng điền mô tả tự do -> `POST /feedback` -> AI_DEBUG phân loại. Nếu AI
chắc chắn KHÔNG phải lỗi thì câu trả lời hiện ngay tại đây; nếu là lỗi (hoặc AI
không chắc) thì backend gom trace và chuyển admin, người dùng nhận mã theo dõi.
"""
from __future__ import annotations

import streamlit as st


def feedback_panel(api_post, screen: str, request_id: str | None = None) -> None:
    """`api_post(path, body)` trả dict, hoặc dict có `_http_error`/None khi lỗi."""
    key = f"fb_{screen}"
    with st.expander("💬 Gặp vấn đề? Gửi phản hồi / báo lỗi"):
        message = st.text_area(
            "Mô tả bạn gặp gì (bạn đang làm gì, mong đợi gì, thấy gì). Không dán cookie/mật khẩu.",
            key=f"{key}_msg", max_chars=2000,
        )
        if st.button("Gửi phản hồi", key=f"{key}_send"):
            if len(message.strip()) < 5:
                st.warning("Vui lòng mô tả rõ hơn (tối thiểu 5 ký tự).")
                return
            body = {"screen": screen, "message": message.strip()}
            if request_id:
                body["request_id"] = request_id
            with st.spinner("Đang phân tích phản hồi..."):
                result = api_post("/feedback", body)
            if not result or result.get("_http_error"):
                detail = (result or {}).get("detail", "không kết nối được API")
                st.error(f"Chưa gửi được phản hồi: {detail}")
            elif result.get("status") == "answered":
                st.info(result["answer"])
            else:
                st.success(result["answer"])
