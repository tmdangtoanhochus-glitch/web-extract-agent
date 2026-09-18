# Kéo lịch sử, bảng, cookie và báo lỗi

## 1. Kéo dữ liệu ban đầu

1. Bước 1: chọn dataset mới/có sẵn hoặc file JSON, thêm URL nguồn.
2. Bước 2: khai báo field. Với bảng, field là các cột muốn lưu.
3. Bước 3: bật **Kéo nhiều lượt / kéo bảng**.
4. Chọn kiểu trường hoặc bảng HTML, khoảng ngày và số trang.
5. Chạy, xem số lượt, số record lưu/bỏ qua, số lượt lỗi. Trạng thái `partial`
   nghĩa là có lượt lỗi; các record đã lưu vẫn giữ nguyên.
6. Bước 4 chọn số record/trang và trang dữ liệu. CSV tải xuống chứa trang đang xem.

### Xuất toàn bộ dữ liệu (phase 10)

Tại Bước 4, mở **Xuất toàn bộ dataset** → **Chuẩn bị CSV toàn bộ** → **Tải CSV toàn bộ**.
File này không bị giới hạn bởi trang đang xem. Nút **Tải CSV trang hiện tại** vẫn giữ
riêng cho nhu cầu lấy một trang.

- Có thể lọc theo **Ngày crawl** hoặc **Ngày dữ liệu (as_of)**, tính theo UTC,
  bao gồm cả ngày bắt đầu/kết thúc. Bộ lọc chỉ áp dụng file xuất, không đổi bảng UI.
- Ngày dữ liệu được ghi từ cột ngày trong luồng kéo bảng. Khi lọc theo as_of,
  record không có ngày dữ liệu sẽ không được xuất; không tự lấy ngày crawl thay thế.
- CSV có UTF-8 BOM để đọc tiếng Việt; metadata đặt tên `meta.*`, cột schema đặt
  tên `data.*`. Đối tượng/mảng được ghi dạng JSON trong một ô. Thiếu field thành ô trống.
- Nội dung giống công thức bắt đầu bằng `=`, `+`, `-`, `@` (kể cả có khoảng trắng
  phía trước) được thêm dấu nháy đơn để giữ dạng text trong bảng tính. Dữ liệu DB
  không bị sửa. CSV trang hiện tại cũng bảo vệ chuỗi công thức.
- File chuẩn bị là kết quả tại lần xuất đó, không tự cập nhật theo lịch append.
  Bấm chuẩn bị lại để lấy dữ liệu mới; có nút xóa file khỏi bộ nhớ phiên UI.
- Backend đọc từng nhóm 500 record theo khóa thời gian/ID, không OFFSET, và loại
  record có `crawled_at` sau mốc bắt đầu xuất. Đây là giới hạn timestamp cho dữ
  liệu append-only, **không phải transaction snapshot**: ghi backdate/đồng hồ lùi
  hoặc sửa record trực tiếp trong DB giữa lúc xuất không được đảm bảo.
- UI tải trọn file vào RAM. Với dataset rất lớn, dùng HTTP client streaming trực
  tiếp `GET /datasets/{dataset_id}/export.csv`; tham số tùy chọn `date_basis`,
  `start`, `end`. Không cần đăng nhập Runner. Response có `X-Export-Cutoff` và
  `Cache-Control: no-store`; backend không ghi file tạm.
- Audit chỉ lưu metadata/số dòng/trạng thái phát stream, không nội dung record.
  Trạng thái complete là backend phát xong, không chứng minh người dùng đã lưu file.

### Xem trước trước khi chạy

Bật chế độ nhiều lượt/bảng rồi bấm **Xem trước đợt kéo** ở Bước 3:

- Hiển thị kế hoạch số lượt, ngày và số trang. Chế độ fields chỉ lập kế hoạch,
  không tải trang hoặc gọi AI.
- Chế độ bảng tải **trang đầu tiên**, kiểm tra ánh xạ/lọc ngày và hiển thị tối đa
  10 dòng mẫu cùng số dòng khớp. Những trang còn lại chưa được kiểm tra.
- Không lưu dataset/record/file/cache. Mẫu nằm trong phiên UI, không vào audit
  hoặc AI debug. Có request ID nên vẫn báo lỗi được nếu xem trước thất bại.
- Kết quả là ảnh chụp của lần xem trước gần nhất; đổi cấu hình thì xem trước lại.
  Dữ liệu website vẫn có thể đổi giữa lúc xem trước và lúc chạy thật.
