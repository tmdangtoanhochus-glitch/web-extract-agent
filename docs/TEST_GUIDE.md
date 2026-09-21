# Hướng dẫn kiểm thử — Web Data Puller (Crawl · Automation · Admin)

Dành cho đồng nghiệp tham gia kiểm thử. Tài liệu chia thành từng ca kiểm thử có **bước làm** và **kết quả mong đợi**. Bạn chỉ cần làm theo và ghi **Đạt / Không đạt**.

- **Địa chỉ ứng dụng (bản deploy):** https://endpoint-4c33f5f5-3a75-4d5d-b688-15ac95e25581.agentbase-runtime.aiplatform.vngcloud.vn
- **Tài khoản Admin / Automation:** xin nhóm phát triển cấp (không ghi mật khẩu trong tài liệu). Không chia sẻ tài khoản.
- **Cách báo lỗi:** dùng khung **"💬 Gặp vấn đề? Gửi phản hồi / báo lỗi"** ở thanh bên (xem ca TC-FB). Ghi kèm mã ca kiểm thử và ảnh chụp màn hình.

## 0. Trước khi bắt đầu

### 0.1 Quy tắc dữ liệu
- Chỉ dùng **trang công khai dành cho thực hành** dưới đây. Không nhập cookie, mật khẩu hay dữ liệu thật của khách hàng vào hệ thống khi thử nghiệm.
- Không kiểm thử tải (spam) hệ thống. Đợi lượt kéo xong rồi mới chạy lượt kế tiếp.

### 0.2 Trang mẫu dùng để test

| Mã | URL | Dùng để thử |
|---|---|---|
| S1 | https://quotes.toscrape.com/ | Trang tĩnh, nhiều bản ghi (câu trích dẫn, tác giả, thẻ) |
| S2 | https://quotes.toscrape.com/page/{page}/ | Phân trang bằng `{page}` |
| S3 | https://books.toscrape.com/ | Nhiều sản phẩm, có ảnh, giá |
| S4 | https://books.toscrape.com/catalogue/page-{page}.html | Phân trang sản phẩm |
| S5 | https://quotes.toscrape.com/js/ | Trang nạp bằng JavaScript (cần Playwright) |
| S6 | https://httpbin.org/status/403 | Giả lập trang trả lỗi 403 |
| S7 | https://example.com/khong-ton-tai | Giả lập lỗi 404 |
| S8 | https://jsonplaceholder.typicode.com/posts | **API JSON** công khai: 100 bản ghi (`userId`, `id`, `title`, `body`) |
| S9 | https://jsonplaceholder.typicode.com/posts?_page={page}&_limit=10 | API JSON có phân trang bằng `{page}` |
| S10 | https://dummyjson.com/products?limit=10 | API JSON lồng nhau: mảng `products`, mỗi sản phẩm có `title`, `price`, `brand` |
| S11 | https://data.vietnambiz.vn/macro-economic | Trang **bảng** chỉ số kinh tế vĩ mô (25 dòng, 5 cột) — thử chế độ **Bảng HTML** (không cần AI) |
| S12 | https://bonbanh.com/oto/page,{page} | Phân trang có số trang **trong đường dẫn** (`page,2`). Website có thể chặn tự động, không phải lỗi hệ thống |

### 0.3 Trang thực hành cho Automation

Chỉ dùng các trang **luyện kiểm thử tự động công khai** dưới đây (tài khoản trong bảng do chính trang công bố cho mục đích thực hành, **không phải tài khoản thật**):

| Mã | URL | Dùng để thử |
|---|---|---|
| A1 | https://the-internet.herokuapp.com/inputs | Ô nhập số: điền giá trị rồi **đọc lại** để so sánh (dùng cho workbook mẫu `docs/samples/Sample_Inputs.xlsx`) |
| A2 | https://the-internet.herokuapp.com/login | Đăng nhập: tài khoản thực hành `tomsmith` / `SuperSecretPassword!` (trang tự công bố ngay trên màn hình) |
| A3 | https://www.saucedemo.com/ | Đăng nhập + danh sách sản phẩm: `standard_user` / `secret_sauce` (công bố trên trang) |
| A4 | https://practicetestautomation.com/practice-test-login/ | Đăng nhập: `student` / `Password123` (công bố trên trang) |
| A5 | https://quotes.toscrape.com/login | Đăng nhập, chấp nhận user/mật khẩu bất kỳ |

### 0.4 Bảng ghi kết quả (mẫu)

| Mã ca | Người test | Ngày | Kết quả (Đạt/Không đạt) | Ghi chú / mã phản hồi |
|---|---|---|---|---|

---

## 1. Giao diện chung

| Mã | Bước làm | Kết quả mong đợi |
|---|---|---|
| TC-UI-01 | Mở địa chỉ ứng dụng | Thấy banner có logo MSB và tên "Web Data Puller"; thanh bên có 3 mục **Crawl · Automation · Admin** |
| TC-UI-02 | Rê chuột qua từng mục ở thanh bên, bấm đổi trang | Mục nổi lên khi rê chuột; mục đang chọn có màu gradient; đổi trang không lỗi |
| TC-UI-03 | Bấm nút « ở đầu thanh bên để thu gọn, sau đó bấm » để mở lại | Thanh bên đóng/mở được; nút bo góc nổi khối |
| TC-UI-04 | Ở Admin và Automation, quan sát các tab | Tab nổi khối, tab đang chọn có gradient; nội dung tab đổi khi bấm |

## 2. Crawl — luồng cơ bản (5 bước)

