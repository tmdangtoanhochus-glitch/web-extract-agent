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
Có Inspector local, discovery cấu trúc và AI đề xuất locator với người dùng duyệt,
cùng picker repair local. Artifact chi tiết được giữ local theo quyết định kiến trúc.

Cloud nhận số đếm PASS/FAIL/ERROR/UNVERIFIED, thời gian và metadata preflight đóng schema.
Chỉ khi yêu cầu AI discovery/repair, cấu trúc đã rà soát được gửi riêng và không persist. Excel, log,
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

## Tạo admin khi deploy (Postgres)

Mặc định Runner dùng SQLite (`data/runner.db`) — phù hợp chạy local, nhưng khi deploy
container lên GreenNode (hoặc bất kỳ nền tảng nào khác), file SQLite trong container
là **ephemeral** (mất khi container restart) trừ khi bạn tự mount volume bền vững.
Dùng Postgres cho môi trường deploy thật để tránh mất dữ liệu user/run:

1. Chuẩn bị 1 Postgres server mà **cả 2 nơi** đều kết nối tới được: API đang chạy
   trên GreenNode, VÀ máy bạn (để chạy script bootstrap 1 lần). Khuyến nghị dùng
   database riêng cho Runner, tách khỏi database của crawl-agent (`DB_BACKEND=postgres`)
   dù bảng đã có tiền tố `runner_*` — tránh lẫn dữ liệu 2 module khi backup/restore.

2. Set biến môi trường khi deploy Runtime API trên GreenNode:
   ```env
   RUNNER_ENABLED=true
   RUNNER_DATABASE_URL=postgresql://user:pass@<host-postgres>:5432/runnerdb
   ```
   API tự `CREATE TABLE IF NOT EXISTS` cho cả 6 bảng (`runner_users`, `runner_sessions`,
   `runner_agents`, `runner_runs`, `runner_audit`, `runner_notifications`) ngay lần đầu
   kết nối — không cần chạy migration riêng.

3. Tạo admin đầu tiên — chạy **NGAY TRÊN MÁY BẠN** (không cần shell vào container
   GreenNode), trỏ đúng cùng Postgres:
   ```bash
   python scripts/create_runner_admin.py --username runneradmin --postgres-dsn "postgresql://user:pass@<host-postgres>:5432/runnerdb"
   ```
   Máy bạn cần kết nối mạng tới được Postgres đó (IP whitelist/VPN/bastion tuỳ hạ tầng
   GreenNode cấp — không nằm trong phạm vi repo này). Script chỉ chạy được khi database
   **chưa có user nào** — chạy 1 lần duy nhất lúc khởi tạo, không chạy lại.

4. Sau khi có admin đầu tiên, **không cần CLI nữa** — đăng nhập UI Runner bằng tài
   khoản vừa tạo, vào tab **Quản trị** để tự tạo thêm user/admin khác (`POST /users`)
   hoặc đặt lại mật khẩu cho user quên mật khẩu (`POST /users/{id}/reset-password` —
   không có luồng tự phục vụ qua email, admin đặt trực tiếp rồi tự báo lại cho user
   qua kênh khác).

## Vận hành và giới hạn

- UI container có `/health` kiểm tra nginx và `/ready` kiểm tra health Streamlit.
  Khi triển khai thử, kiểm tra cả hai và tương tác trang để xác minh WebSocket.
  `/ready` chưa thay thế kiểm tra API/DB/AI. Ghi kết quả trong RUNNER_UAT_RESULTS.md.
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
- Docker local được kiểm chứng theo từng ca tại RUNNER_UAT_RESULTS.md; cách tạo
  context source riêng và chạy smoke nằm trong RUNNER_CONTAINER_SMOKE.md.
  Chưa nghiệm thu GreenNode, PostgreSQL hoặc browser trên UAT thật.

## Record local và AI chuẩn hóa theo Runner (phase 26–27)

Luồng đã chốt: người dùng tự thao tác trong Inspector/Recorder; AI biên dịch bằng
chứng thành steps phù hợp executor. Không có chế độ AI tự điều hướng hoặc tự chạy
nghiệp vụ. Runner chỉ thực thi khi người dùng chủ động kích hoạt cấu hình và tạo run.

Để dùng AI chuẩn hóa, xuất thêm JSON cấu trúc:

```powershell
python record_runner.py --output config/Recorded_Draft.xlsx --events-output config/Recorded_Events.json
```

Trên UI Runner → Record local → **AI chuẩn hóa bản ghi theo Runner**, tải JSON,
mô tả ý nghĩa flow/sự kiện, rà nội dung rồi xác nhận gửi metadata cho AI. Backend
cần bật AI như Describe đang dùng; không cần thêm dependency hoặc file settings.
XLSX ghi thô vẫn giữ để đối chiếu. JSON tối đa 500 sự kiện; `dropped` khác 0 nghĩa
là bản ghi chưa đầy đủ, cần rà soát/ghi lại. Không upload JSON tự chứa giá trị nhập.

Compiler yêu cầu mọi sự kiện được bao phủ đúng một lần, đúng thứ tự và màn hình.
AI có thể gộp các fill liên tiếp trên cùng phần tử. Với Ant Design, chỉ khi có bằng
chứng ô nhập chỉnh sửa được và một popup đang hiển thị, click mở + các fill tùy chọn
+ click chọn mới được gộp thành `select_antd`, `dropdown_selector=visible`,
`match_type=exact`, `value_source=testcase`. Người dùng tự nhập giá trị lựa chọn.
Trường hợp khác giữ action đã chứng minh hoặc đánh dấu cần kiểm tra, không đoán
action/framework. Ant Design trong iframe/shadow chưa được gộp tự động vì hàm
Runner tìm popup ở page chính.

Sheet review ghi event ID nguồn và giải thích REVIEW_LOCATOR/REVIEW_REPEAT/
REVIEW_CUSTOM_CONTROL. Locator chưa chắc có thể để placeholder. Không tự suy luận
account, group, prefill, assertion hoặc wait chưa được ghi. Nhóm lặp cần xác định
locator theo chỉ số; compiler chưa tự chuyển nhiều lần nhập thành group.
Mọi step inactive, testcase chỉ header, không settings. Ghép bản đã chuẩn hóa bằng
prepare_runner.py rồi tự nhập testcase và chạy Inspector/preflight trước khi dùng.

Recorder hỗ trợ iframe lồng nhau và shadow DOM mở qua locator cấu trúc có scope;
không thu URL/tên frame. Checkbox/radio ghi check/uncheck; upload chỉ ghi action
và vị trí input, không đọc filename/nội dung file. Bạn tự nhập đường dẫn file ở
testcase; executor từ chối các đường dẫn credential đã biết hoặc symlink/junction.
Không ghi drag-and-drop, shadow DOM đóng hoặc suy luận nghiệp vụ từ text trang.

## Record local không dùng AI

Tạo sẵn thư mục config và chạy trên máy người dùng:

```powershell
python record_runner.py --output config/Recorded_Draft.xlsx
```

Browser mới không dùng profile đăng nhập có sẵn. Người dùng tự mở website và
thao tác; đóng các tab để xuất workbook. Recorder không đọc file môi trường,
giá trị input, text trang hoặc URL điều hướng. Ghi vị trí cấu trúc, loại thao tác
và enum capability của widget; không xuất chuỗi class/attribute. Hỗ trợ click,
fill, select, check/uncheck/upload trong iframe và shadow DOM mở.
Nút dạng input type button/submit/reset/image được ghi thành click; không thu
nhãn hoặc giá trị của nút. Các lần bấm riêng được giữ thành các bước riêng.
Gõ liên tiếp trong cùng ô được ghi thành một bước. Nếu xen giữa là thao tác ở
frame khác, pause/resume hoặc chuyển màn hình, lần nhập tiếp theo được ghi riêng.
Không tự gửi recording lên server. Chỉ JSON được người dùng rà và xác nhận trên UI
mới gửi cho AI. File output phải chưa tồn tại.

Workbook nháp có step `active=N`, sheet testcases chỉ chứa header; không có dòng
mẫu hoặc sheet settings. Ghép với config hiện có theo bước chuẩn bị bên dưới,
sau đó người dùng tự nhập testcase/role/input/expected. Không coi một flow chỉ
click/fill là testcase đã xác minh kết quả. Compose giữ mapping sự kiện và ghi chú
review của từng nháp; prepare chép chúng vào sheet draft_review mới, giữ ghi chú
và testcase có sẵn của người dùng.

