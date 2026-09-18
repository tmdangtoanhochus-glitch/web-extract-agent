# Thiết kế tích hợp Runner local với UI/GreenNode

## Trạng thái triển khai và quyết định bổ sung (cập nhật 2026-09-17)

### Phase 26–27: Inspector/Recorder do người dùng thao tác, AI biên dịch cấu hình

Yêu cầu đã làm rõ: không phát triển AI tự điều hướng hoặc self-healing tự thực thi
nghiệp vụ. Người dùng thao tác local, AI nhận recording cấu trúc đã rà soát và biên
dịch thành workbook phù hợp Runner. Quyết định này thay phạm vi autonomous nêu
trong roadmap đích cũ bên dưới; Runner execution vẫn deterministic theo cấu hình.

Recorder xuất JSON tùy chọn (tối đa 500 events), schema đóng với action, screen,
structural locator, enum widget và related locator. Không thu DOM text, URL, input,
filename hay nội dung file. Metadata widget chỉ phản ánh capability đã nhận diện,
không xuất giá trị attribute. Iframe/shadow mở dùng scope; shadow đóng không hỗ trợ.
Các lần gõ liên tiếp cùng locator/screen được gộp tại bộ nhận sự kiện local dùng
chung cho các frame, không gộp riêng trong từng document. Thao tác xen giữa ở frame
khác, pause/resume hoặc chuyển screen kết thúc chuỗi gõ; lần nhập sau vẫn được ghi.
Giới hạn 500 tính trên các sự kiện sau khi gộp, JSON và workbook thô cùng thứ tự.

Endpoint /runner/authoring/recording yêu cầu Runner login và xác nhận rà soát.
AI chỉ đề xuất tên/action và nhóm event; compiler ràng buộc tất cả event đúng thứ
tự, không bỏ click, tự thêm thao tác hoặc tự sinh testcase/settings. Native select
giữ select; Ant Design đủ bằng chứng được gộp select_antd với input ở DOM chính.
Read/wait cần event rõ ràng. Account, repeat group và control chưa đủ bằng chứng
cần rà soát, không đoán. Workbook ghi mapping nguồn/cảnh báo trong review; active=N.
Không persist recording ở backend. UI bỏ draft/xác nhận cũ khi thay đầu vào/logout.

### Phase 23–25: chốt phạm vi và nghiệm thu

docs/RUNNER_ROADMAP.md đối chiếu MVP gốc với các phase triển khai và là bảng
theo dõi phần còn lại. Phase 23 hoàn tất tài liệu; phase 24 kiểm chứng triển khai,
phase 25 UAT/sửa lỗi/bàn giao. Hai phase cuối cần bằng chứng môi trường thật.
Không mở rộng sang autonomous self-healing, PostgreSQL hoặc multi-worker trong
phạm vi chốt MVP hiện tại. Kết quả ghi tại docs/RUNNER_UAT_RESULTS.md.
UI giữ /health làm liveness nginx; bổ sung /ready proxy health Streamlit để
phân biệt process proxy còn sống với UI sẵn sàng. Docker UI local đã xác minh
ready 200 khi Streamlit chạy, 502 khi chỉ nginx chạy. Build dùng context source
riêng, không copy workspace/state/credential, có manifest SHA-256; xem
docs/RUNNER_CONTAINER_SMOKE.md. Kết quả API/persistence/browser ghi riêng theo ca,
không suy ra GreenNode hoặc UAT đã đạt từ kết quả local.

Phase 25 đã có diễn tập restart offline: lifecycle FastAPI đầy đủ, SQLite tạm
đóng/mở lại, kiểm tra crawl/dedup, Runner summary/ownership và báo lỗi đã lọc.
Docker API tạm để lại theo yêu cầu người dùng sau gián đoạn engine. Bằng chứng
offline không thay đổi các điều kiện nghiệm thu môi trường thật trong roadmap.

### Phase 22: chẩn đoán journal không có side effect

CLI `--journal-status` chạy độc lập với token, API và vòng polling. Dùng cùng
validator với agent, chỉ trả mã lỗi và metadata trạng thái theo whitelist;
không in nội dung/tên file/đường dẫn. Reference là hash rút gọn của tên file,
không phải cam kết ẩn danh. Có thể chọn run ID để đối chiếu lịch sử trên UI.
Quét tối đa 1.000 mục, không đệ quy; báo truncated nếu còn mục chưa kiểm tra.
Không đọc nội dung pending, tên file credential hoặc đường dẫn liên kết.
Không tạo state/lock, sửa journal, gửi kết quả hay chạy testcase. Snapshot
không nguyên tử khi agent đang hoạt động; chẩn đoán không tự phục hồi hoặc
suy luận tác động nghiệp vụ. Chính sách giữ bằng chứng của phase 21 giữ nguyên.

### Phase 21: journal fail-closed theo từng run