### TC-CR-01 Lấy một trang, lưu vào DB (đường thành công)
1. Trang **Crawl**, Bước 1: chọn **Lưu vào DB**, **Tạo dataset mới**, tên dataset `Test-Quotes-01`.
2. Nhập URL **S1**, bấm **+ Thêm link**.
3. Bấm **2. Trường dữ liệu**, thêm 3 field: `quote` (mô tả: nội dung câu trích dẫn), `author` (tác giả), `tags` (các thẻ).
4. Bấm **3. Chạy & Kết quả** → **🚀 Chạy crawl**.

**Mong đợi:** thanh tiến trình chạy; Console log hiện trạng thái `saved`; có nhiều bản ghi (trang S1 có 10 câu); mỗi giá trị có confidence; có phần xem trước dữ liệu.

### TC-CR-02 Xem dữ liệu đã lưu
1. Bấm **4. Dữ liệu đã lưu**, chọn dataset `Test-Quotes-01`.

**Mong đợi:** thấy các bản ghi vừa lưu, mỗi bản ghi có `quote`, `author`, `tags`, thời điểm crawl.

### TC-CR-03 Chạy lại khi nội dung không đổi
1. Quay lại Bước 1, chọn **Dùng dataset có sẵn** → `Test-Quotes-01`, giữ nguyên URL S1 và field, chạy lại.

**Mong đợi:** trạng thái **unchanged** (không đổi), không tạo thêm bản ghi.

### TC-CR-04 Schema không khớp
1. Dùng dataset có sẵn `Test-Quotes-01` nhưng đổi tập field ở Bước 2 (ví dụ chỉ còn `quote`), chạy.

**Mong đợi:** thông báo `schema_mismatch` (hệ thống không tự gộp dataset khác schema).

### TC-CR-05 Nhiều URL cùng lúc
1. Tạo dataset mới, thêm cả **S1** và **S3** ở Bước 1, field `title` (tiêu đề hoặc tên) và `price`.

**Mong đợi:** thanh tiến trình chạy qua cả hai URL; mỗi URL có dòng log riêng.

### TC-CR-06 Trang nạp bằng JavaScript
1. Dataset mới, URL **S5**, field `quote`, `author`. Chạy.

**Mong đợi:** lấy được dữ liệu (trang chỉ hiện nội dung sau khi chạy JavaScript). Ghi nhận thời gian chạy (chậm hơn trang tĩnh).

### TC-CR-07 Lỗi HTTP và báo lỗi rõ ràng
1. Dataset mới, URL **S6** (403), một field bất kỳ, chạy. Lặp lại với **S7** (404).

**Mong đợi:** Console log báo lỗi có mã (`http_403`, `http_404`) hoặc lý do dễ hiểu; **không** báo lỗi trống hoặc treo mãi.

## 3. Crawl — nhiều trang và bảng

### TC-CR-10 Phân trang bằng `{page}`
1. Bước 1, mở **Phân trang — cào nhiều page liên tiếp**, nhập pattern **S2**, chọn số trang (ví dụ 3), bấm tạo danh sách URL.

**Mong đợi:** danh sách URL tạo đúng 3 link (`page/1`, `page/2`, `page/3`). Chạy xong có dữ liệu của cả 3 trang.

### TC-CR-11 Kéo nhiều lượt, xem trước và tạm dừng
1. Bước 3: bật **Kéo nhiều lượt / kéo bảng**, cấu hình theo giao diện; bấm **Xem trước đợt kéo**.
2. Chạy thật; giữa chừng bấm **Tạm dừng crawl**, rồi **Tiếp tục crawl**.

**Mong đợi:** xem trước chỉ tải trang đầu và không lưu; tạm dừng/tiếp tục hoạt động; kết quả cuối không trùng dòng.

### TC-CR-12 Chạy lại lượt lỗi
1. Nếu một đợt kéo có lượt lỗi, dùng phần **Chạy lại riêng các lượt lỗi**.

**Mong đợi:** chỉ chạy lại lượt đã lỗi; dòng đã lưu không bị lưu trùng.

### TC-CR-13 Trang bảng: dùng chế độ Bảng HTML, không cần AI
1. Bước 1 nhập **S11**, dataset mới. Bước 2 khai báo 5 field: `chi_tieu`, `ky_cong_bo`, `ky_hien_tai`, `ky_truoc`, `ngay_cong_bo_tiep_theo` (mô tả tùy ý).
2. Bước 3: bật **Kéo nhiều lượt / kéo bảng** → **Bảng HTML**, CSS chọn bảng `table`, cột lần lượt 1, 2, 3, 4, 5. Bấm **Xem trước đợt kéo**, rồi chạy.

**Mong đợi:** xem trước hiện các dòng mẫu; chạy xong có **25 dòng** (ví dụ dòng đầu: "Tăng trưởng GDP (YoY)", "Quý 2/2026", "8.39%", "7.94%"), hoàn tất trong vài giây, không có thanh tiến độ AI. So với cách trích bằng AI (dễ chậm hoặc timeout vì phải sinh 25 bản ghi), chế độ bảng nhanh và chính xác hơn.

## 4. Crawl — lưu ra file, ảnh, lịch

### TC-CR-20 Lưu ra file
1. Bước 1 chọn **Lưu ra file**; Bước 2 đặt tên file, định dạng **xlsx** (rồi lặp lại với **csv**), cách ghi **Thêm vào file**. Chạy với S1.
2. Ở Bước 3 bấm nút **⬇ Tải** file kết quả và mở bằng Excel.

**Mong đợi:** file mở được, đúng cột, đủ dòng. Lưu ý: luồng file không tạo dataset và không kiểm tra trùng. File được lưu **trên server** (thư mục `data/exports/`) và bạn tải về trình duyệt bằng nút **⬇ Tải**; không lưu thẳng vào ổ đĩa máy bạn.

