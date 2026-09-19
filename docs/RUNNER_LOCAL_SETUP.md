# Cài môi trường Python để chạy Automation trên máy của bạn

Tài liệu dành cho người dùng cuối. Trang web (Crawl / Automation / Admin) chạy trên server, nhưng ba việc sau chạy **trên máy của bạn**
vì cần điều khiển trình duyệt thật:

| Việc | Lệnh |
|---|---|
| Ghi thao tác (Record) | `python record_runner.py ...` |
| Xem cấu trúc trang (Inspector) | `python inspect_runner.py ...` |
| Chạy testcase (Agent) | `python local_runner_agent.py ...` |

Làm lần lượt các bước dưới đây, **một lần duy nhất** cho mỗi máy. Hướng dẫn viết cho Windows (PowerShell); phần macOS/Linux ở cuối.

## 0. Chuẩn bị
- Windows 10/11, còn trống khoảng **3 GB** ổ đĩa (Python, thư viện và trình duyệt Chromium).
- Kết nối internet, và máy truy cập được trang web cần test.
- Thông tin bạn cần hỏi quản trị viên: **địa chỉ API** (ví dụ `https://xxxx.agentbase-runtime.aiplatform.vngcloud.vn`) và một
  **tài khoản Runner** (username/mật khẩu để đăng nhập trang Automation).

## 1. Cài Python 3.12
1. Tải Python **3.12** tại <https://www.python.org/downloads/windows/> (bản "Windows installer 64-bit").
2. Khi cài, **tick ô "Add python.exe to PATH"** ở màn hình đầu tiên, rồi bấm Install Now.
3. Mở **PowerShell mới** và kiểm tra:
   ```powershell
   python --version
   ```
   Phải hiện `Python 3.12.x`. Nếu báo không tìm thấy lệnh, thử `py -3.12 --version`; nếu vẫn không được thì cài lại và nhớ tick PATH.

> Dùng đúng 3.12: các thư viện trong dự án được kiểm thử trên bản này. Bản quá mới hoặc quá cũ có thể lỗi khi cài.

## 2. Lấy mã nguồn
Agent cần thư mục `src/`, `runner_agent/`, `docs/runner.py` và các script ở thư mục gốc, nên lấy **cả dự án**:
```powershell
git clone https://github.com/tmdangtoanhochus-glitch/web-extract-agent.git
cd web-extract-agent
```
Không có git thì vào trang GitHub của dự án, bấm **Code → Download ZIP**, giải nén, rồi mở PowerShell trong thư mục vừa giải nén.
**Mọi lệnh bên dưới đều phải chạy từ thư mục gốc dự án** (nơi có file `requirements.txt`).