Journal local kiểm tra schema/state/identity/timestamp/result trước recovery,
resend hoặc retention. Mục hỏng hay chưa ghi xong không được dùng để suy luận
kết quả, chạy lại hoặc xóa artifact; giữ nguyên bằng chứng, chỉ bỏ qua mục đó.
Các mục hợp lệ vẫn tiến triển. Console chỉ mã giai đoạn, không raw payload/error.
Write dùng .pending exclusive + flush/fsync + atomic replace. Pending có sẵn không
bị ghi đè và chặn thực thi lại cùng run ID; orphan pending cũng giữ nguyên.
Retention có thể kéo dài với mục lỗi cho tới khi người vận hành kiểm tra local;
không tự quarantine/delete hoặc replay để làm sạch trạng thái.

### Phase 20: giữ kết quả muộn nhưng không sửa lịch sử LOST

LOST không đồng nghĩa executor chưa chạy. Với run đã được claim, API nhận result
đến muộn vào late_result (metrics/status/preflight theo contract cũ, received_at).
Giữ nguyên status LOST, finished_at của lần mất theo dõi và toàn bộ retention.
Chỉ nhận lần đầu, audit riêng, owner/agent authorization như kết quả thông thường.
Summary/UI hiển thị riêng kết quả muộn. Không tạo lại artifact đã xóa hoặc replay.
Agent CLI có --resend-run để chủ động gửi lại journal đã được API cũ ACK; không
recover/claim/execution, single-instance lock và schema giới hạn vẫn áp dụng.

### Phase 19: thử một step tách biệt với Inspector và run testcase

try_step_runner.py là công cụ local do người dùng chủ động chạy, không nhận command
từ AI/cloud. Chọn một dòng, tự điều hướng, review highlight rồi xác nhận EXECUTE <row>.
Dùng locator builder hiện tại và thao tác Playwright trực tiếp trên ElementHandle
đã review sau kiểm tra identity/source hash. Chỉ hỗ trợ fill/click/check/select/wait
đơn giản, không dùng setting/env/testcase để tự resolve giá trị. Giá trị thử nhập ẩn,
không persist hoặc gửi cloud. Workbook giữ nguyên kể cả active.

Report metadata local persist ý định EXECUTION_STARTED trước side effect; hoàn tất
chỉ là ACTION_COMPLETED, không phải PASSED. Lỗi sau khi bắt đầu là OUTCOME_UNKNOWN;
không auto retry/replay. Mỗi lần thử là process/phiên browser mới và xác nhận riêng.
Report không thuộc artifact run hay cloud retention. Luồng này bổ sung bước thử có
người duyệt trong thiết kế đích, không biến Inspector thành executor hoặc cho phép
AI tự thao tác UAT. Action phức tạp vẫn thực hiện bằng executor đầy đủ.

### Phase 18: Record nhiều màn hình và đánh dấu wait/read

Recorder giữ state pause/screen tại process local, dùng phím tắt Ctrl+Alt+P/N.
Control chỉ có enum, không nhận screen name/URL/value từ website. Người dùng chủ
động đánh dấu screen mới trước thao tác tiếp theo; tối đa 100 màn hình/1000 step.
Phím Ctrl+Alt+W ghi wait cho phần tử trỏ tới; Ctrl+Alt+A ghi read_result_single
css_input/exact cho input/textarea/select thông thường, thêm expected header trống.
Không lấy actual/expected hoặc tự chạy assertion; không nhận read từ màn hình thứ
hai do giới hạn RESULT_SCREEN của executor. Password/file/checkbox/radio/hidden
không dùng hotkey read. Steps inactive, testcase vẫn chỉ có header, không settings.
Inspector kiểm tra locator wait cấu trúc theo count/visibility, không thực thi
lệnh wait/reload. Navigation, iframe/shadow DOM và assertion tự suy luận chưa có.

### Phase 13–14: discovery và repair có người duyệt

Quyết định này cụ thể hóa flow AI + Inspector ở mục 5–7: dùng Playwright local
qua adapter giới hạn, không đưa raw DOM/accessibility text cho MCP/AI trên cloud.
Người dùng tự điều hướng và đăng nhập; discover_runner.py chụp cấu trúc một màn hình,
chỉ gồm candidate ID, tag chuẩn và CSS nth-of-type. Không có URL, text, attribute,
input value, credential hoặc screenshot. Tối đa 100 candidate, có cờ truncated.
Người dùng highlight theo ID, kiểm tra rồi EXPORT; cấu trúc đổi trước xuất thì chụp lại.

UI nhận snapshot đã rà soát và mô tả có ID cụ thể. API đóng schema, xác thực Runner,
AI opt-in, không persist snapshot/mô tả/response. AI chỉ chọn ID có trong mô tả và
snapshot; Python kiểm tra action/tag và tham chiếu. Discovery xuất steps inactive
và header testcases; testcase/settings vẫn do người dùng quản lý. Một snapshot
không dùng để suy ra locator cho màn hình khác. Không tự khám phá nội dung nghiệp vụ.

Repair AI trả ID/reason enum; Python gắn hash snapshot và action/read_method.
Không nhận workbook/log/DOM/ảnh của run lỗi. CLI local đối chiếu proposal, yêu cầu
người dùng mở đúng màn hình, highlight và xác nhận EXPORT; kiểm tra lại identity,
visibility, uniqueness và hash nguồn. Bản sao giữ dữ liệu/settings, chỉ thay locator
và đặt mọi step/testcase inactive. Không tự replay UAT. CSS vị trí có thể trỏ nhầm
sau thay đổi layout dù vẫn unique; người dùng phải xác minh target khi highlight.