### TC-CR-21 Tải ảnh
1. Dataset mới, URL **S3**, field `title` và `image` (URL ảnh). Ở Bước 2 đánh dấu `image` là ảnh cần tải. Chạy.

**Mong đợi:** giá trị `image` được thay bằng đường dẫn file ảnh trên server (thư mục `data/images/`); nếu một ảnh lỗi thì chỉ cảnh báo, bản ghi vẫn lưu.

### TC-CR-22 Lịch tự động (chỉ lưu vào DB)
1. Bấm **5. Lịch tự động**, chọn một dataset đã có (tạo ở TC-CR-01), nhập URL, mô tả field, chọn chu kỳ 1 giờ, bấm **+ Tạo lịch**.
2. Xem lịch trong danh sách, sửa chu kỳ, rồi xóa lịch.

**Mong đợi:** tạo, sửa, xóa lịch thành công, có thông báo. (Không cần đợi tới giờ chạy để kết luận Đạt cho ca này.)

### TC-CR-23 Lịch KHÔNG hỗ trợ lưu ra file
1. Ở **5. Lịch tự động**, tìm lựa chọn "Lưu ra file".

**Mong đợi:** không có lựa chọn lưu file cho lịch; chỉ có dòng chú thích "Lịch chỉ lưu vào DB. Cần file thì xuất từ dataset ở Bước 4". (Lý do: file nằm trên server dùng chung, không phân quyền theo người dùng.) Muốn có file: chạy lịch vào dataset rồi xuất CSV/XLSX ở Bước 4.

## 4b. Crawl — tiến độ, chế độ Nhanh/Chậm và hạn mức AI

> Hệ thống đang dùng model có hạn mức thấp (GLM-5.3-flash: **5 request/phút**). Với trang dài chia nhiều đoạn, bạn sẽ thấy hệ thống
> **tự chờ** giữa các lượt gọi AI — đó là hành vi đúng, không phải lỗi treo. Trang dài để thử: https://vi.wikipedia.org/wiki/H%C3%A0_N%E1%BB%99i
> (chia nhiều đoạn, mất vài phút). Field gợi ý: `topic` (chủ đề đoạn văn), `fact` (một sự kiện hoặc số liệu được nêu).

### TC-CR-40 Hai thanh tiến độ tách biệt
1. Chạy crawl trang S1 (trang ngắn), quan sát ngay dưới nút chạy.

**Mong đợi:** thấy dòng trạng thái ("⚙️ CODE đang chạy — tải trang" rồi "🤖 MODEL AI đang xử lý" rồi "✅ Hoàn tất") và **hai thanh**:
`① Crawl` (tải, làm sạch, kèm số ký tự gửi AI) và `② AI` (số đoạn xong/tổng). Có đồng hồ ⏱ đếm giây.

### TC-CR-41 Trang dài: tiến độ từng đoạn
1. Crawl trang Wikipedia "Hà Nội" ở chế độ mặc định (Chậm).

**Mong đợi:** thanh ② hiện `k/N đoạn xong · 🤖 model đang xử lý đoạn x/N`; thanh ① đã đầy. Khi hết hạn mức request/phút, dòng trạng thái
đổi sang "⏳ Đang chờ hạn mức AI ~Ns (… không phải lỗi)" và số giây đếm ngược; sau đó tự chạy tiếp. Kết thúc `saved`; nếu trang quá dài,
Console log ghi "Trang quá dài — chỉ xử lý 6 đoạn đầu".

### TC-CR-42 Chế độ Nhanh bị giới hạn theo hạn mức
1. Bước 3, mở "Tốc độ trích xuất AI", tick "Dùng chế độ Nhanh"; crawl lại đúng trang ở TC-CR-41 (dùng dataset khác).

**Mong đợi:** lúc đầu có đoạn xử lý ngay nhưng mỗi phút **chỉ gửi tối đa bằng hạn mức** (GLM-5.3-flash: 5 lượt/phút), các đoạn còn lại hiện "chờ hạn mức" rồi lần lượt chạy;
**không** có đoạn nào lỗi 429 (thanh ② không hiện "⚠ đoạn lỗi"). Tổng thời gian ngắn hơn chế độ Chậm, nhưng không nhanh gấp N lần vì hạn mức.

### TC-CR-43 Trang không cần AI hoặc không đổi
1. Chạy lại đúng URL/field của TC-CR-01 với dataset có sẵn khi trang không đổi.

**Mong đợi:** thanh ② hiện "không cần gọi (nội dung không đổi)" và đầy ngay; không có lượt gọi AI.

### TC-CR-44 Lỗi tải trang không hiện tiến độ giả
1. Crawl URL S6 (403).

**Mong đợi:** lỗi báo rõ như TC-CR-07; thanh không hiện "Hoàn tất" giả.

## 4c. Crawl — nguồn API (JSON)

Dành cho trang lấy dữ liệu qua API. Dán **link API** vào chính ô URL và tick **Nguồn là API (JSON)** ở Bước 1. Hệ thống tải JSON, tự tìm mảng bản ghi, ghép tên field với khóa JSON và **không gọi AI** (tức thì, không tốn token, không timeout). Lấy link API từ trình duyệt: mở trang → F12 → tab Network → lọc Fetch/XHR → chọn dòng trả dữ liệu → Copy URL.

### TC-CR-50 API đơn giản
1. Bước 1: nhập **S8**, tick **Nguồn là API (JSON)**. Bước 2: dataset mới, field `title` và `body` (tên trùng khóa JSON). Chạy.

