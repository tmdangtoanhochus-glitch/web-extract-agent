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

### 0.3 Bảng ghi kết quả (mẫu)

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

## 4. Crawl — lưu ra file, ảnh, lịch

### TC-CR-20 Lưu ra file
1. Bước 1 chọn **Lưu ra file**; Bước 2 đặt tên file, định dạng **xlsx** (rồi lặp lại với **csv**), cách ghi **Thêm vào file**. Chạy với S1.
2. Ở Bước 3 bấm nút **⬇ Tải** file kết quả và mở bằng Excel.

**Mong đợi:** file mở được, đúng cột, đủ dòng. Lưu ý: luồng file không tạo dataset và không kiểm tra trùng.

### TC-CR-21 Tải ảnh
1. Dataset mới, URL **S3**, field `title` và `image` (URL ảnh). Ở Bước 2 đánh dấu `image` là ảnh cần tải. Chạy.

**Mong đợi:** giá trị `image` được thay bằng đường dẫn file ảnh trên server (thư mục `data/images/`); nếu một ảnh lỗi thì chỉ cảnh báo, bản ghi vẫn lưu.

### TC-CR-22 Lịch tự động
1. Bấm **5. Lịch tự động**, tạo lịch chạy mỗi 1 giờ cho một URL đã thử ở TC-CR-01.
2. Xem lịch trong danh sách, sửa chu kỳ, rồi xóa lịch.

**Mong đợi:** tạo, sửa, xóa lịch thành công, có thông báo. (Không cần đợi tới giờ chạy để kết luận Đạt cho ca này.)

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

> Các ca TC-AU-04 trở đi cần **máy có Python** (xem hướng dẫn trên trang). Nhóm không cài Python có thể chỉ làm TC-AU-01 đến TC-AU-03.

### TC-AU-01 Đăng nhập và hướng dẫn
1. Mở trang **Automation** khi chưa đăng nhập.
2. Đăng nhập bằng `tester01`.

**Mong đợi:** chưa đăng nhập chỉ thấy form đăng nhập và mục "Quên mật khẩu?". Sau đăng nhập thấy khung **📘 Automation là gì?** và **🛠️ Cài môi trường Python** (mở sẵn lần đầu), khung cảnh báo website chặn tự động, và 7 tab.

### TC-AU-02 Người dùng chỉ thấy dữ liệu của mình
1. Với hai tài khoản khác nhau, mỗi tài khoản xem tab **Lịch sử & kết quả** và **Agent**.

**Mong đợi:** mỗi người chỉ thấy run và agent của mình.

### TC-AU-03 Describe (cần AI bật)
1. Tab **Describe**, nhập mô tả: "Đăng nhập bằng account, tìm khách hàng theo CIF rồi đọc số tiền", bấm tạo.

**Mong đợi:** nếu AI đã bật, tải được file Excel nháp có sheet `steps`; nếu chưa bật, hiện thông báo "Describe AI chưa được bật". Không nhập dữ liệu thật.

### TC-AU-04 Cài môi trường Python theo hướng dẫn
1. Làm theo khung **🛠️ Cài môi trường Python** (Bước 1–6) trên máy cá nhân.

**Mong đợi:** hai lệnh kiểm tra ở Bước 6 in `Thu vien OK` và `Chromium OK`. Ghi lại **bước nào khó hiểu hoặc lỗi** để cải thiện hướng dẫn.

### TC-AU-05 Tạo agent
1. Tab **Agent**, tạo agent; sao chép token (chỉ hiện một lần).
2. Thu hồi agent thử.

**Mong đợi:** token hiển thị một lần; sau khi rời trang không xem lại được; thu hồi thành công.

### TC-AU-06 Record trên máy (cần Python)
1. Chạy `python record_runner.py --output config/Recorded_Draft.xlsx --events-output config/Recorded_Events.json` ở máy bạn.
2. Trong trình duyệt mở ra, tự vào một trang công khai (ví dụ https://quotes.toscrape.com/login) và thao tác vài bước, đóng trình duyệt.

**Mong đợi:** sinh ra file Excel nháp và file JSON sự kiện; không có giá trị nhập hoặc URL trong JSON.

### TC-AU-07 Chạy testcase bằng agent (cần Python và workbook)
1. Nhờ nhóm phát triển cung cấp workbook mẫu, đặt vào thư mục `config`. Tạo agent, chạy `local_runner_agent.py` với token.
2. Trên web, tab **Chạy testcase**, chọn agent và workbook, bấm chạy.

**Mong đợi:** agent nhận run, trình duyệt mở trên **máy bạn**; tab **Lịch sử & kết quả** hiện tóm tắt PASS/FAIL và thời gian; file chi tiết nằm ở `data/local-runner`.
*Trạng thái:* ca này **chưa được nghiệm thu với trang thật**, cần ghi nhận kỹ kết quả.

## 9. Sau khi triển khai (kiểm tra vận hành)

| Mã | Bước làm | Kết quả mong đợi |
|---|---|---|
| TC-OP-01 | Mở `<địa chỉ ứng dụng>/health` | Thấy `{"status":"ok"}` |
| TC-OP-02 | Tải lại trang sau vài phút không dùng | Trang mở bình thường, dữ liệu dataset đã lưu vẫn còn |
| TC-OP-03 | Thử vào Admin khi chưa đăng nhập | Không xem được nội dung quản trị |

## 10. Những điều KHÔNG phải lỗi (giới hạn đã biết)

- Website có CAPTCHA, WAF, OTP/2FA hoặc chặn IP đám mây có thể không lấy được dữ liệu. Hệ thống **không** vượt qua các cơ chế này.
- Trang nặng JavaScript chạy chậm hơn trang tĩnh (Playwright).
- Chất lượng trích xuất phụ thuộc mô tả field và model AI; giá trị confidence thấp được gắn cờ "cần xem lại".
- Mỗi lượt chỉ dùng được một cookie cho một nguồn.
- Automation chạy trên **máy người dùng** và cần cài Python; không có chế độ chạy trên server.
- Tài khoản Automation do admin cấp; không có đăng ký tự do.

## 11. Cách ghi nhận và báo lỗi

Với mỗi ca **Không đạt**, ghi lại: mã ca, bước xảy ra, kết quả thực tế so với mong đợi, ảnh chụp màn hình, thời điểm (để nhóm tra cứu log), trình duyệt sử dụng.
Gửi qua khung **💬 Gặp vấn đề? Gửi phản hồi / báo lỗi** hoặc trực tiếp cho nhóm phát triển. **Không** dán cookie, mật khẩu hay dữ liệu thật vào phản hồi.

## 12. Tiêu chí chấp nhận đợt kiểm thử
- Toàn bộ ca mức ưu tiên cao (TC-CR-01..07, TC-CR-32, TC-CR-33, TC-AD-01, TC-AD-02, TC-AU-01) đạt.
- Không còn lỗi ngăn người dùng hoàn thành luồng chính (Crawl 5 bước, đăng nhập admin).
- Các ca cần AI thật hoặc trang thật (TC-FB-01, TC-AU-03, TC-AU-06, TC-AU-07) được ghi nhận kết quả, kể cả khi chưa đạt.