Đã có AI discovery/repair theo phạm vi có người duyệt này. Autonomous navigation,
iframe/shadow DOM, raw DOM MCP và tự sửa/chạy lại testcase chưa được triển khai.
Các action phức tạp vẫn dùng cấu hình thủ công theo executor hiện có.

Phase 15 thêm compose_runner.py để ghép nháp nhiều màn hình theo thứ tự người dùng
chọn, tối đa 20 nháp/2000 steps. Không nhận draft chứa testcase/settings, từ chối
tên step trùng, màn hình xen kẽ và nhiều màn hình kết quả. Sau ghép dùng prepare_runner.py
để giữ config/testcase hiện có; không tự đổi setting hoặc activate. Phase 16 bổ sung
ma trận nghiệm thu tại docs/RUNNER_ACCEPTANCE.md; test offline hoàn tất nhưng chưa
nghiệm thu browser/AI/GreenNode/PostgreSQL thật. Không coi đây là hoàn tất triển khai
vận hành hoặc mọi khả năng mở rộng trong thiết kế đích.

Phase 17 bổ sung gen nhóm nhập lặp theo dispatcher run_repeat_group (các action
fill/fill_enter/select/select_antd/force_select_antd dùng testcase và click dùng empty).
Group liền mạch trên một screen, có ít nhất một field testcase; không chứa dữ liệu
hoặc account. Người dùng tự nhập danh sách `;` và kiểm tra locator theo chỉ số.
Describe UI cho chọn 1–100 khối kết quả để Python tạo đủ header expected nhóm;
không để AI quyết định số khối chạy hoặc thay setting. Compose/prepare giữ các cột
trống, preflight chặn nhóm action/value_source không tương thích. Runtime resolve
placeholder local riêng từng phần tử danh sách, không đưa giá trị đó lên cloud.

### Bổ sung ranh giới crawler và Runner — phase 8

- Crawler và gửi báo lỗi vẫn công khai, không dùng session/token Runner. Admin debug
  giữ Basic Auth riêng. Cookie nguồn nhập tại Bước 3 chỉ dùng cho đợt crawl đó,
  không lưu DB và không dùng cookie chung của admin; lịch nguồn cần cookie chưa hỗ trợ.
- Crawler có pipeline bulk lịch sử/bảng riêng; scheduler crawler gọi lại pipeline đó,
  lưu cấu hình trong `scheduled_jobs.crawl_options`. Không đưa thao tác crawl sang
  local Runner, không thay đổi workbook/testcase/settings hay auth của Runner.
- Báo lỗi UI nối với audit crawl qua request ID; AI debug chỉ nhận metadata đã giới hạn,
  admin chủ động yêu cầu chẩn đoán. Không tự sửa code hoặc dùng dữ liệu này để gen testcase.
- Chi tiết và giới hạn triển khai: `docs/CRAWL_SUPPORT.md` (một worker, bulk đồng bộ,
  bảng HTML tĩnh, lịch khoảng ngày UTC; chưa kiểm chứng dịch vụ thật).

### Bổ sung phase 9: preview/retry crawler

- Preview crawler chỉ lập kế hoạch và lấy mẫu trang bảng đầu, không gọi AI hoặc
  tạo dataset/record. Mẫu chỉ trả về UI, không lưu trong audit/đưa vào AI debug.
- Retry chọn lọc chỉ dành cho bảng DB và do người dùng yêu cầu. Fingerprint cấu
  hình và kết quả audit xác định số lượt cần chạy lại; giữ cùng dataset và dedup.
  Không áp dụng retry này cho local Runner hoặc testcase UAT. Quy tắc không replay
  Runner sau mất heartbeat vẫn giữ nguyên.
- Cookie không nằm trong fingerprint hay snapshot cấu hình; phải nhập lại cho
  retry. Không bổ sung settings, gen testcase, gửi DOM hay thay đổi auth Runner.

### Runner

Phase 11 bổ sung điều khiển lịch crawler và queue RAM cho bulk, tách biệt hoàn toàn
khỏi job/agent Runner. Pause/cancel cooperative giữa các lượt; queue/control/cookie
không persist và không replay sau restart. Giữ deployment một process; hai worker
thread crawler không phải local Runner. Quy tắc không tự chạy lại testcase UAT và
không gen testcase/settings vẫn giữ nguyên. Chi tiết giới hạn tại `docs/CRAWL_SUPPORT.md`.

Phase 10 bổ sung CSV toàn bộ dataset crawler qua endpoint streaming và keyset
pagination, với lọc ngày UTC. Không thay đổi artifact Runner, quyền truy cập
Runner hoặc retention của run; CSV chuẩn bị trên UI do người dùng chủ động xóa
khỏi phiên, backend không tạo file artifact. Chi tiết tại `docs/CRAWL_SUPPORT.md`.

Phần dưới là thiết kế đích. Bản tích hợp hiện tại hoàn thành nền tảng chạy
workbook qua agent local và UI; chưa hoàn thành toàn bộ thiết kế đích.

