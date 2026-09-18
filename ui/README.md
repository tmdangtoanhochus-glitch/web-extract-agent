# UI (Streamlit)

`app.py` — form 5 bước: Nguồn dữ liệu → Trường dữ liệu → Chạy & Kết quả → Dữ liệu đã lưu →
Lịch tự động. Chỉ gọi backend qua HTTP (`/crawl`, `/datasets`, `/datasets/{id}/records`,
`/schedules`), không import trực tiếp `src.*` — giữ ranh giới frontend/backend.

Bước 5 (Lịch tự động) tạo/xem/xoá job crawl định kỳ (APScheduler chạy ở backend, xem
`src/scheduler.py`) — job vẫn chạy nền dù đóng UI này, chỉ cần backend đang chạy.

Chạy (cần backend đang chạy ở cổng 8000):

```bash
uvicorn src.api.main:app --reload
streamlit run ui/crawl.py
```

Đổi địa chỉ backend bằng biến môi trường `API_BASE_URL` (mặc định `http://localhost:8000`).

Theme màu tham khảo phong cách từ mockup thiết kế ban đầu — **không** có Postgres config,
Data Dictionary/Lineage, hay visual selector (roadmap sau, xem `CLAUDE.md` mục "Việc CHƯA
làm trong MVP").