**Mong đợi:** lưu **100 bản ghi**, hoàn tất dưới vài giây; thanh AI báo bỏ qua (không gọi AI). Xem dữ liệu ở Bước 4 thấy `title` và `body` đúng như API.

### TC-CR-51 Ghép field theo tên gần giống hoặc theo mô tả
1. Nhập **S10**, tick nguồn API. Field: `ten` (mô tả `title`), `gia` (mô tả `price`), `hang` (mô tả `brand`). Chạy.

**Mong đợi:** 10 bản ghi; hệ thống ghép được vì mô tả trùng khóa JSON. Field đặt tên hoàn toàn khác và không có mô tả trùng khóa sẽ báo lỗi.

### TC-CR-52 Báo lỗi rõ khi không ghép được field
1. Nhập **S8**, tick nguồn API, khai báo field `mau_son`. Chạy.

**Mong đợi:** thông báo lỗi nêu rõ field không ghép được và **liệt kê các khóa JSON có trong dữ liệu** (`userId`, `id`, `title`, `body`) để bạn sửa tên field.

### TC-CR-53 Nhiều trang API
1. Bước 1 mở **Phân trang**, pattern **S9**, từ page 1 đến 3, bấm tạo URL; tick nguồn API; field `title`. Chạy.

**Mong đợi:** 3 URL, mỗi URL 10 bản ghi (tổng 30), chạy lại lần nữa thì các trang đã lưu báo "không đổi".

### TC-CR-54 Tick API nhưng URL là trang web thường
1. Nhập **S1**, tick nguồn API, chạy.

**Mong đợi:** lỗi "Phản hồi không phải JSON; bỏ tick 'Nguồn là API' nếu đây là trang web thường".

### TC-CR-55 Chặn địa chỉ nội bộ
1. Nhập `http://127.0.0.1:8000/x`, tick nguồn API, chạy.

**Mong đợi:** bị từ chối ngay (không gọi tới địa chỉ nội bộ).

## 5. Crawl — tuân thủ và trang cần đăng nhập

### TC-CR-30 Lưu ý website chặn tự động
1. Bước 1, tìm khung cảnh báo vàng "Một số website chặn hoặc không cho phép truy cập tự động", bấm **Xem chi tiết**.

**Mong đợi:** có danh sách CAPTCHA, WAF, giới hạn IP, OTP/2FA, robots.txt; nêu rõ hệ thống **không giải CAPTCHA** và cách xử lý hợp lệ.

### TC-CR-31 robots.txt mặc định được tôn trọng
1. Bước 3, mở khung **robots.txt** và đọc cảnh báo.
2. Thử crawl một trang có robots.txt cấm (nhờ nhóm phát triển cung cấp URL thử, hoặc bỏ qua ca này nếu chưa có).

**Mong đợi:** mặc định trang bị cấm sẽ báo `blocked_by_robots_txt`.

### TC-CR-32 Bỏ qua robots.txt phải có lý do
1. Ở khung robots.txt, tích **Bỏ qua robots.txt cho lượt này** nhưng **để trống lý do**, chạy.
2. Lặp lại với lý do "Kiểm thử nội bộ, được phép".

**Mong đợi:** ca 1 bị từ chối (yêu cầu lý do, ít nhất 5 ký tự); ca 2 chạy được. Tích chọn này chỉ áp dụng cho lượt đó.

### TC-CR-33 Dán cookie phải xác nhận rủi ro
1. Bước 3, mở khung **Nguồn cần đăng nhập: dán cookie cho lượt kéo này**. Đọc hướng dẫn 4 bước và khung cảnh báo rủi ro.
2. Dán một chuỗi **giả** (ví dụ `test=abc123`), **không tích** ô xác nhận, bấm **🚀 Chạy crawl**.
3. Tích ô "Tôi hiểu các rủi ro trên và chấp nhận dùng cookie của mình cho lượt này", chạy lại.

**Mong đợi:** ca 2 báo lỗi "chưa tích xác nhận… chưa chạy" và **không** gửi yêu cầu; ca 3 chạy. Sau khi chạy, ô cookie được xóa (phải dán lại nếu muốn dùng lần nữa).
**Lưu ý:** dùng cookie giả để thử, tuyệt đối không dùng cookie thật của tài khoản quan trọng.

## 6. Phản hồi và báo lỗi (mọi màn hình)

### TC-FB-01 Phản hồi câu hỏi cách dùng
1. Mở khung **💬 Gặp vấn đề? Gửi phản hồi / báo lỗi** ở thanh bên, nhập: "Làm sao để lưu dữ liệu ra file Excel?", bấm **Gửi phản hồi**.

**Mong đợi:** hệ thống trả lời trực tiếp bằng hướng dẫn (AI nhận định không phải lỗi). *Ghi chú:* phụ thuộc AI thật; nếu AI chưa cấu hình sẽ chuyển admin.

### TC-FB-02 Báo lỗi thật
1. Nhập: "Bấm chạy crawl thì báo lỗi và không có dữ liệu", gửi.

**Mong đợi:** hiện thông báo đã chuyển admin kèm **mã**; Admin thấy phản hồi này ở khung "Phản hồi AI đã chuyển admin" (xem TC-AD-05).

### TC-FB-03 Không lộ bí mật
1. Nhập phản hồi có dòng `cookie: sessionid=abcdef123456`, gửi. Sau đó admin mở phản hồi.

**Mong đợi:** trong phản hồi lưu, đoạn cookie bị che bằng `[REDACTED]`.

## 7. Admin