### Phím tắt Record (phase 18)

- **Ctrl+Alt+N**: bắt đầu screen tiếp theo, trước thao tác đầu tiên trên màn hình
  mới. Screen đầu là `recorded`, tiếp theo `recorded_002`… (tối đa 100). Không tự
  lấy URL/route hoặc suy luận tên màn hình. Thứ tự được giữ trong workbook.
- **Ctrl+Alt+P**: tạm dừng/tiếp tục ghi toàn phiên, không đóng browser. Thao tác khi
  pause không được đưa vào draft. Pause không dừng thao tác do bạn thực hiện trên website.
- Rê chuột lên target rồi **Ctrl+Alt+W**: thêm step `wait` với CSS cấu trúc để chờ
  hiển thị khi chạy sau này. Trong lúc Record không gọi wait hay reload website.
- Rê chuột lên input/textarea/select rồi **Ctrl+Alt+A**: thêm `read_result_single`,
  `css_input`, `match_type=exact` và header `expected_*` trống. Không đọc giá trị.
  Không áp dụng password/file/checkbox/radio/hidden. Executor chỉ đọc kết quả ở
  một result screen, nên đánh dấu các read trên cùng màn hình cuối; read ở màn hình
  khác bị từ chối. Khi prepare, duyệt result_screen chỉ nếu cần đổi và có giải thích.

Góc browser hiện screen, paused/recording và accepted/not recorded. Chỉ dùng phím
tắt khi browser có focus; nếu OS hoặc website chặn hotkey, thao tác chưa được ghi.
Đóng mọi tab để xuất như trước. Step mới vẫn inactive; người dùng tự nhập expected.
Inspector kiểm tra count/visibility cho wait dạng CSS cấu trúc mà không thực thi wait.

Giới hạn: chưa ghi iframe/shadow DOM, upload, checkbox/radio, dropdown tùy biến,
navigation tự động hoặc assertion tự suy luận; tối đa 1000 event. CSS theo vị trí cần sửa khi layout
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
so sánh exact. Khi cần nhóm nhập lặp, nêu rõ trong mô tả; AI tạo group identifier
với fill/fill_enter/select/select_antd/force_select_antd dùng testcase và click
dùng empty. Nhóm phải liền mạch trên một screen, có ít nhất một field testcase.
Bạn tự sửa locator theo từng dòng (có thể dùng {i} như executor hỗ trợ) và tự nhập
danh sách giá trị phân cách bằng `;`; không có giá trị nào do generator tạo.
Placeholder local trong từng phần tử được resolve khi chạy, thiếu biến sẽ báo lỗi.

Chọn **Số khối kết quả cần cột expected** từ 1–100 trên UI. Với read_result_group,
Python tạo expected_<field>_0 đến expected_<field>_<n-1>; với read_result_single
vẫn chỉ có expected_<field>. Số này chỉ tạo header, không đổi settings hoặc số block
website mà executor đọc. Người dùng tự nhập từng expected. Compose và prepare giữ
đủ cột trống đã chọn; không tự sinh testcase. Các trường step tùy chọn vẫn đầy đủ.

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

Lệnh picker trên là **repair theo lựa chọn của người dùng**, không gọi AI.
Không gọi AI, gửi DOM/workbook lên server hoặc tự thực hiện step. CSS theo cấu trúc
có thể thay đổi khi giao diện đổi; chạy lại Inspector rồi rà soát trước khi bật.
Iframe/shadow DOM chưa hỗ trợ. Browser thật/hotkey cần người vận hành kiểm chứng;
test tự động hiện dùng browser giả lập.

## Kiểm tra không dùng secret

### Chẩn đoán journal chỉ đọc (phase 22)

Chạy tại máy agent, thay `<STATE_FOLDER>` bằng thư mục state đang sử dụng:

```powershell
python local_runner_agent.py --state <STATE_FOLDER> --journal-status
python local_runner_agent.py --state <STATE_FOLDER> --journal-status --run-id <RUN_ID>
```

Lấy Run ID từ lịch sử trên UI để kiểm tra riêng. Không cần token, API, workbook
hay file môi trường. Lệnh không tạo thư mục/lock, không sửa file, không gửi kết quả
và không chạy testcase. Không dùng đồng thời với `--resend-run`.