- Cookie xóa sau mỗi submit; nếu nguồn cần đăng nhập, dán lại khi bấm chạy thật.

### Chạy lại riêng lượt lỗi

Sau một đợt **bảng lưu DB** có lỗi, Bước 3 xuất hiện **Chạy lại riêng các lượt lỗi**.
Chọn đợt, nhập lại cookie nếu cần, rồi bấm **Chạy lại lượt lỗi**. Hệ thống dùng
cấu hình gốc và cùng dataset, chỉ chạy các số thứ tự đã lỗi trong audit.
Các dòng đã lưu vẫn được kiểm tra trùng, kể cả lượt từng bị lỗi giữa chừng khi ghi DB.

Backend đối chiếu fingerprint cấu hình và dataset, không tin số thứ tự do client tự
chỉ định. Nếu muốn sửa selector/cột/ngày/URL, chạy đợt mới và chọn dataset có sẵn.
Không tự retry. Không hỗ trợ retry chọn lọc cho file append, fields hay khoảng ngày
di động vì chưa có cơ chế đảm bảo giữ đúng kế hoạch/không ghi lặp tương ứng.
Timeout chưa có kết quả xác định cũng không được coi là danh sách lượt lỗi.
Retry đọc dữ liệu hiện tại của nguồn, không khôi phục bản snapshot website cũ.
Nút retry dựa trên lịch sử trong phiên UI; đợt cũ trước phase 9 không có fingerprint
không dùng API retry được. Khi mất phiên UI, có thể chạy lại đợt trên dataset có sẵn.

Lỗi selector, ô gộp, số cột, định dạng ngày và giới hạn dòng có mã lỗi riêng.
Thông báo không in giá trị ô gây lỗi. Admin xem được cả lịch `partial` và lỗi từng lượt.

Ví dụ URL nguồn có bộ lọc lịch sử/phân trang:

```text
https://example.com/history?from={start}&to={end}&page={page}
```

`from`, `to`, `page` là ví dụ: phải thay bằng tên tham số thực tế của nguồn.
`{start}` và `{end}` được thay bằng ngày ISO `YYYY-MM-DD`, hai đầu bao gồm.
Khoảng 01–03 với một ngày/lượt và hai trang/khoảng sẽ tạo sáu lượt.
Trang bắt đầu có thể là 0 hoặc 1. Tối đa 100 lượt mỗi đợt; chia nhỏ đợt lớn.
Nguồn cần thật sự hỗ trợ lịch sử; thay URL không tạo ra dữ liệu đã mất.

### Bảng

- Selector phải khớp đúng một bảng, ví dụ `table`, `#history` hoặc `table.prices`.
- Ánh xạ mỗi field sang số cột từ 1, trái sang phải; dòng tiêu đề toàn `th` bỏ qua.
- Có thể chọn cột ngày và định dạng (`%d/%m/%Y`, `%Y-%m-%d`). Khi có khoảng ngày,
  lọc theo ngày trong từng dòng; giá trị ngày sai khiến lượt đó lỗi, không âm thầm bỏ dòng.
- Nếu URL không có placeholder ngày, bảng vẫn lọc theo cột ngày từ nội dung nguồn.
- Chưa hỗ trợ bảng chỉ xuất hiện sau JavaScript, ô gộp, tự bấm trang tiếp theo,
  cursor pagination hoặc tự tải ảnh trong ô. Cần URL phân trang rõ ràng.
- Mỗi dòng lưu thành một record; không gọi AI để suy diễn dòng bảng.
- DB bỏ qua dòng có toàn bộ giá trị giống nhau trong cùng dataset, kể cả ở trang khác
  hoặc đợt khác. Dòng thay đổi tạo record mới, không ghi đè record cũ.
  Nên chọn cả cột ngày/mã định danh để các sự kiện khác nhau không bị coi là trùng.
- File JSON chỉ hỗ trợ append trong chế độ nhiều lượt; giữ cả dòng lặp như luồng file cũ.

## 2. Kéo tiếp và schedule append

- Muốn chạy lại/tiếp tục một đợt, chọn **Dùng dataset có sẵn** ở Bước 1.
  Chọn **Tạo dataset mới** vẫn tạo dataset mới, không tự gộp.
- Sau lượt kéo, vào Bước 5 → **Đặt lịch append từ đợt vừa kéo**.
- Nguồn, field, ánh xạ bảng, phân trang và dataset/file được dùng lại. Lịch không tự
  chuyển dữ liệu sang dataset khác.