**Phạm vi gen chốt theo người dùng:** chỉ sinh sheet steps và cột template của
testcases. Không sinh dòng testcase, dữ liệu hoặc expected value. Settings không
được sinh lại; chỉ đề xuất thay đổi khi hàm executor cần, giải thích lý do và hỏi
người dùng từng mục, mặc định giữ nguyên. Quyết định này thay thế phần gen toàn bộ
settings/testcase của phase 6c. Đăng nhập Runner chỉ áp dụng cho Runner; crawl công
khai không cần đăng nhập. Panel quản trị crawler nhạy cảm giữ cơ chế bảo vệ riêng.

- Tái sử dụng `docs/runner.py` mới qua `execute_config`; không phụ thuộc các
  module `core_*` của runner cũ. Process riêng cho mỗi run, agent polling HTTP.
- Runner được bật bằng `RUNNER_ENABLED`, mặc định tắt; metadata nằm trong
  các bảng `runner_*` riêng, SQLite mặc định. Không dùng scheduler crawler để
  thực thi Playwright. Retention có scheduler riêng.
- User/admin dùng password hash Argon2 và session opaque có hạn sử dụng;
  agent có token riêng, database chỉ lưu hash token. API ở prefix `/runner`.
- **Điều chỉnh phạm vi artifact:** cloud nhận summary số liệu và metadata preflight
  giới hạn theo schema đóng (phase 12: mã lỗi, sheet, dòng, số lượng active). Excel, log,
  screenshot nằm local; upload/download artifact chi tiết trên cloud chưa triển
  khai. Masking là biện pháp giảm lộ dữ liệu, không bảo đảm loại bỏ mọi thông tin
  nhạy cảm. Không gửi DOM/artifact cho AI trong bản hiện tại.
- Local config reference là mặc định. Hybrid upload chỉ dành cho workbook đã
  loại bỏ secret, kiểm tra định dạng/formula/ô nhạy cảm và xóa bản tạm theo run.
- Không tự chạy lại testcase sau mất heartbeat hoặc agent chết vì thao tác UAT
  có thể đã xảy ra. Journal cho phép gửi lại kết quả, không replay thao tác.
- Retention 7 ngày, thông báo trước xóa ít nhất 24 giờ, lưu audit; khi offline
  hoặc thông báo muộn, hạn xóa được kéo dài để giữ đủ thời gian cảnh báo.
- Record local bản đầu đã có CLI `record_runner.py` và hướng dẫn trong UI;
  chỉ capture click/fill/select bằng CSS cấu trúc, không lấy input value, text,
  attribute hoặc navigation URL. Export step inactive và header testcases, không có dữ liệu mẫu
  local, không gửi recording lên cloud. Giới hạn 1000 event, chưa hỗ trợ iframe,
  shadow DOM, upload, checkbox/radio hoặc assertion tự động. Đây là một phần
  Record Mode, chưa phải toàn bộ recorder/inspector ở mục 5–7. Phase 18 bổ sung
  chia screen/pause thủ công và đánh dấu wait/read bằng phím tắt như mô tả trên.
- Describe bản đầu đã có: `/runner/authoring/describe` yêu cầu đăng nhập và xác
  nhận nội dung không nhạy cảm, dùng GreenNode chat theo cấu hình runtime hiện có.
  `RUNNER_AI_ENABLED` mặc định false. AI chỉ trả steps theo schema đóng;
  Python suy ra header testcases (metadata, input, expected), tuyệt đối không tạo dòng dữ liệu.
  Có đủ 13 cột step, locator `:not(*)` và active=N; không có sheet settings tự sinh.
  `prepare_runner.py` ghép local với config có sẵn, giữ testcase người dùng nhập,
  chỉ thêm cột trống. Settings giữ nguyên trừ khi người dùng duyệt từng đề xuất có
  giải thích từ run_screen/read_and_verify; hiện chỉ đề xuất screen_flow/login_screen/result_screen.
  `preflight_runner.py` kiểm tra tĩnh sau khi người dùng nhập dữ liệu, không đọc secret.
  Phase 12 nối kiểm tra tĩnh vào executor local trước import runner/browser và resolve
  môi trường. Run bị chặn trả ERROR; UI hiện metadata whitelist, không nhận giá trị
  testcase/settings/URL/selector. Không tự sửa config. Preflight pass không bảo đảm
  locator, đăng nhập hoặc hành vi đúng. Contract Result mới là tùy chọn để nhận agent
  cũ; triển khai API trước agent. Direct CLI docs/runner.py giữ validator riêng.
  Runner đã hỗ trợ resolve expected placeholder trước so sánh; thiếu biến báo lỗi.
  Gen tối đa 100 step, assertion exact khi được yêu cầu; expected người dùng tự nhập.
  Phase 17 có repeat group và header expected nhiều result block theo số người dùng chọn.
  Không tự truy cập website, tạo run hoặc sửa testcase đang chạy. Không lưu mô tả,
  phản hồi model hoặc workbook trên server; audit chỉ ghi event và user.