JSON chứa `status`, `counts`, `files` và `truncated`. Mỗi mục chỉ có mã phân loại,
`file_ref` từ hash rút gọn tên file và một số metadata trạng thái nếu hợp lệ;
không có nội dung, tên file thô hoặc đường dẫn. Hash này không bảo đảm ẩn danh.

| Mã | Ý nghĩa |
| --- | --- |
| VALID | Journal vượt qua validator; không kết luận testcase PASS |
| INVALID_JSON / INVALID_METADATA / INVALID_RESULT | Nội dung không đúng contract |
| IDENTITY_MISMATCH / INVALID_TIMESTAMP | ID hoặc mốc thời gian không hợp lệ |
| TOO_LARGE / UNREADABLE | Vượt 128 KB hoặc không đọc được |
| INTERRUPTED_WRITE | Có file ghi dở; không đọc nội dung pending |
| SYMLINK / SKIPPED_PROTECTED_NAME / UNSAFE_PATH | Đường dẫn bị loại, không đọc nội dung |

Status `OK` trả mã thoát 0; các status khác trả 2 để người vận hành kiểm tra.
`REVIEW_REQUIRED` có lỗi hoặc còn mục chưa quét; `STATE_UNAVAILABLE` là state chưa
có/không truy cập được; `RUN_NOT_FOUND` là không thấy run đã chọn. `UNSAFE_STATE`
hoặc `UNSAFE_RUN_REFERENCE` báo đường dẫn bị từ chối. Không diễn giải mã thoát 2
là testcase thất bại.

Quét tối đa 1.000 file journal/pending, không đệ quy. `truncated=true` nghĩa là
chưa kiểm tra hết, có thể chọn riêng run cần xem. Kết quả là snapshot không nguyên
tử: nếu agent đang ghi, hãy kiểm tra lại khi run kết thúc và agent đã dừng.
Không xóa journal/pending để ép chạy lại; xử lý theo hướng dẫn giữ bằng chứng dưới đây.

### Journal hỏng hoặc ghi dở (phase 21)

Agent giữ journal để tránh chạy testcase hai lần. Mỗi mục được kiểm tra kích thước
(128 KB), schema, run_id khớp tên file, timestamp và result metadata trước xử lý.
Nếu JSON hỏng, timestamp sai, file không đọc được hoặc còn `.pending` từ lần ghi
bị ngắt, agent bỏ qua mục đó và giữ nguyên file/artifact. Các mục hợp lệ vẫn tiếp tục.
Không tự sửa/xóa hoặc suy đoán kết quả từ journal lỗi.

Console báo mã giai đoạn `read`, `interrupted_write`, `result_write`, `recovery`
hoặc `retention`, mỗi loại một lần trong process; không in nội dung file/exception.
Journal tồn tại dù hỏng, hoặc chỉ còn `.pending`, vẫn chặn thực thi lại cùng run ID.
Lệnh --resend-run cũng từ chối journal chưa đủ bằng chứng là kết quả đã hoàn tất.

Khi gặp cảnh báo, người vận hành chờ run hiện tại kết thúc rồi dừng agent, sao lưu
thư mục state và kiểm tra file tại máy local. Đối chiếu summary local và tác động
website trước quyết định phục hồi từ bản sao lưu đã xác minh. Không xóa journal/
pending để ép chạy lại, không gửi nội dung file cho trợ lý. Nếu chỉ mất quyền ghi
hoặc ổ đĩa đầy, khắc phục tại local trước; pending còn lại vẫn cần kiểm tra riêng.
Artifact của mục bị bỏ qua có thể tồn tại quá hạn vì cleanup ưu tiên giữ bằng chứng.

Ghi mới tạo `.pending` bằng exclusive create, flush/fsync rồi atomic replace;
không ghi đè file dở. Đây không phải bảo đảm chống mọi dạng lỗi ổ đĩa/mất điện;
giữ backup phù hợp. Cơ chế không thay thế xác nhận nghiệp vụ sau sự cố.

### Kết quả đến muộn khi mất kết nối (phase 20)

