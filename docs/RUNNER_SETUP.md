# Runner local: chạy thử bản tích hợp

## Phạm vi hiện tại

**Crawl công khai không cần đăng nhập.** Chỉ các chức năng Runner trên UI/API cần
tài khoản Runner. Panel quản trị crawler nhạy cảm giữ cơ chế bảo vệ riêng.
Gen chỉ tạo steps và header testcases; người dùng tự nhập toàn bộ testcase.
Không sinh settings. Thay đổi settings phải có lý do từ hàm cần dùng và được
người dùng duyệt từng mục; không đồng ý thì giữ nguyên.

Đã có executor workbook, tài khoản user/admin, agent polling, UI tạo/xem run,
phân quyền theo chủ sở hữu, summary và retention. Runner mặc định tắt để giữ
luồng crawler hiện tại. Có Record local và Describe AI xuất workbook nháp.
Có Inspector local kiểm tra locator và repair local theo phần tử người dùng chọn. AI repair và chuyển artifact
chi tiết lên cloud là phần chưa triển khai.

Cloud chỉ nhận số đếm PASS/FAIL/ERROR/UNVERIFIED và thời gian chạy. Excel, log,
screenshot nằm trong thư mục state trên máy agent. Masking không bảo đảm loại
bỏ mọi dữ liệu nghiệp vụ trên trang; không gửi các artifact này cho AI/cloud.

## Cài và bật

Chạy từ thư mục gốc project trong môi trường Python đang dùng cho ứng dụng:

```powershell
python -m pip install -r requirements.txt -r requirements-auth.txt -r requirements-runner.txt
python -m playwright install chromium
python scripts/create_runner_admin.py --username runneradmin
$env:RUNNER_ENABLED = 'true'
python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

Bootstrap hỏi mật khẩu bằng đầu vào ẩn, chỉ dùng cho database Runner SQLite
mặc định `data/runner.db`. Không chạy lại bootstrap trên database đã có user.
API và bootstrap phải trỏ cùng database nếu đổi đường dẫn. Backend PostgreSQL
có adapter nhưng chưa được kiểm chứng integration; chưa dùng làm cấu hình triển khai.

Ở terminal khác, chạy UI như trước:

```powershell
python -m streamlit run ui/app.py
```

Mở trang **Runner**, đăng nhập, tạo agent và giữ token được cấp một lần.
Trên máy truy cập được hệ thống cần test, chuẩn bị thư mục `config` chứa workbook
và file môi trường local theo `runner.env.example`. Chỉ người vận hành quản lý
file thật, không upload hoặc gửi nội dung cho trợ lý.

```powershell
python local_runner_agent.py --api http://localhost:8000 --configs config --state data/local-runner --env-path runner.env
```

Agent hỏi token bằng đầu vào ẩn. Dùng HTTPS nếu API ở máy khác. Trên UI chọn agent
và tên workbook trong thư mục config để tạo run. Chế độ local là mặc định;
Hybrid cho phép upload workbook đã bỏ dữ liệu nhạy cảm, server xóa bản tạm sau
khi kết thúc hoặc job hết hạn. Validator không thể nhận diện mọi secret tùy ý
trong Excel; người vận hành phải kiểm tra trước khi upload. Dùng `${TEN_BIEN}`
cho giá trị cần resolve từ môi trường local.

## Vận hành và giới hạn

- Mỗi agent chạy một job, mỗi run dùng process riêng; không tự chạy lại testcase
  khi mất kết nối. Chỉ kết quả được gửi lại. Nếu agent chết, kiểm tra trình duyệt/
  worker còn sống và trạng thái nghiệp vụ trước khi chủ động tạo run mới.
- Mất heartbeat quá 5 phút chuyển run sang LOST; kết quả đến muộn không đổi
  trạng thái terminal. Job chờ quá 24 giờ hết hạn.
- Artifact giữ 7 ngày, có thông báo trước khi xóa ít nhất 24 giờ. Agent offline
  thực hiện retention khi chạy lại; thời gian giữ có thể kéo dài. Metadata/audit
  giữ lại. UI hiển thị thông báo server, console agent hiển thị thông báo local.
- API cloud cần HTTPS, persistent storage, giới hạn request/login ở reverse proxy
  và quy trình backup trước khi đưa vào vận hành nhiều người dùng.
- Chưa kiểm chứng Docker/GreenNode deployment, PostgreSQL hoặc browser trên UAT thật.

## Record local (bản đầu)

Tạo sẵn thư mục config và chạy trên máy người dùng:

```powershell
python record_runner.py --output config/Recorded_Draft.xlsx
```

Browser mới không dùng profile đăng nhập có sẵn. Người dùng tự mở website và
thao tác; đóng các tab để xuất workbook. Recorder không đọc file môi trường,
giá trị input, text/attribute của phần tử hoặc URL điều hướng. Chỉ ghi click,
fill và select HTML chuẩn ở trang chính, bằng CSS theo vị trí phần tử.
Không gửi recording lên server. File output phải chưa tồn tại.

Workbook nháp có step `active=N`, sheet testcases chỉ chứa header; không có dòng
mẫu hoặc sheet settings. Ghép với config hiện có theo bước chuẩn bị bên dưới,
sau đó người dùng tự nhập testcase/role/input/expected. Không coi một flow chỉ
click/fill là testcase đã xác minh kết quả.

Giới hạn: chưa ghi iframe/shadow DOM, upload, checkbox/radio, dropdown tùy biến,
navigation hoặc assertion; tối đa 1000 event. CSS theo vị trí cần sửa khi layout
thay đổi. Số event bị từ chối nằm trong sheet review. Bản này chưa có AI hay
inspector tìm locator ổn định. Đóng browser bình thường để xuất; kill process
hoặc Ctrl+C có thể mất recording chưa xuất. Browser UAT thật cần người dùng kiểm chứng.

## Describe AI (steps đầy đủ cột, testcases chỉ header)

Backend dùng các biến runtime `AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL` và
`AI_TIMEOUT_SECONDS` đã có. Người vận hành tự cấu hình; không gửi giá trị thật
cho trợ lý. Để bật Describe, đặt thêm `RUNNER_AI_ENABLED=true` cùng
`RUNNER_ENABLED=true` rồi khởi động lại API. Endpoint AI phải dùng HTTPS
(HTTP chỉ cho loopback). Không cần thay client AI của crawler.

Trong tab **Describe**, nhập flow ngắn chỉ dùng role/placeholder, kiểm tra nội dung
không có dữ liệu nhạy cảm và xác nhận gửi cho AI. Bấm **Tạo workbook nháp**, sau đó
tải workbook về máy. API không lưu mô tả, phản hồi model hoặc workbook xuống disk/DB;
audit chỉ ghi event `DRAFT_GENERATED` và người thực hiện. UI giữ workbook trong phiên
cho đến khi xóa nháp hoặc đăng xuất. Nội dung mô tả được gửi tới nhà cung cấp AI;
chính sách lưu dữ liệu của nhà cung cấp nằm ngoài cơ chế lưu trữ của ứng dụng.

AI chỉ tạo JSON **steps**; Python kiểm tra schema rồi suy ra các header testcase
tương ứng. Workbook gồm:

- `steps`: `screen`, `step`, `action`, `locator_type`, `locator`, `value_source`,
  `active`, `wait_selector`, `dropdown_selector`, `match_type`, `prefill_check`,
  `group`, `read_method`.
- `testcases`: chỉ có hàng tên cột metadata, input và `expected_*`; không có
  testcase, scenario, giá trị hoặc placeholder mẫu được điền sẵn.
- `review`: những phần phải kiểm tra trước khi bật chạy.

Ví dụ mô tả: “Đăng nhập bằng account, tìm theo CIF rồi đọc số tiền để so sánh.
Chỉ tạo step và các cột input/expected, tôi tự nhập testcase.”
Workbook sẽ có cột dữ liệu tìm kiếm, step đọc kết quả và cột expected tương ứng.
Tên cụ thể do AI đề xuất; validator bắt buộc các tên khớp giữa sheet.

Hỗ trợ các action executor hiện có, gồm dropdown, wait và read_result. Assertion
được tạo khi người dùng yêu cầu; không tự suy diễn giá trị nghiệp vụ. Hiện gen
so sánh exact, group lặp vẫn trống; group result chỉ có expected cho block đầu,
cần mở rộng thủ công nếu có nhiều block. Các trường tùy chọn vẫn xuất đầy đủ.

Backend từ chối code, giá trị input literal, locator tự đoán và field ngoài schema.
Bản nháp chưa inspect website: locator `:not(*)` không khớp phần tử nào,
step `active=N`. Schema từ chối trường settings/testcases nếu model tự sinh.
Người dùng giữ cấu hình hiện có, thay locator, tự nhập dữ liệu và kiểm tra assertion trước
khi chạy. Runner resolve expected placeholder local, báo lỗi nếu thiếu biến.
Không tạo run hoặc tự mở browser khi bấm tạo nháp.

Mô tả giới hạn 6000 ký tự, tối đa 100 step, hai yêu cầu AI đồng thời mỗi API process;
không tự retry. Có chặn mẫu credential/URL thường gặp, nhưng không thể nhận diện
mọi secret trong văn bản tự do: việc rà soát trước khi gửi là bắt buộc. Reverse proxy
cần đặt quota/rate limit theo chính sách triển khai. Chưa gọi model GreenNode thật
trong kiểm chứng; test dùng MockTransport, không cần API key thật.

## Chuẩn bị config: settings có giải thích và duyệt từng mục

Không upload config gốc lên AI. Ghép nháp Describe/Record vào bản sao config local:

```powershell
python prepare_runner.py --template config/Existing.xlsx --draft config/Describe_Draft.xlsx --output config/Prepared.xlsx
```

File draft phải chỉ có header testcases; dữ liệu do người dùng nhập đặt ở config
template hoặc nhập sau khi chuẩn bị. Công cụ thay sheet steps bằng step nháp,
thêm cột testcase còn thiếu, giữ nguyên mọi dòng testcase đã có và sheet khác.
Không ghi đè file nguồn/output. Nếu source thay đổi trong lúc review, dừng để làm lại.

Settings mặc định giữ nguyên, không reset timeout/browser/selector. Chỉ khi flow
mới không khớp hàm executor, công cụ đưa đề xuất trước/sau kèm lý do:

- `screen_flow`: run_testcase/run_screen cần danh sách màn hình theo thứ tự.
- `login_screen`: chỉ đề xuất nếu step account ở màn hình khác cấu hình login.
- `result_screen`: chỉ đề xuất nếu read_result ở màn hình khác cấu hình kết quả.

Mỗi mục hỏi `[y/N]`; phải nhập `y` mới đổi trong bản sao. Từ chối giữ nguyên giá trị
cũ và ghi quyết định vào preparation_review. Không suy diễn thay đổi các setting
riêng của website. Với config đã khớp step, không có câu hỏi hoặc thay đổi settings.
Nếu chưa có config gốc, người dùng tự tạo settings; công cụ gen không tạo hộ.

Sau đó người dùng tự nhập testcase/expected và chọn dòng active. Kiểm tra tĩnh:

```powershell
python preflight_runner.py --config config/Prepared.xlsx
```

Preflight chỉ in số dòng/mã lỗi, không đọc `.env`, không resolve secret và không
mở browser. Mã thoát 1 nếu còn vấn đề như thiếu testcase active, locator nháp hoặc
screen không khớp settings; mã 0 chỉ là qua kiểm tra tĩnh, không phải PASS testcase.
Nháp thiếu settings vẫn dùng được với Inspector/Repair nhưng không gửi chạy trực tiếp.

## Inspector local: kiểm chứng locator trên màn hình hiện tại

Sau khi bổ sung locator trong workbook, chạy trên máy người dùng:

```powershell
python inspect_runner.py --config config/Describe_Draft.xlsx --output inspection.json
```

Chương trình mở browser mới, không load file môi trường, không dùng profile có sẵn.
Người dùng tự điều hướng và đăng nhập. Terminal liệt kê số màn hình theo sheet
steps; nhập `<số màn hình> <số tab>`, ví dụ `1 1`, để kiểm tra trang đang mở.
Chuyển màn hình thủ công rồi kiểm tra tiếp trong cùng browser. Tab được tính theo
thứ tự mở, không dựa trên tab đang focus. Nhập `q` để lưu report và đóng browser.

Inspector kiểm tra cả step inactive; không tự goto/click/fill/read input, sửa file
hay gửi dữ liệu ra server/AI. Locator thông thường dùng cùng builder với Runner;
read_result chỉ kiểm tra trực tiếp được css_input/css_disabled, không đọc giá trị.
Report gồm hash workbook, thời điểm, số màn hình/tab/dòng và số đếm/trạng thái.
Không chứa DOM, text/attribute từ trang, URL, locator hoặc giá trị nhập.

| Trạng thái | Ý nghĩa |
| --- | --- |
| UNIQUE_VISIBLE | Một phần tử khớp và đang hiển thị; chưa chứng minh đúng mục tiêu |
| NOT_FOUND | Không có phần tử khớp trong trang hiện tại |
| AMBIGUOUS | Có nhiều phần tử khớp |
| HIDDEN | Một phần tử khớp nhưng đang ẩn |
| UNRESOLVED | Locator trống hoặc vẫn là placeholder |
| MANUAL_REVIEW | Cần kiểm tra thủ công: wait, group, dropdown động, radio theo giá trị hoặc read method phức tạp |
| CHECK_ERROR | Không truy vấn được locator; report không ghi raw exception |

Kết quả chỉ đúng tại thời điểm kiểm tra, không phải PASS testcase hay xác nhận
phần tử có thể thao tác. Iframe/shadow DOM, business assertion và AI repair chưa
được kiểm chứng tự động. Một step có thể có nhiều check; UNIQUE_VISIBLE cho target
không xóa MANUAL_REVIEW cho wait/dropdown/group của step đó.

Không ghi đè report có sẵn. Đây là report xuất chủ động do người dùng giữ, không
phải artifact của run nên không có cleanup tự động. Tối đa 2000 dòng step và 100
snapshot mỗi phiên. Thoát bằng `q` để lưu; kill/Ctrl+C có thể mất report chưa xuất.
Browser thật cần người vận hành thử; test hiện dùng browser giả lập, không UAT.

## Repair local có xác nhận

Dùng số dòng Excel trong báo cáo Inspector (header là dòng 1):

```powershell
python repair_runner.py --config config/Describe_Draft.xlsx --row 2 --output config/Repaired_Draft.xlsx
```

Trong browser mới, tự đăng nhập và mở màn hình cần sửa. Rê chuột lên phần tử thay
thế rồi nhấn **Ctrl+Alt+L**. Picker chỉ dựng CSS theo tag/vị trí phần tử, không lấy
text, attribute hoặc input value. Terminal hiển thị dòng và locator mới; nhập
`EXPORT` để xác nhận, Enter để chọn lại hoặc `q` để hủy tại bước review.
Đóng browser để hủy khi chưa chọn được phần tử.

Trước khi xuất, công cụ kiểm tra phần tử còn duy nhất/hiển thị và đúng đối tượng
đã chọn. Nếu DOM thay đối tượng, phải chọn/xác nhận lại. Hash workbook được kiểm
tra để từ chối xuất từ một file đã bị thay đổi trong lúc review.

Bản sao giữ các sheet/dữ liệu, chỉ đổi `locator_type=css` và `locator` của dòng chọn,
đồng thời đặt **mọi step/testcase về active=N**. Sheet `repair_review` ghi hash nguồn,
dòng/cột sửa, locator mới và thời điểm. File gốc giữ nguyên; không ghi đè output.
Người dùng quản lý bản nháp này như workbook xuất từ Describe/Record.

Hỗ trợ target trực tiếp cho fill/click/check/select và một số biến thể, cùng
read_result_single với css_input/css_disabled. Group, radio theo giá trị, wait,
form_item, fill_sequence và read method phức tạp cần sửa thủ công. Kiểm tra tag
chỉ loại bỏ một số nhầm lẫn cơ bản, không chứng minh phần tử đúng nghiệp vụ hay
đủ điều kiện tương tác. Wait/dropdown/setting phụ vẫn cần kiểm tra riêng.

Đây là **repair theo lựa chọn của người dùng**, không phải AI discovery/repair.
Không gọi AI, gửi DOM/workbook lên server hoặc tự thực hiện step. CSS theo cấu trúc
có thể thay đổi khi giao diện đổi; chạy lại Inspector rồi rà soát trước khi bật.
Iframe/shadow DOM chưa hỗ trợ. Browser thật/hotkey cần người vận hành kiểm chứng;
test tự động hiện dùng browser giả lập.

## Kiểm tra không dùng secret

```powershell
python -B scripts/test_offline.py -x
```

Bộ kiểm tra dùng dữ liệu giả, chặn mạng và việc mở file secret, không chạy
PostgreSQL integration mặc định. Người vận hành tự chạy UAT và chỉ gửi số liệu/
output đã che dữ liệu nhạy cảm để đối chiếu.