### TC-AD-01 Đăng nhập admin chung
1. Trang **Admin**, đăng nhập bằng tài khoản admin.

**Mong đợi:** thấy 5 tab: *Crawl · Job lỗi & gợi ý sửa*, *Crawl · Cookie*, *Crawl · Báo lỗi từ người dùng*, *Automation · Người dùng*, *Automation · Audit*. Đăng nhập sai thì báo "Sai username/password".

### TC-AD-02 Đăng nhập một lần dùng cho cả Automation
1. Sau TC-AD-01, chuyển sang trang **Automation**.

**Mong đợi:** đã đăng nhập sẵn (thấy tên tài khoản và vai trò admin), không phải nhập lại.

### TC-AD-03 Job lỗi và gợi ý sửa
1. Tab *Crawl · Job lỗi & gợi ý sửa*, bấm **Tải lại danh sách lỗi**.

**Mong đợi:** hiện danh sách lỗi (hoặc "Không có lỗi nào"). Nếu có lỗi, thử nút gợi ý sửa: kết quả chỉ là văn bản gợi ý, **không có nút áp dụng tự động**.

### TC-AD-04 Quản lý người dùng Automation
1. Tab *Automation · Người dùng*, tạo user `tester01` (mật khẩu ≥ 12 ký tự, role `user`).
2. Khóa rồi mở khóa user; đặt lại mật khẩu.

**Mong đợi:** các thao tác thành công có thông báo; mật khẩu dưới 12 ký tự bị từ chối; không tự khóa được chính mình.

### TC-AD-05 Xử lý phản hồi chuyển admin
1. Ở thanh bên Admin, mở **💬 Phản hồi AI đã chuyển admin**, xem phản hồi tạo ở TC-FB-02, mở **Trace**, bấm **Đã xử lý**.

**Mong đợi:** thấy nội dung, chẩn đoán của AI, trace; sau khi bấm "Đã xử lý" phản hồi biến khỏi danh sách.

### TC-AD-06 Quên mật khẩu
1. Đăng xuất Automation. Ở màn đăng nhập, mở **Quên mật khẩu?**, nhập username `tester01`, gửi.
2. Đăng nhập Admin, xem yêu cầu ở tab *Automation · Người dùng*, đặt lại mật khẩu cho `tester01`.

**Mong đợi:** thông báo gửi yêu cầu luôn giống nhau dù username có tồn tại hay không; admin thấy yêu cầu; đặt lại xong thì yêu cầu biến mất; đăng nhập bằng mật khẩu mới thành công, mật khẩu cũ không còn dùng được.

## 8. Automation

**Automation là gì (đọc trước khi test).** Đây là bộ **kiểm thử giao diện tự động theo dữ liệu**. Bạn mô tả flow trong một file Excel (workbook): sheet `steps` liệt kê từng bước (mở màn hình, điền, bấm, đọc kết quả), sheet `testcases` liệt kê các ca cần thử cùng **kết quả mong đợi** (`expected_*`). Một chương trình nhỏ tên **agent** chạy trên **máy của bạn**, mở trình duyệt thật, làm theo workbook rồi so giá trị đọc được với `expected_*`: kết quả **PASS** (khớp), **FAIL** (lệch) hoặc **UNVERIFIED** (không có giá trị mong đợi để so). Trang web chỉ dùng để soạn workbook, giao việc và xem tóm tắt; **trình duyệt, tài khoản đăng nhập và báo cáo chi tiết không rời khỏi máy bạn**.

Các tab trên trang (theo thứ tự xuất hiện): **Chạy testcase · Lịch sử & kết quả · Agent · Thông báo · Describe · Record local · Inspector local**. Ba tab cuối là công cụ **soạn workbook**, bốn tab đầu là **vận hành**. Mỗi ca dưới đây giải thích một chức năng, cách thử và kết quả mong đợi.

> Các ca TC-AU-04 trở đi cần **máy có Python** (theo khung **🛠️ Cài môi trường Python** trên trang), trừ TC-AU-12 và TC-AU-13. Nhóm không cài Python có thể chỉ làm TC-AU-01 đến TC-AU-03, TC-AU-12 (xem lịch sử do người khác chạy) và TC-AU-13.

### 8.1 Chuẩn bị chung cho các ca chạy thật
1. Lấy cả dự án về máy (`git clone`) hoặc bản đóng gói nhóm phát triển cung cấp; cài Python theo hướng dẫn trên trang (TC-AU-04).
2. Tạo file `runner.env` (ngoài Git) chứa tài khoản của hệ thống được test theo dạng `TIỀN_TỐ_USERNAME` / `TIỀN_TỐ_PASSWORD`. Tiền tố lấy từ cột `role_code` (và `specialized_bank`) của testcase; để trống cả hai thì dùng tiền tố `DEFAULT`. Với workbook mẫu chỉ cần:

   ```
   DEFAULT_USERNAME=demo
   DEFAULT_PASSWORD=demo
   ```

   (Trang thực hành A1 không cần đăng nhập nên giá trị nào cũng được; **không** đặt tài khoản thật vào file này khi thử.)
3. Workbook mẫu có sẵn: `docs/samples/Sample_Inputs.xlsx` (dùng trang A1). Nó có 2 testcase: **TC01** nhập 123 và mong đợi đọc lại 123 (phải **PASS**), **TC02** nhập 45 nhưng cố ý mong đợi 46 (phải **FAIL**). Hai kết quả này cho biết cả nhánh đúng và nhánh sai đều hoạt động.

### TC-AU-01 Đăng nhập và hướng dẫn
1. Mở trang **Automation** khi chưa đăng nhập.
2. Đăng nhập bằng `tester01`.