Sau quá hạn heartbeat, backend giữ trạng thái LOST vì không biết local đã thực
hiện những gì. Nếu agent gửi kết quả sau đó, API lưu `late_result` đầu tiên và
UI hiển thị riêng **kết quả agent báo** cùng thời điểm nhận. Không chuyển LOST
thành PASSED/FAILED, không tạo run khác hoặc chạy lại testcase. Report preflight
bị chặn vẫn buộc kết quả agent thành ERROR dù counts có passed.

Hạn artifact/notification giữ nguyên. Metadata vẫn có thể nhận sau khi artifact
đã hết hạn, nhưng file summary/artifact đã xóa không được tạo lại. Kết quả chỉ nhận
từ đúng agent đã claim run; run chưa được claim không có kết quả muộn hợp lệ.
Gửi trùng giữ kết quả đầu tiên, không nhân audit hoặc sửa mốc thời gian.

Agent đang PENDING_RESULT sẽ gửi lại bình thường. Với journal đã REPORTED do API
cũ ACK nhưng bỏ qua kết quả LOST, nâng API/UI trước rồi chủ động gửi lại metadata:

```powershell
python local_runner_agent.py --api <API_URL> --state <STATE_FOLDER> --resend-run <RUN_ID>
```

Chờ không còn run local đang chạy, dừng vòng polling rồi dùng đúng state/token của
agent cũ. Single-instance lock ngăn chạy song song với agent đang hoạt động. Lệnh
chỉ validate và gửi metrics/preflight từ journal có sẵn, không đọc workbook/env
để thực thi, không recover/cleanup/claim job. Không chỉnh journal thủ công. Nếu
agent bị thu hồi hoặc journal không còn result thì không thể gửi bằng lệnh này;
không tạo run mới để bù khi chưa kiểm tra tác động trên website. Sau gửi, khởi động
lại agent bình thường và bấm Làm mới lịch sử trên UI.

### Chạy thử đúng một step local (phase 19)

Inspector chỉ kiểm tra locator. Khi cần thực hiện một thao tác thật để thử step,
chạy trên môi trường test được phép:

```powershell
python try_step_runner.py --config config/Prepared.xlsx --row 2 --output trial.json
```

Tự mở website/đăng nhập trong browser mới, nhập số tab. Công cụ highlight phần tử
khớp duy nhất, đang hiển thị. Fill/select hỏi giá trị thử qua đầu vào ẩn (nếu không
ẩn được thì dừng); không tự lấy giá trị từ testcase/account hay file credential.
Sau khi xác minh target và tác động của thao tác, gõ `EXECUTE 2` để thực hiện dòng 2
một lần. Chuỗi khác hủy. Source hash và element identity được kiểm tra lại sau xác nhận.

Hỗ trợ action đơn giản fill, click, check, select và wait selector CSS cấu trúc.
Thực thi trên ElementHandle đã review, dùng cùng thao tác Playwright với handler
trực tiếp của Runner. Timeout mỗi thao tác 10 giây. Không force, không prefill check,
không group hoặc post-action wait command; các trường hợp đó dùng Runner đầy đủ.
Wait ở đây chỉ dành cho target đã có và đang hiển thị khi review, không thử flow
chờ phần tử chưa xuất hiện. Công cụ không thực hiện assertion hay đọc actual value.

Step inactive vẫn có thể được người dùng chủ động thử bằng xác nhận này; workbook
không thay đổi và không tự activate. Đây là thử hành vi một phần tử, không chạy testcase,
không kết luận đúng nghiệp vụ hoặc thay kết quả run trên cloud.

| Trạng thái report | Ý nghĩa |
| --- | --- |
| PREPARING | Đã tạo report, chưa ghi nhận ý định thực thi |
| CANCELLED | Người dùng hủy/không nhập giá trị thử/chưa bắt đầu thực thi |
| TARGET_UNAVAILABLE / TARGET_CHANGED | Target không unique/visible hoặc đã đổi sau review; chưa thực thi |
| WORKBOOK_CHANGED | Source đổi sau review; chưa thực thi |
| PREPARATION_ERROR | Lỗi chuẩn bị, chưa bắt đầu action |
| EXECUTION_STARTED | Đã persist ý định chạy; nếu tiến trình chết, kết quả chưa xác định |
| ACTION_COMPLETED | Lời gọi thao tác hoàn tất; không phải testcase PASS |
| OUTCOME_UNKNOWN | Có thể side effect đã xảy ra; kiểm tra website trước mọi lần thử khác |