- Đây là phần lập nháp của Describe, chưa phải flow AI+MCP khám phá website ở mục 7.
  Inspector local bản đầu đã có (`inspect_runner.py`): người dùng tự điều hướng,
  chọn màn hình/tab để kiểm tra số phần tử khớp và visibility, dùng cùng locator
  builder với Runner. Không thực hiện step, thu thập input value/DOM thô, sửa workbook hoặc gửi
  report lên cloud. Report chỉ metadata (hash workbook, thời điểm, số dòng và
  trạng thái). Wait/group/dropdown/read method phức tạp cần kiểm tra thủ công.
  Report xuất chủ động được người dùng quản lý, không áp retention artifact run.
  Repair local đã có (`repair_runner.py`): người dùng hover phần tử rồi Ctrl+Alt+L,
  công cụ dựng CSS cấu trúc, kiểm tra duy nhất/visibility/identity và yêu cầu xác
  nhận trước xuất workbook mới. Hash nguồn chống áp sửa lên phiên bản file đã đổi.
  Giữ dữ liệu các sheet, thay locator của một dòng và đặt toàn bộ step/testcase
  inactive; thêm sheet repair_review, không sửa file gốc hoặc upload DOM/input.
  Đây là picker local; phase 13–14 ở trên bổ sung AI discovery/repair có người duyệt.
  Kiểm chứng hành vi trên browser thật vẫn cần UAT riêng.
  PostgreSQL và deployment GreenNode cần kiểm chứng riêng trước vận hành.

Hướng dẫn cài đặt và giới hạn: [docs/RUNNER_SETUP.md](docs/RUNNER_SETUP.md).

## 1. Mục tiêu

Tích hợp `runner.py` hiện có vào hệ thống Web Extract / AI Test Automation theo hướng:

- UI và backend có thể deploy lên GreenNode.
- Runner Playwright vẫn có thể chạy **local trên máy người dùng**.
- File `.env` chứa username/password vẫn nằm trên máy người dùng.
- Credential không được gửi lên AI, UI hoặc GreenNode.
- File config testcase có thể được upload/chọn để chạy nhưng không được lưu lâu dài trên server.
- Log, result, error và screenshot được quản lý theo `run_id`, có retention 7 ngày.
- Trước khi xóa artifact phải cảnh báo người dùng và lưu audit log.
- AI có thể hỗ trợ inspect website, generate step và repair locator, nhưng runner vẫn là executor deterministic.

---

## 2. Nguyên tắc kiến trúc

Tách hệ thống thành hai phần chính:

```text
                     GreenNode / Server
        ┌──────────────────────────────────────┐
        │ UI                                   │
        │ Backend API                          │
        │ AI Planner / Step Generator          │
        │ Job Management                       │
        │ Audit Metadata                       │
        │ Artifact Retention / Notification    │
        └─────────────────┬────────────────────┘
                          │
                          │ job / config / command
                          ▼
                  Máy người dùng
        ┌──────────────────────────────────────┐
        │ Local Runner Agent                   │
        │ runner.py                            │
        │ Playwright                           │
        │ config testcase                      │
        │ runner.env / .env local              │
        └─────────────────┬────────────────────┘
                          │
                          ▼
                    Website UAT
```

### Vì sao nên để Runner local?

1. Credential không phải gửi lên server.
2. Website UAT nội bộ có thể chỉ truy cập được từ VPN/mạng nội bộ của người dùng.
3. Runner hiện tại đã hoạt động và đang đọc `.env` local.
4. Giảm thay đổi code runner.
5. Execution vẫn deterministic, không phụ thuộc AI khi chạy regression.

---

## 3. Cơ chế đọc `.env`

### 3.1. Hiện trạng

Runner hiện đang đọc `.env` trong cùng thư mục với `runner.py`.

### 3.2. Thiết kế mới

Giữ backward compatibility nhưng cho phép chỉ định đường dẫn `.env` khác thông qua biến:

```text
RUNNER_ENV_PATH
```

Pseudo-code:

```python
from pathlib import Path
from dotenv import load_dotenv
import os

default_env = Path(__file__).resolve().parent / ".env"

env_path = os.getenv(
    "RUNNER_ENV_PATH",
    str(default_env)
)

load_dotenv(env_path)
```

### 3.3. Hành vi

Nếu không set `RUNNER_ENV_PATH`:

```text
runner/
├─ runner.py
└─ .env
```

Runner vẫn hoạt động như hiện tại.

Nếu người dùng muốn để credential ở vị trí riêng:

```text
C:\Users\<user>\.web-extract-agent\runner.env
```

thì Local Runner Agent có thể set:

```text
RUNNER_ENV_PATH=C:\Users\<user>\.web-extract-agent\runner.env
```

### 3.4. Yêu cầu bảo mật

- Không gửi nội dung `.env` lên server.
- Không gửi `.env` cho AI.
- Không log username/password.
- Không ghi credential vào testcase.
- Không lưu credential trong database.
- Không đưa `.env` vào Git.
- `.gitignore` phải chứa:

```text
.env
*.env
runner.env
```

---

## 4. Credential trong testcase

Testcase không chứa giá trị username/password thật.

Chỉ dùng placeholder hoặc role/key:

```text
${RM_USERNAME}
${RM_PASSWORD}
```

hoặc:

```text
ROLE=RM
```

Runner local resolve giá trị từ `.env` tại runtime.

Ví dụ:

```env
RM_USERNAME=user_x
RM_PASSWORD=secret_x

ADMIN_USERNAME=user_y
ADMIN_PASSWORD=secret_y
```