**Chức năng:** cổng đăng nhập riêng của Automation (tách khỏi Crawl, Crawl không cần đăng nhập). **Mong đợi:** chưa đăng nhập chỉ thấy form đăng nhập và mục "Quên mật khẩu?". Sau đăng nhập thấy khung **📘 Automation là gì?** (mô tả kỹ thuật), **🛠️ Cài môi trường Python** (mở sẵn lần đầu), khung cảnh báo website chặn tự động, và 7 tab.

### TC-AU-02 Người dùng chỉ thấy dữ liệu của mình
1. Với hai tài khoản khác nhau, mỗi tài khoản xem tab **Lịch sử & kết quả** và **Agent**.

**Chức năng:** cô lập dữ liệu theo chủ sở hữu. **Mong đợi:** mỗi người chỉ thấy run và agent của mình.

### TC-AU-03 Describe: AI viết workbook nháp từ mô tả (cần AI bật)
1. Tab **Describe**, nhập mô tả, ví dụ: "Mở trang, nhập một số vào ô số, đọc lại giá trị ô số để kiểm tra". Tick xác nhận không có bí mật, bấm **Tạo workbook nháp**.
2. Bấm **Tải workbook nháp** và mở bằng Excel.

**Chức năng:** AI chỉ sinh **sheet `steps`** đúng lược đồ đóng (các cột `screen`, `step`, `action`, `locator_type`, `locator`, `value_source`…) và **cột mẫu của `testcases`**. Mọi bước ở trạng thái **không hoạt động (`active=N`)**, `locator` chỉ là chỗ giữ chỗ để bạn điền hoặc dùng Inspector/Record; AI **không** tạo dữ liệu testcase, **không** đặt kết quả mong đợi, **không** đụng sheet `settings`. **Mong đợi:** nếu AI đã bật thì tải được file có sheet `steps` và cột `testcases`; nếu chưa bật thì hiện "Describe AI chưa được bật". Không nhập dữ liệu thật hoặc URL nội bộ.

### TC-AU-04 Cài môi trường Python theo hướng dẫn
1. Làm theo khung **🛠️ Cài môi trường Python** (Bước 1–6) trên máy cá nhân.

**Chức năng:** chuẩn bị máy để chạy agent (Python, thư viện, trình duyệt Chromium do Playwright quản lý). **Mong đợi:** hai lệnh kiểm tra ở Bước 6 in `Thu vien OK` và `Chromium OK`. Ghi lại **bước nào khó hiểu hoặc lỗi** để cải thiện hướng dẫn.

### TC-AU-05 Agent: tạo và thu hồi
1. Tab **Agent**, tạo agent; sao chép **token** (chỉ hiện một lần).
2. Thu hồi agent thử.

**Chức năng:** agent là tiến trình `local_runner_agent.py` trên máy bạn, xác thực bằng token; nó hỏi server có việc không (`claim`), báo "còn sống" khi đang chạy (heartbeat), ghi nhật ký cục bộ (journal) để **không tự chạy lại** khi mất kết nối, rồi gửi lại **chỉ số liệu tóm tắt** (số ca PASS/FAIL, thời gian). **Mong đợi:** token hiển thị một lần, rời trang không xem lại được; thu hồi thành công. Trên trang còn có lệnh chẩn đoán journal (`--journal-status`) và gửi lại kết quả (`--resend-run`), chỉ đọc hoặc gửi lại, không chạy testcase.

### TC-AU-06 Record local: ghi thao tác thật thành workbook nháp (cần Python)
1. Chạy `python record_runner.py --output config/Recorded_Draft.xlsx --events-output config/Recorded_Events.json` ở máy bạn.
2. Trong trình duyệt mở ra, tự vào **A2** (hoặc A3), đăng nhập và thao tác vài bước. Phím tắt: **Ctrl+Alt+N** bắt đầu màn hình kế tiếp, **Ctrl+Alt+P** tạm dừng/tiếp tục, **Ctrl+Alt+W** (rê chuột lên phần tử) thêm bước chờ, **Ctrl+Alt+A** (trên ô nhập) thêm bước đọc kết quả. Đóng trình duyệt để xuất file.

**Chức năng:** ghi click, điền, chọn, tick/untick và upload bằng **vị trí phần tử** (hỗ trợ iframe và shadow DOM mở). **Không ghi** giá trị nhập, nội dung file hay URL. **Mong đợi:** sinh file Excel nháp (step ở trạng thái không hoạt động, có header testcases) và file JSON sự kiện không chứa giá trị nhập hoặc URL. Bạn tự nhập testcase và kỳ vọng.

### TC-AU-07 Ghép nháp vào workbook và kiểm tra tĩnh (cần Python)
1. Ghép nháp vào workbook có sẵn: `python prepare_runner.py --template docs/samples/Sample_Inputs.xlsx --draft config/Recorded_Draft.xlsx --output config/Prepared.xlsx`.
2. Kiểm tra: `python preflight_runner.py --config docs/samples/Sample_Inputs.xlsx`.

**Chức năng:** `prepare` giữ nguyên settings và testcase bạn đã nhập, chỉ bổ sung header còn thiếu và hỏi từng mục thay đổi. `preflight` là **kiểm tra tĩnh** (cấu trúc, dòng active, locator nháp), không mở trình duyệt, không đọc bí mật. **Mong đợi:** với workbook mẫu, preflight in `ready_for_local_review: true`, `active_steps: 2`, `active_testcases: 2`, không có lỗi. Lưu ý: đạt preflight **chưa** chứng minh đăng nhập hay hành vi đúng.