Report chỉ có hash workbook, dòng, action, thời điểm, attempts và status. Không có
input/expected, selector, URL, DOM hoặc exception message. Công cụ không upload hoặc
retry. Report xuất chủ động do người dùng quản lý; không tự retention như artifact run.
Không dùng lại output đã tồn tại. Dù report bị mất, chương trình không có queue/replay;
một lần thử mới luôn cần xác nhận người dùng. Browser thật vẫn cần nghiệm thu riêng.

### Discovery và AI repair có người duyệt (phase 13–14)

1. Chạy `python discover_runner.py --output discovery.json` tại máy truy cập được UAT.
2. Tự mở website và đăng nhập trong browser mới; nhập số tab trong terminal.
3. Nhập candidate ID (`c1`, `c2`…) để highlight phần tử. Chỉ rõ chức năng của từng
   ID bằng mô tả của chính bạn; công cụ không lấy label/text để tự suy luận.
4. Nhập `EXPORT`. Nếu cấu trúc đổi trong lúc rà soát thì chụp lại. File gồm CSS
   cấu trúc và loại phần tử; không có URL, input value, attribute hay text trang.
5. UI **Runner → Inspector local → AI hỗ trợ chọn locator**: chọn JSON, rà soát
   bảng cấu trúc, nhập mô tả có ID, xác nhận gửi cho AI. Ví dụ “Điền account vào c1,
   c2 rồi click c3; c1 là username, c2 là password”. Dùng chức năng này khi admin
   đã bật RUNNER_AI_ENABLED; không cần cấu hình AI ở máy người dùng.
6. Chọn tạo steps hoặc sửa một locator. Tạo steps xuất đủ cột inactive và header
   testcases; không có settings hoặc testcase. Mỗi snapshot cho một màn hình.
   Với nhiều màn hình, tạo nháp riêng, nêu rõ tên screen và tên step khác nhau
   trong mô tả, ghép như dưới đây rồi chuẩn bị config. Không ghép một màn hình
   xuất hiện xen kẽ vì executor nhóm step theo screen.
7. Khi sửa locator, chọn đúng action/read_method của dòng cần sửa, tải proposal rồi:

```powershell
python repair_runner.py --config config/Existing.xlsx --row 2 --snapshot discovery.json --proposal Repair_Proposal.json --output config/Repaired_Draft.xlsx
```

Tự mở lại đúng màn hình, chọn tab, xem phần tử được highlight và nhập EXPORT nếu
đúng mục tiêu. Công cụ không chạy click/fill/testcase. Hash proposal phải khớp
snapshot; action/read_method phải khớp dòng. Sau xác nhận, kiểm tra lại element
identity/visibility/uniqueness và hash workbook trước khi xuất bản sao inactive.
File gốc, dữ liệu testcase và settings giữ nguyên. Có thể hủy bằng q.

AI không được trả code, locator mới, testcase/settings hoặc chọn ID bạn chưa nêu.
Không có labels nên AI không chứng minh được đúng ngữ nghĩa; bạn phải kiểm tra target.
CSS theo vị trí có thể lệch khi layout đổi. Không nhận raw DOM, screenshot hay log
để repair; không tự chạy lại run thất bại. Iframe/shadow DOM, repeat group, radio theo
giá trị và read method phức tạp cần cấu hình thủ công. Snapshot tối đa 100 phần tử
hiển thị, chỉ tag HTML chuẩn; phần tử khác dùng picker local.

Snapshot/proposal là file người dùng chủ động xuất, do người dùng quản lý, không
phải artifact run. UI có nút xóa snapshot/đề xuất khỏi phiên, đổi snapshot không hiện
đề xuất cũ, logout xóa đề xuất. API chỉ audit loại sự kiện và user, trả no-store.

### Ghép flow nhiều màn hình (phase 15)

```powershell
python compose_runner.py --draft config/Login_Draft.xlsx --draft config/Search_Draft.xlsx --output config/Flow_Draft.xlsx
python prepare_runner.py --template config/Existing.xlsx --draft config/Flow_Draft.xlsx --output config/Prepared.xlsx
python preflight_runner.py --config config/Prepared.xlsx
```