AI chỉ được thấy:

```text
${RM_USERNAME}
${RM_PASSWORD}
```

không được thấy giá trị thật.

---

## 5. Recorder / Inspector

Khi người dùng thao tác trên website để generate step:

### Không được capture:

- Username thật
- Password thật
- Token
- OTP
- Nội dung nhạy cảm trong input

### Chỉ capture loại thao tác

Ví dụ:

```json
{
  "event": "fill",
  "field": "username",
  "locator_type": "label",
  "locator": "Username"
}
```

```json
{
  "event": "replace",
  "field": "password",
  "locator_type": "label",
  "locator": "Password"
}
```

```json
{
  "event": "select_dropdown",
  "field": "branch",
  "locator_type": "role",
  "locator": "combobox|Branch"
}
```

Recorder chỉ cần biết:

- `click`
- `fill`
- `replace`
- `select`
- `check`
- `radio`
- `upload`
- `wait`
- `assert`

Không cần biết user nhập giá trị gì.

---

## 6. Vai trò AI và Playwright MCP

### AI / Playwright MCP dùng cho:

- Khám phá website chưa biết.
- Inspect DOM / accessibility tree.
- Tìm locator candidate.
- Hiểu flow qua nhiều screen.
- Generate step theo schema runner.
- Repair locator khi step fail.

### Runner dùng cho:

- Execute testcase.
- PASS / FAIL.
- Screenshot.
- Log.
- Retry deterministic.
- Regression execution.

### Flow đề xuất

```text
Người dùng mô tả testcase
hoặc Record thao tác
        ↓
Inspector / Playwright MCP
        ↓
AI Planner
        ↓
AI generate step
        ↓
Python schema validator
        ↓
Locator validator
        ↓
Runner chạy thử
        ↓
Fail?
 ├─ No  → lưu/export step
 └─ Yes → AI + MCP repair
```

Khi step đã ổn:

```text
runner.py
→ execute trực tiếp
→ không gọi AI
→ không dùng MCP
→ không tốn token
```

---

## 7. Hai mode tạo testcase

### 7.1. Describe Mode

Người dùng mô tả testcase bằng text.

Phù hợp cho flow ngắn.

Ví dụ:

```text
Mở trang login, đăng nhập bằng role RM,
tìm khách hàng theo CIF và kiểm tra tên khách hàng.
```

AI + MCP khám phá website và generate step.

### 7.2. Record Mode

Người dùng thao tác trực tiếp trên website.

Phù hợp cho flow nhiều màn hình.

Hệ thống ghi:

- URL / route
- Element được click
- Element được fill
- Element được select
- Navigation
- Modal
- Screen transition

Không ghi giá trị nhập thực tế.

---

## 8. Tích hợp Runner vào UI

UI không cần lưu lâu dài file testcase.

### Flow:

```text
User chọn testcase file
        ↓
Upload tạm
        ↓
Backend tạo run
        ↓
Local Runner execute
        ↓
Return status/result
        ↓
Temp testcase delete
```

Nếu chạy Local Mode:

```text
UI local
→ đọc config từ máy user
→ runner local
→ không upload config lên server
```

Nếu chạy Server/Hybrid Mode:

```text
UI server
→ config upload tạm
→ job gửi cho Local Runner Agent
→ runner local execute
→ trả result đã sanitize
```

---

## 9. Naming convention cho run

Không dùng:

```text
run_20260915_ab12
```

Ưu tiên dùng tên config + timestamp.

Ví dụ config:

```text
UAT_Login.xlsx
```

Run folder:

```text
UAT_Login_20260915_081530
```

Metadata:

```text
config_name = "UAT_Login.xlsx"
run_id      = "UAT_Login_20260915_081530"
```

---

## 10. Quản lý file tạm

### Temp execution files

```text
temp_uploads/
  UAT_Login_20260915_081530/
    testcase.xlsx
    intermediate/
```

Xóa ngay sau khi execution hoàn tất.

### Run artifacts

```text
runs/
  UAT_Login_20260915_081530/
    run_log.txt
    results.xlsx
    errors.xlsx
    screenshots/
```

Run artifacts giữ tối đa 7 ngày.

---

## 11. Retention Policy

### Chính sách

```text
Temp testcase:
→ delete ngay sau run

Run artifacts:
→ giữ tối đa 7 ngày

Audit metadata:
→ giữ lâu dài theo policy
```

### Metadata tối thiểu

```text
run_id
config_name
started_at
finished_at
status
pass_count
fail_count
duration
expires_at
notification_sent_at
deleted_at
deletion_reason
```

Không lưu:

- testcase content
- username
- password
- token
- OTP

---

## 12. Notification trước khi xóa

Trước khi artifact hết hạn, ví dụ trước 24 giờ:

```text
Run UAT_Login_20260915_081530
sẽ bị xóa sau 24 giờ.

Hãy tải xuống các file cần thiết trước thời hạn.
```

UI có thể hiển thị:

```text
Expires in: 23h 45m
```

---

## 13. Audit log khi xóa

Khi cleanup job xóa artifact:

```json
{
  "event": "RUN_ARTIFACTS_DELETED",
  "run_id": "UAT_Login_20260915_081530",
  "deleted_at": "2026-09-22T08:00:00",
  "reason": "retention_policy_7_days",
  "notification_sent_at": "2026-09-21T08:00:00",
  "deleted_items": [
    "run_log.txt",
    "results.xlsx",
    "errors.xlsx",
    "screenshots/"
  ]
}
```

Audit log nên:

- append-only nếu có thể
- không cho user thường sửa/xóa
- không chứa credential
- đủ để chứng minh hệ thống đã cảnh báo và xóa đúng policy

---

## 14. Cleanup Job

Cleanup chạy định kỳ, ví dụ mỗi ngày.

Pseudo-flow:

```text
Find runs where:
expires_at <= now

For each run:
    verify notification_sent
    delete artifact folder
    write audit event
    mark deleted_at
```

Nếu notification chưa gửi:

```text
send notification
delay delete theo policy
```

---

## 15. Local Runner Agent

Đây là thành phần chạy trên máy người dùng.

Nhiệm vụ:

- Nhận job từ server.
- Đọc config local/tạm.
- Đọc `.env` local.
- Chạy runner.py.
- Sanitize log.
- Upload result cần thiết.
- Không gửi secret.

Có thể chạy như:

```text
python local_runner_agent.py
```

hoặc đóng gói thành executable/container sau này.

---

## 16. API giao tiếp Server ↔ Local Runner

Ví dụ job payload:

```json
{
  "run_id": "UAT_Login_20260915_081530",
  "config_name": "UAT_Login.xlsx",
  "action": "EXECUTE",
  "artifact_policy": {
    "retention_days": 7
  }
}
```

Không được gửi:

```text
username
password
token
OTP
.env content
```

Result:

```json
{
  "run_id": "UAT_Login_20260915_081530",
  "status": "FAILED",
  "passed": 18,
  "failed": 2,
  "duration": 94.3
}
```

---

## 17. Deploy lên GreenNode

Có thể deploy:

```text
GreenNode:
- UI
- FastAPI backend
- AI integration
- Job orchestration
- Audit DB
- Notification
- Retention scheduler
```

Không nên mặc định deploy runner credential lên GreenNode.

Runner execution có thể để local.

### Hybrid Deployment

```text
GreenNode
  ↓
UI/API/AI
  ↓
Job Queue
  ↓
Local Runner Agent
  ↓
Internal UAT Website
```

---

## 18. Vì sao Hybrid phù hợp với môi trường ngân hàng

1. Website UAT có thể chỉ truy cập từ internal network/VPN.
2. Credential không cần rời khỏi máy.
3. AI không tiếp xúc secret.
4. Runner hiện tại được tái sử dụng gần như nguyên vẹn.
5. UI và AI vẫn có thể deploy tập trung.
6. Audit và retention vẫn quản lý tập trung.
7. Giảm rủi ro compliance và data leakage.

---

## 19. Các thay đổi tối thiểu cần làm với runner hiện tại

### Runner core

Không rewrite runner.

Chỉ cần:

1. Cho phép custom `.env` path.
2. Tách executor thành callable function nếu hiện đang chạy script-only.
3. Chuẩn hóa output theo `run_id`.
4. Sanitize log.
5. Không ghi secret vào screenshot/log.
6. Có adapter trả result cho UI/backend.

Ví dụ interface:

```python
result = run_testcase(
    config_path=config_path,
    run_id=run_id,
    output_dir=output_dir,
    env_path=env_path
)
```

---

## 20. Security Rules

Bắt buộc:

```text
- AI không được đọc .env.
- AI không được thấy credential.
- Recorder không capture input value nhạy cảm.
- Runner không log password/token.
- Screenshot phải mask sensitive field nếu cần.
- Temp config phải delete sau execution.
- Artifact auto delete sau 7 ngày.
- Notification trước khi delete.
- Audit event phải được ghi sau delete.
- .env không commit Git.
```

---

## 21. MVP đề xuất

Phase 1:

```text
- UI chọn config
- Local Runner execute
- .env local
- Result trả về UI
- Temp delete
- Artifact lưu 7 ngày
```

Phase 2:

```text
- Record Mode
- Inspector
- AI generate step
- Step validator
```

Phase 3:

```text
- Playwright MCP discovery
- AI repair locator
- Self-healing step
```

Phase 4:

```text
- Notification
- Cleanup scheduler
- Audit retention
- GreenNode deployment
```

---

## 22. Kết luận

Kiến trúc khuyến nghị:

```text
GreenNode
= UI + API + AI + orchestration + audit

Local machine
= runner + Playwright + config + .env + internal network access
```

Credential tiếp tục nằm trên máy người dùng.

Runner không cần rewrite lớn.

AI hỗ trợ generate/repair step nhưng không tham gia execution regression bình thường.

File testcase là temporary.

Run artifacts giữ 7 ngày, có notification trước khi xóa và audit log sau khi xóa.


---

## 23. Authentication và User Management

UI không còn chỉ dành cho admin trace lỗi mà sẽ có nhiều người dùng chạy testcase, xem kết quả và tải artifact. Vì vậy cần bổ sung authentication và authorization ở mức MVP.

### Role tối thiểu

```text
admin
user
```

### Quyền đề xuất