### TC-AU-08 Inspector: kiểm tra locator còn khớp phần tử không (cần Python)
1. `python inspect_runner.py --config docs/samples/Sample_Inputs.xlsx --output inspection.json`.
2. Trong trình duyệt mới tự mở **A1**. Ở terminal nhập số màn hình và số tab (ví dụ `1 1`), xong nhập `q` để lưu báo cáo.

**Chức năng:** với mỗi step, đếm số phần tử khớp `locator` và báo trạng thái (ví dụ `UNIQUE_VISIBLE` = đúng 1 phần tử đang hiển thị). Báo cáo **chỉ chứa số dòng, số phần tử, trạng thái**; không chứa DOM, URL, locator hay giá trị nhập; không gửi lên server. **Mong đợi:** báo cáo có một dòng cho mỗi step; với workbook mẫu, ô số thường ở trạng thái khớp 1 phần tử hiển thị. Ghi lại trạng thái từng dòng bạn thấy. Nhắc lại: `UNIQUE_VISIBLE` chưa chứng minh đúng mục tiêu.

### TC-AU-09 Repair: chọn lại phần tử khi giao diện đổi (cần Python)
1. Cố ý sửa `locator` của dòng 2 trong một bản sao workbook thành giá trị sai (ví dụ `input[type=text]`), chạy lại Inspector để thấy báo không khớp.
2. `python repair_runner.py --config <bản sao> --row 2 --output config/Repaired.xlsx`. Trong trình duyệt mở **A1**, rê chuột lên ô số rồi nhấn **Ctrl+Alt+L**; xem CSS đề xuất ở terminal, nhập `EXPORT`.

**Chức năng:** đề xuất locator mới từ phần tử bạn trỏ; chỉ đổi `locator_type`/`locator` của **dòng đã chọn**, giữ nguyên dữ liệu, đặt mọi step/testcase của bản sao về `active=N` để buộc bạn rà soát lại; file gốc không đổi. **Mong đợi:** xuất được bản sao; chạy lại Inspector với bản sao thấy khớp.

### TC-AU-10 Thử một step có xác nhận (cần Python)
1. `python try_step_runner.py --config docs/samples/Sample_Inputs.xlsx --row 2 --output trial.json`.
2. Mở **A1** trong trình duyệt mới, kiểm tra phần tử được tô sáng, nhập `EXECUTE 2` ở terminal; nhập giá trị thử khi được hỏi.

**Chức năng:** thực hiện **đúng một step thật, đúng một lần**, sau khi bạn xác nhận; không thử lại, không sửa workbook, không kết luận testcase PASS. **Mong đợi:** ô số được điền; báo cáo `trial.json` ghi `ACTION_COMPLETED` (chỉ nghĩa là thao tác hoàn tất, **không phải** testcase PASS).

### TC-AU-11 Chạy testcase bằng agent (cần Python)
1. Tạo agent (TC-AU-05), đặt `docs/samples/Sample_Inputs.xlsx` vào thư mục `config`, chạy: `python local_runner_agent.py --api <địa chỉ API> --configs config --state data/local-runner --env-path runner.env`; agent hỏi token bằng ô nhập ẩn (gõ hoặc dán rồi Enter, không thấy chữ hiện ra).
2. Trên web, tab **Chạy testcase**: chọn agent, nguồn **File có sẵn trên máy agent**, nhập tên `Sample_Inputs.xlsx`, bấm **Tạo run**.

**Chức năng:** server chỉ **giao việc** (agent nhận qua `claim`); agent tự chạy **preflight trước khi mở trình duyệt**, rồi chạy tuần tự từng testcase trong Chromium trên máy bạn, đọc giá trị bằng `read_method` (ví dụ `css_input` đọc giá trị ô nhập), so **chính xác** với `expected_*`, chụp ảnh khi lỗi (ảnh che các ô nhập). Chọn **Upload tạm** nếu muốn gửi tạm workbook lên server (tối đa 10 MB; không bao giờ upload `runner.env`). **Mong đợi:** trình duyệt mở trên **máy bạn**; TC01 **PASS**, TC02 **FAIL**.

### TC-AU-12 Lịch sử & kết quả: đọc kết quả
1. Tab **Lịch sử & kết quả**, bấm **Làm mới**, mở run vừa chạy.

**Chức năng:** server lưu **báo cáo tổng hợp** (số ca PASS/FAIL/lỗi, thời gian, kết quả preflight, mã lỗi kèm sheet/dòng nếu bị chặn); Excel chi tiết và ảnh chụp lỗi nằm ở thư mục `runs` của agent trên máy bạn. Báo cáo cloud giữ tối đa 7 ngày. **Mong đợi:** thấy run với 1 ca PASS và 1 ca FAIL; run "mất theo dõi" (LOST) hiện cảnh báo riêng và không tự tạo lại; kết quả gửi muộn hiện là "kết quả nhận muộn", không phải lần chạy mới. Trong file kết quả Excel ở máy bạn: mỗi testcase một dòng, kết quả nhóm (`read_result_group`) được đánh số block đúng, còn kết quả đơn (`read_result_single`) **không** sinh block thừa.

