# Web Data Extraction & Management Platform

Ứng dụng cho phép người dùng nghiệp vụ (non-technical) tự cấu hình thu thập dữ liệu từ
website được phép, không cần viết code — nhập URL + mô tả field cần lấy bằng ngôn ngữ
tự nhiên, hệ thống tự crawl và AI trích xuất theo cấu trúc.

Xem `CLAUDE.md` để biết đầy đủ kiến trúc, nguyên tắc thiết kế và quy ước code.

## Chạy thử (local, không cần Docker)

```bash
pip install -r requirements.txt
playwright install chromium

cp .env.example .env
# điền AI_BASE_URL / AI_API_KEY thật vào .env

python -m pytest tests/ -v          # chạy test bằng mock, không cần credentials
uvicorn src.api.main:app --reload    # chạy backend
streamlit run ui/app.py              # chạy giao diện (terminal khác)
```

## Chạy bằng Docker

```bash
cp .env.example .env
# điền .env

docker compose up --build
```
- API: http://localhost:8000
- UI: http://localhost:8501

## Compliance

Mặc định luôn kiểm tra `robots.txt` và có delay giữa các request theo domain
(`FETCH_DEFAULT_DELAY_SECONDS` trong `.env`). Không tắt kiểm tra robots.txt trừ khi có
lý do rõ ràng và được ghi log lại tường minh.

## Cấu trúc project

Xem mục "Nguyên tắc thiết kế bắt buộc" trong `CLAUDE.md` — tóm tắt: fetch/clean/AI/storage
tách rời theo adapter pattern, AI chỉ trích xuất chứ không tự quyết định nghiệp vụ, dữ liệu
lưu dạng `dataset` + JSON linh hoạt thay vì tạo bảng SQL riêng từng loại.