- Nếu đợt ban đầu có khoảng ngày, lịch đổi thành **N ngày gần nhất**, tính theo ngày UTC;
  mỗi lần chạy sẽ tính lại ngày. Chọn khoảng chồng lấn để nhận dữ liệu về muộn.
- Nếu không có khoảng ngày, lịch kéo lại nguồn và số trang đã chọn; ô số ngày không áp dụng.
- Cấu hình lưu trong DB, được nạp lại sau restart. Lịch cũ không có cấu hình mới vẫn
  chạy pipeline một trang như trước.

Giới hạn vận hành: một backend worker/process như cấu hình APScheduler hiện tại.
Các đợt bulk giữ khóa trong lúc xử lý, nhả khóa khi chờ tạm dừng để lịch và người
dùng khác tiếp tục. Khi resume, kiểm tra lại dedup trước lượt tiếp theo.
Chưa có khóa phân tán cho nhiều process hoặc checkpoint tiếp tục sau crash.
UI bulk dùng queue RAM từ phase 11; endpoint `/crawl`, preview và retry chọn lọc
vẫn đồng bộ, UI chờ tối đa 600 giây. Nếu timeout, kiểm tra dataset trước khi chạy lại;
timeout UI không chứng minh backend đã dừng. Đợt dài nên chia nhỏ.
Dedup DB đọc lịch sử theo từng trang; dataset lớn cần tối ưu chỉ mục/unique key trước khi scale.

### Tạm dừng và thay đổi lịch (Bước 5)

- **Tạm dừng lịch** ngăn lượt chạy tiếp theo, không ngắt lượt đã bắt đầu.
- **Bật lại lịch** tính lần chạy tiếp theo từ thời điểm bật, không chạy bù toàn bộ
  thời gian tạm dừng. Trạng thái giữ qua restart backend.
- **Đổi thời gian chạy** thay chu kỳ hoặc giờ hàng ngày và múi giờ, không đổi
  nguồn hay đích. Bấm **Lưu thời gian mới** mới áp dụng. Lịch đang pause vẫn pause.
  Form này thay timing cũ; lịch cron phức tạp qua API cần gửi đầy đủ trigger_args.
- UI hiển thị next_run_at từ scheduler, để trống nếu pause hoặc scheduler chưa chạy.
- API: `PATCH /schedules/{job_id}` với `enabled` hoặc cặp `trigger_type/trigger_args`.
  Các route lịch vẫn thuộc crawler chia sẻ như trước, không thêm đăng nhập Runner.