### TC-AU-14 Báo lỗi và gợi ý sửa cho run lỗi
1. Tạo một run lỗi có chủ đích: đặt vào thư mục `config` một bản sao workbook mẫu đã xóa hết `active=Y` ở sheet `testcases` (hoặc đổi `locator` thành `:not(*)`), rồi tạo run như TC-AU-11. Run sẽ bị chặn ở kiểm tra tĩnh (trạng thái **ERROR**, preflight *blocked*). Có thể thay bằng run **FAILED** của TC02 trong workbook mẫu.
2. Tab **Lịch sử & kết quả**, mở run vừa lỗi: thấy dòng **Run này có vấn đề** cùng nút **🛠 Gợi ý sửa** và **📨 Báo lỗi cho admin**. Mở một run PASSED để xác nhận **không** có hai nút này.
3. Bấm **🛠 Gợi ý sửa**. Sau đó bấm **📨 Báo lỗi cho admin**, nhập ghi chú, bấm **Gửi cho admin**.
4. Đăng nhập Admin (tài khoản admin Runner), tab **Automation · Run lỗi & gợi ý sửa**.

**Chức năng:** giống Crawl (job lỗi và báo lỗi có gợi ý sửa). Gợi ý gồm 2 lớp: **gợi ý cố định theo từng mã lỗi** kiểm tra tĩnh (ví dụ `UNRESOLVED_LOCATOR` sheet `steps` dòng 3: điền locator thật; `ENTER_AND_ACTIVATE_USER_TESTCASES`: tự nhập testcase và đặt `active=Y`) và **gợi ý từ AI** nếu backend đã bật AI (ba phần: nguyên nhân có thể, cách sửa, cần kiểm tra thêm). Cả AI lẫn admin **chỉ thấy metadata**: trạng thái, số ca PASS/FAIL/lỗi, mã lỗi, sheet, số dòng; không thấy giá trị workbook, selector, mật khẩu hay tên file. Không có nút "áp dụng": bạn tự sửa workbook ở máy local. Giới hạn 5 lần gợi ý mỗi phút cho mỗi người. **Mong đợi:** bước 3 hiện các gợi ý cố định đúng mã lỗi của run, kèm gợi ý AI hoặc dòng "AI gợi ý sửa chưa được bật" (khi đó vẫn có gợi ý cố định); gửi báo lỗi báo thành công kèm mã. Bước 4: thấy báo lỗi (người gửi, run, trạng thái, ghi chú; mật khẩu hay token lỡ dán vào ghi chú đã bị che thành `[REDACTED]`) và run trong danh sách "cần chú ý"; nút **🤖 Hỏi AI gợi ý sửa** trả gợi ý cho run đó.

### TC-AU-13 Thông báo và quên mật khẩu
1. Tab **Thông báo** xem nhắc báo cáo sắp hết hạn; thử nút **Quên mật khẩu?** ở màn đăng nhập (xem TC-AD-05, TC-AD-06).

**Chức năng:** nhắc tải báo cáo trước khi bị xóa theo thời hạn lưu; luồng quên mật khẩu gửi yêu cầu tới admin. **Mong đợi:** thông báo hiển thị đúng; yêu cầu quên mật khẩu tới được admin.

*Trạng thái nghiệm thu:* các ca dùng **trang thật của đơn vị** (ngoài các trang thực hành công khai ở mục 0.3) **chưa được nghiệm thu**; hãy ghi nhận kỹ kết quả và các bước không rõ.

## 9. Sau khi triển khai (kiểm tra vận hành)

| Mã | Bước làm | Kết quả mong đợi |
|---|---|---|
| TC-OP-01 | Mở `<địa chỉ ứng dụng>/health` | Thấy `{"status":"ok"}` |
| TC-OP-02 | Tải lại trang sau vài phút không dùng | Trang mở bình thường, dữ liệu dataset đã lưu vẫn còn |
| TC-OP-03 | Thử vào Admin khi chưa đăng nhập | Không xem được nội dung quản trị |

## 10. Những điều KHÔNG phải lỗi (giới hạn đã biết)

- Website có CAPTCHA, WAF, OTP/2FA hoặc chặn IP đám mây có thể không lấy được dữ liệu. Hệ thống **không** vượt qua các cơ chế này.
- Trang nặng JavaScript chạy chậm hơn trang tĩnh (Playwright).
- Nguồn API: chỉ hỗ trợ phương thức GET, chưa hỗ trợ đặt lịch cho nguồn API.
- Chất lượng trích xuất phụ thuộc mô tả field và model AI; giá trị confidence thấp được gắn cờ "cần xem lại".
- Model AI có **hạn mức request/phút** (GLM-5.3-flash 5/phút): trang dài phải chờ giữa các lượt gọi; chế độ Nhanh không nhanh hơn hạn mức cho phép.
- Mỗi lượt chỉ dùng được một cookie cho một nguồn.
- Automation chạy trên **máy người dùng** và cần cài Python; không có chế độ chạy trên server.
- Tài khoản Automation do admin cấp; không có đăng ký tự do.

## 11. Cách ghi nhận và báo lỗi

Với mỗi ca **Không đạt**, ghi lại: mã ca, bước xảy ra, kết quả thực tế so với mong đợi, ảnh chụp màn hình, thời điểm (để nhóm tra cứu log), trình duyệt sử dụng.
Gửi qua khung **💬 Gặp vấn đề? Gửi phản hồi / báo lỗi** hoặc trực tiếp cho nhóm phát triển. **Không** dán cookie, mật khẩu hay dữ liệu thật vào phản hồi.

## 12. Tiêu chí chấp nhận đợt kiểm thử
- Toàn bộ ca mức ưu tiên cao (TC-CR-01..07, TC-CR-32, TC-CR-33, TC-AD-01, TC-AD-02, TC-AU-01) đạt.
- Không còn lỗi ngăn người dùng hoàn thành luồng chính (Crawl 5 bước, đăng nhập admin).
- Các ca cần AI thật hoặc trang thật (TC-FB-01, TC-AU-03, TC-AU-06 đến TC-AU-14) được ghi nhận kết quả, kể cả khi chưa đạt.