## 3. Tạo môi trường ảo (venv)
Môi trường ảo giữ thư viện của dự án tách khỏi Python của hệ thống, tránh xung đột phiên bản:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```
Thành công khi đầu dòng lệnh hiện `(.venv)`. Mỗi lần mở PowerShell mới bạn phải chạy lại dòng `Activate.ps1`.

Nếu báo *"running scripts is disabled on this system"*, chạy dòng sau (chỉ có tác dụng trong cửa sổ này) rồi kích hoạt lại:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## 4. Cài thư viện
```powershell
$env:PYTHONUTF8 = "1"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r requirements-auth.txt -r requirements-runner.txt
```
Dòng đầu (`PYTHONUTF8`) tránh lỗi `UnicodeDecodeError ... cp1252` khi pip đọc file có tiếng Việt. Bước này mất vài phút.

## 5. Cài trình duyệt cho Playwright
```powershell
python -m playwright install chromium
```
Tải khoảng vài trăm MB. Đây là trình duyệt mà Record, Inspector và Agent dùng để mở trang.

## 6. Kiểm tra môi trường đã đủ
```powershell
python -c "import playwright, pandas, openpyxl, dotenv, httpx, pydantic; print('Thu vien OK')"
python -c "from playwright.sync_api import sync_playwright as s; p=s().start(); b=p.chromium.launch(); print('Chromium OK', b.version); b.close(); p.stop()"
```
Cả hai dòng phải in `... OK`. Nếu dòng nào lỗi, xem mục **Xử lý lỗi thường gặp** bên dưới.

## 7. Tạo file thông tin đăng nhập của trang cần test
User/pass của **trang được test** (không phải tài khoản Runner) chỉ nằm trên máy bạn:
```powershell
Copy-Item runner.env.example runner.env
notepad runner.env
```
Điền theo mẫu (`RM_USERNAME`, `RM_PASSWORD`, và các cặp `<ROLE>_USERNAME` / `<ROLE>_PASSWORD` cho từng role trong testcase).
- **Không** gửi file này cho ai, không dán vào chat, không đưa vào thư mục upload. `*.env` đã bị git bỏ qua.
- Workbook chỉ ghi **tên role/placeholder**, không ghi mật khẩu thật.

## 8. Chạy từng phần
Thay `<API>` bằng địa chỉ API quản trị viên cấp.

**a. Ghi thao tác** (mở trình duyệt, bạn thao tác trên trang cần test):
```powershell
python record_runner.py --output config/Recorded_Draft.xlsx --events-output config/Recorded_Events.json
```
Sau đó vào trang **Automation → Record local**, tải lên file `Recorded_Events.json` để AI chuẩn hóa thành testcase.

**b. Xem cấu trúc trang (Inspector):**
```powershell
python inspect_runner.py --config config/<ten-workbook>.xlsx --output config/Inspected.json
```

**c. Kiểm tra workbook trước khi chạy** (không mở trình duyệt, không đọc `runner.env`):
```powershell
python preflight_runner.py --config config/<ten-workbook>.xlsx
```

**d. Chạy testcase bằng Agent:**
1. Trên web: đăng nhập trang **Automation**, mở tab **Agent**, tạo agent và **copy token** (chỉ hiện một lần).
2. Trên máy bạn:
   ```powershell
   python local_runner_agent.py --api <API> --configs config --state data/local-runner --env-path runner.env
   ```
   Agent hỏi token bằng ô nhập ẩn (gõ vào sẽ không thấy gì, dán rồi bấm Enter là được).
3. Trên web: chọn agent và workbook rồi tạo run. Kết quả chi tiết (log, ảnh chụp) nằm trong thư mục `data/local-runner`
   trên máy bạn; server chỉ nhận số đếm PASS/FAIL và thời gian.

Để agent chạy liên tục, giữ cửa sổ PowerShell đó mở. Đóng cửa sổ là agent dừng.

## Xử lý lỗi thường gặp

| Triệu chứng | Cách xử lý |
|---|---|
| `python` không được nhận diện | Cài lại Python và tick "Add python.exe to PATH", mở PowerShell mới. Hoặc dùng `py -3.12` thay cho `python`. |
| `Activate.ps1 ... running scripts is disabled` | Chạy `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` rồi kích hoạt lại. |
| `UnicodeDecodeError: 'charmap' codec ...` khi pip | Chạy `$env:PYTHONUTF8 = "1"` rồi cài lại. |
| `ModuleNotFoundError: No module named 'src'` (hoặc `runner_agent`) | Bạn đang đứng sai thư mục. `cd` về thư mục gốc dự án (có `requirements.txt`) rồi chạy lại. |
| `ModuleNotFoundError: No module named 'playwright'` (hoặc pandas...) | Chưa kích hoạt venv (thiếu `(.venv)` đầu dòng) hoặc chưa cài thư viện: kích hoạt rồi chạy lại bước 4. |
| `Executable doesn't exist ... chromium` | Chưa cài trình duyệt: chạy `python -m playwright install chromium`. |
| Lỗi mạng/SSL khi pip hoặc playwright tải về | Máy đang qua proxy công ty: nhờ IT cấp cấu hình proxy (`HTTPS_PROXY`), hoặc thử mạng khác. |
| Agent báo `401` / không đăng nhập được | Token agent sai hoặc hết hạn: tạo agent mới trên trang Automation và dán token mới. |
| Không kết nối được `<API>` | Kiểm tra địa chỉ (đủ `https://`), thử mở `<API>/health` trên trình duyệt, phải thấy `{"status":"ok"}`. |
| Ổ đĩa đầy khi cài | Cần khoảng 3 GB trống; dọn ổ đĩa rồi cài lại. |

## macOS / Linux
Các bước giống nhau, khác ở vài lệnh:
```bash
python3.12 -m venv .venv
source .venv/bin/activate
export PYTHONUTF8=1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r requirements-auth.txt -r requirements-runner.txt
python -m playwright install chromium
cp runner.env.example runner.env
```
Trên Linux có thể cần thêm thư viện hệ thống cho Chromium: `python -m playwright install --with-deps chromium` (cần quyền sudo).

## Cập nhật sau này
Khi có phiên bản mới của dự án: vào thư mục dự án, chạy `git pull`, kích hoạt venv, rồi chạy lại bước 4 để cập nhật thư viện.