**admin**
- Quản lý user.
- Xem toàn bộ run.
- Xem audit log.
- Theo dõi cleanup/retention.
- Trace lỗi hệ thống.
- Khóa/mở user.

**user**
- Tạo/chạy testcase.
- Xem run do chính mình tạo.
- Tải artifact của chính mình.
- Không xem run của user khác.
- Không xem credential hoặc secret hệ thống.

### Không dùng Excel để quản lý user/password

User/password của UI phải lưu trong database.

Không lưu password plaintext.

Ví dụ bảng `users`:

```text
user_id
username
email
password_hash
role
is_active
created_at
updated_at
```

Password phải được hash bằng thuật toán phù hợp như bcrypt hoặc Argon2.

---

## 24. Phân biệt UI Credential và Runner Credential

Hai loại credential phải hoàn toàn tách biệt.

### UI Login Credential

Dùng để đăng nhập hệ thống:

```text
username/email
password_hash
role
```

Lưu trong DB trung tâm.

### Runner UAT Credential

Dùng để runner đăng nhập website UAT:

```text
RM_USERNAME
RM_PASSWORD
ADMIN_USERNAME
ADMIN_PASSWORD
...
```

Lưu trong `runner.env` trên máy người dùng.

Không lưu runner credential trong DB trung tâm.  
Không gửi runner credential lên GreenNode.  
Không gửi runner credential cho AI.

---

## 25. Data Storage Architecture

### Central Database

Lưu:

```text
users
roles
runs
audit_logs
notifications
retention metadata
```

Ví dụ bảng `runs`:

```text
run_id
config_name
created_by
started_at
finished_at
status
pass_count
fail_count
duration
expires_at
notification_sent_at
deleted_at
deletion_reason
```

MVP dùng SQLite; production có thể chuyển PostgreSQL.

### Artifact Storage

Lưu theo `run_id`:

```text
runs/
  UAT_Login_20260915_081530/
    run_log.txt
    results.xlsx
    errors.xlsx
    screenshots/
```

Retention 7 ngày.

Artifact phải gắn với `run_id` và `owner_user_id`.

### Temp Storage

Lưu tạm uploaded testcase, working files, intermediate files.

```text
temp_uploads/
  UAT_Login_20260915_081530/
```

Xóa ngay sau execution hoàn tất.

### Runner Local Secret Storage

Lưu trên máy người dùng:

```text
C:\Users\<user>\.web-extract-agent\runner.env
```

hoặc:

```text
~/.web-extract-agent/runner.env
```

Credential không sync qua Git và không upload lên server.

### Runtime Secrets

Các secret như:

```text
GREENNODE_API_KEY
DATABASE_URL
JWT_SECRET
BACKEND_SECRET
```

phải nằm trong environment variable hoặc secret manager/runtime secret.

---

## 26. Audit theo User

Audit phải ghi được ai thực hiện hành động nào.

Ví dụ:

```json
{
  "event": "RUN_CREATED",
  "run_id": "UAT_Login_20260915_081530",
  "user_id": "user_001",
  "created_at": "2026-09-15T08:15:30"
}
```

Ví dụ cleanup:

```json
{
  "event": "RUN_ARTIFACTS_DELETED",
  "run_id": "UAT_Login_20260915_081530",
  "owner_user_id": "user_001",
  "deleted_at": "2026-09-22T08:00:00",
  "reason": "retention_policy_7_days",
  "notification_sent_at": "2026-09-21T08:00:00"
}
```

Audit không được chứa password, token hoặc testcase content nhạy cảm.

---

## 27. Authentication MVP Scope

MVP chỉ cần:

```text
- Login
- Logout
- User/Admin role
- Password hash
- is_active
- Authorization theo owner
- Audit basic
```

Chưa cần:

```text
- MFA
- Forgot password qua email
- Self registration
- OAuth nhiều provider
- Permission matrix phức tạp
```

Nếu sau này có SSO/OIDC/IAM phù hợp thì có thể thay login local bằng SSO.

---

## 28. Storage Summary

```text
Central DB
├─ users
├─ roles
├─ runs
├─ audit_logs
├─ notifications
└─ retention metadata

Artifact Storage
├─ run_log.txt
├─ results.xlsx
├─ errors.xlsx
└─ screenshots/

Temp Storage
└─ testcase/config upload
   → delete sau run

User Machine
└─ runner.env
   ├─ UAT username
   └─ UAT password

Runtime Secret
├─ GREENNODE_API_KEY
├─ DATABASE_URL
└─ backend secret
```

---

## 29. Kiến trúc chốt

```text
GreenNode / Server
├─ UI
├─ Authentication
├─ User/Role Management
├─ FastAPI Backend
├─ AI / Step Generation
├─ Job Orchestration
├─ Central DB
├─ Audit
├─ Notification
└─ Retention Scheduler

User Machine
├─ Local Runner Agent
├─ runner.py
├─ Playwright
├─ config testcase
└─ runner.env
```

Nguyên tắc:

```text
UI credential
→ DB hash

Runner credential
→ local runner.env

Backend secret
→ runtime secret

Testcase upload
→ temporary

Run artifact
→ retention 7 ngày

Audit metadata
→ lưu dài hạn theo policy
```
