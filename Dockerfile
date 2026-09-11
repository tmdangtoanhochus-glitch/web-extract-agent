FROM python:3.12-slim

WORKDIR /app

# Cài dependency hệ thống cần cho Playwright (Chromium)
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Cài trình duyệt Playwright + dependency hệ thống đi kèm
RUN playwright install --with-deps chromium

COPY . .

EXPOSE 8000

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