Backend dùng API trigger/job của [APScheduler 3](https://apscheduler.readthedocs.io/en/3.x/modules/schedulers/base.html);
trạng thái enabled được lưu riêng trong DB của ứng dụng để giữ qua restart.

### Tạm dừng đợt đang kéo lâu (Bước 3)

1. Bật **Kéo nhiều lượt / kéo bảng**, bấm **Chạy crawl**. UI gửi task nền rồi trả
   quyền điều khiển ngay; theo dõi **Tiến độ đợt crawl**, tự cập nhật khoảng 2 giây/lần.
2. Bấm **Tạm dừng crawl**. Trạng thái ban đầu là đang chờ tạm dừng: request đang
   fetch/extract/ghi vẫn chạy hết. Sau đó chuyển thành **Đã tạm dừng** trước lượt kế tiếp.
3. Bấm **Tiếp tục crawl** để kéo lượt kế tiếp. Hoặc **Dừng hẳn đợt kéo** để kết thúc;
   giữ mọi record đã lưu, không tự chạy lại phần chưa kéo.

Giới hạn cụ thể:

- Không ngắt cưỡng bức một request HTTP/AI đang chờ. Dừng ở lượt cuối có thể kết thúc
  bình thường nếu không còn lượt nào phía sau. Pause không rollback dữ liệu.
- Tự dừng sau 15 phút ở trạng thái pause; muốn tiếp tục muộn hơn phải tạo đợt mới
  với dataset có sẵn. File append vẫn có thể lặp record nếu chạy lại toàn đợt.
- Đợt nền hỗ trợ tối đa 20 nguồn cùng schema/dataset/file, mỗi nguồn giữ giới hạn
  100 lượt. Queue có 2 worker thread, tối đa 8 task chưa kết thúc; task paused vẫn
  chiếm một worker nhưng không giữ khóa bulk. Queue đầy trả 429.
- Cookie chỉ nằm trong RAM của đợt, hết hạn có thể khiến những lượt sau thất bại.
  Mã điều khiển nằm trong phiên UI, backend chỉ giữ hash; không cần đăng nhập Runner.
  Không gửi mã này vào báo lỗi. Đóng/mất phiên UI có thể mất quyền điều khiển đợt đó.
- Backend restart làm mất queue/control; **không tự replay**. DB/audit đã ghi còn
  nguyên. Kiểm tra dataset trước khi tạo đợt mới. UI có nút bỏ theo dõi đợt đã mất.
- Kết quả task ở RAM tối đa 1 giờ, hoặc bị loại sớm khi bộ đệm đủ 32 task; tải/xem
  record đã lưu vẫn qua dataset/file bình thường. Chưa có resume sau crash.
- Crawl một trang, preview và retry chọn lọc hiện vẫn đồng bộ, chưa có nút điều
  khiển giữa request. Cơ chế này không điều khiển Runner testcase/UAT.

API nền: `POST /crawl-jobs` với `requests` là danh sách CrawlRequest; trả `id` và
`control` một lần. Gửi `X-Crawl-Control` khi đọc `GET /crawl-jobs/{id}` hoặc
`POST /crawl-jobs/{id}/control` với action `pause`, `resume`, `cancel`.

## 3. Cookie ở luồng người dùng

1. Tự đăng nhập website nguồn bằng trình duyệt.
2. F12 → **Network**, tải lại trang. Chọn request lấy nội dung cần kéo.
3. **Headers → Request Headers → Cookie**: copy chỉ giá trị.
4. Bước 3 của ứng dụng → **Nguồn cần đăng nhập** → chọn đúng nguồn, dán cookie.

[Tài liệu Network chính thức của Chrome](https://developer.chrome.com/docs/devtools/network/reference).
Không dán mật khẩu, Authorization, Set-Cookie, cURL hoặc HAR. Chỉ dùng phiên được phép truy cập.
Khi triển khai, dùng HTTPS giữa trình duyệt, UI và API.

Cookie chỉ nằm trong bộ nhớ phục vụ đợt hiện tại; không lưu DB/audit hoặc cấu hình lịch.
Form xóa sau submit; chỉ gắn cookie cho đúng scheme/host/port đã chọn, chặn redirect
sang origin khác. robots.txt và rate limit vẫn áp dụng. Cookie hết hạn phải dán lại.
Không bảo đảm lọc mọi dữ liệu nhạy cảm mà website trả về; dữ liệu crawl vẫn cần được người
dùng chọn và quản lý phù hợp. Dataset crawler hiện vẫn dùng mô hình chia sẻ có sẵn.

**Thay đổi tương thích:** cookie lưu chung trước đây trong admin không còn được fetcher
mặc định tự dùng. Admin vẫn có thể xem metadata và xóa mục cũ. Lịch của nguồn bắt buộc
đăng nhập chưa được hỗ trợ qua cookie tạm; cần cơ chế phiên riêng trước khi triển khai lịch đó.

## 4. Báo lỗi và chẩn đoán

- Sau khi thử crawl, mở **Báo lỗi cho admin**, chọn lượt và loại vấn đề, bấm gửi.
- Hộp này nằm ngoài phần hiển thị kết quả: `TypeError` sau khi API trả dữ liệu vẫn báo được.
- Báo cáo lưu bền trong audit: mã lượt kéo, URL bỏ query/userinfo, tên field, trạng thái,
  cấu hình khoảng ngày/phân trang và vị trí lỗi. Không gửi cookie, raw HTML, giá trị trích xuất,
  exception message hay biến cục bộ. Báo cáo từ client được đánh dấu chưa xác minh.
- Admin đăng nhập riêng, mở tab báo lỗi để xem; có thể bấm **AI chẩn đoán**. Chỉ metadata
  được gửi cho AI; kết quả lưu lại và chỉ là gợi ý, không tự sửa code/chạy lệnh.
- Không cấu hình AI vẫn nhận báo cáo bình thường. Hộp admin hiện tra 1000 audit event gần nhất,
  chưa có phân trang/tìm kiếm toàn bộ lịch sử. Không gửi email hay thông báo ngoài ứng dụng.

Runner vẫn yêu cầu đăng nhập riêng; crawl và gửi báo lỗi không yêu cầu đăng nhập Runner.