Thứ tự --draft là thứ tự thực hiện. Chỉ nhận file nháp có steps inactive và header
testcases; file đã chứa testcase/settings bị từ chối để tránh làm mất dữ liệu.
Tối đa 20 nháp/2000 steps. Tên step phải khác nhau trên toàn flow, screen liền mạch,
chỉ một màn hình đọc kết quả theo executor hiện có; xung đột cột input/expected bị chặn.
Không đổi tên hoặc sắp xếp lại tự động. Settings chỉ được đề xuất ở prepare và
người dùng duyệt riêng từng mục. Sau ghép vẫn cần tự nhập testcase và activate.

Trạng thái nghiệm thu và thứ tự triển khai: [RUNNER_ACCEPTANCE.md](RUNNER_ACCEPTANCE.md).

### Preflight tự động khi chạy qua agent (phase 12)

Executor mới tự kiểm tra workbook trước khi mở browser hoặc resolve môi trường.
Lỗi cấu trúc, chưa nhập/bật testcase, locator nháp, action/locator_type/value_source
không hợp lệ hoặc màn hình không khớp flow sẽ chặn run với trạng thái ERROR.
Không tự sửa workbook; file gốc giữ nguyên. Executor CLI trả mã 2 nếu preflight chặn.

Tại UI **Runner → Lịch sử**, xem khối preflight để biết sheet, dòng Excel (header
là dòng 1) và mã lỗi. Một số mã thường gặp:

| Mã | Việc người dùng cần kiểm tra |
| --- | --- |
| INVALID_WORKBOOK | File Excel, sheet bắt buộc, formula/external link và credential literal |
| MISSING_SETTINGS_USE_PREPARE | Ghép nháp với template bằng prepare_runner.py |
| ENTER_AND_ACTIVATE_USER_TESTCASES | Tự nhập testcase và chọn active=Y cho testcase muốn chạy |
| NO_ACTIVE_STEPS | Rà soát rồi tự chọn step active=Y |
| UNRESOLVED_LOCATOR / UNRESOLVED_WAIT | Dùng Inspector/repair hoặc chỉnh locator local |
| SCREEN_NOT_IN_FLOW / RESULT_SCREEN_MISMATCH | Đối chiếu steps với settings; chỉ sửa settings khi cần và tự duyệt |
| INVALID_ACTION / INVALID_LOCATOR_TYPE / INVALID_VALUE_SOURCE | Đối chiếu tên được executor hỗ trợ |
| INVALID_REPEAT_GROUP | Nhóm lặp cần field testcase và chỉ các action được run_repeat_group hỗ trợ; không dùng account/wait/read/force_fill |
| NO_ACTIVE_ASSERTIONS | Cảnh báo: có thể chạy nhưng không đủ bằng chứng để kết luận testcase PASSED |

`runs/<run_id>/preflight.json` và summary local có báo cáo; được dọn cùng artifact
theo retention hiện tại. Cloud chỉ nhận metadata theo schema đóng: status, số lượng
active, code, sheet, row và truncated. Không gửi URL, selector, tc_id, input/expected,
DOM hoặc exception message trong report này. UI tối đa 100 lỗi/100 cảnh báo; chạy
`preflight_runner.py` local nếu cần xem toàn bộ metadata.

Preflight không kiểm tra secret, đăng nhập, selector trên DOM thật hay hành vi UAT.
Chỉ coi đây là điều kiện trước chạy; kết quả testcase vẫn do executor xác định.
Luồng gọi trực tiếp `docs/runner.py` vẫn dùng validator nội bộ của runner; gate mới
áp dụng `runner_agent.executor` mà agent khởi chạy, không thay CLI runner độc lập.

**Thứ tự cập nhật:** nâng API trước, sau đó cập nhật/khởi động lại agent local.
Agent cũ vẫn gửi được summary số liệu nhưng không có metadata preflight. Agent mới
gửi thêm metadata; API cũ từ chối contract này và journal sẽ chờ gửi lại, không chạy
lại testcase. Không cần thay đổi setting workbook hoặc file credential.

```powershell
python -B scripts/test_offline.py -x
```

Bộ kiểm tra dùng dữ liệu giả, chặn mạng và việc mở file secret, không chạy
PostgreSQL integration mặc định. Người vận hành tự chạy UAT và chỉ gửi số liệu/
output đã che dữ liệu nhạy cảm để đối chiếu.
