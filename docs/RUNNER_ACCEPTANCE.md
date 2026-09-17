# Runner và crawler: trạng thái nghiệm thu

Ngày đối chiếu: 2026-09-17, phase 27 (kiểm chứng offline). **562 test offline pass**,
bao gồm sửa nút input và giữ lần nhập xen giữa các frame. Một cảnh báo deprecation
Starlette/AnyIO. Test dùng HTTP/AI/browser giả lập, SQLite tạm và chặn mạng/secret.
Docker local được kiểm chứng từng ca trong RUNNER_UAT_RESULTS.md.
Chưa xác nhận PostgreSQL, GreenNode hoặc UAT thật.

Roadmap và tiêu chí kết thúc: [RUNNER_ROADMAP.md](RUNNER_ROADMAP.md).
Phase 23 đã chốt tài liệu; Docker API ở phase 24 tạm để lại theo yêu cầu người dùng.
Phase 25 đã diễn tập restart offline, chưa nghiệm thu môi trường thật.
Kết quả môi trường thật ghi tại [RUNNER_UAT_RESULTS.md](RUNNER_UAT_RESULTS.md).
562 test ở trên là regression offline, không thay thế kết quả container/UAT.

## Phạm vi đã có code và test

| Phần | Trạng thái / giới hạn |
| --- | --- |
| Crawler công khai, cookie theo đợt, báo lỗi cho admin | Có; cookie không lưu vào lịch |
| Bulk lịch sử/bảng, preview, retry lượt lỗi, dedup, export CSV | Có; bảng HTML tĩnh, retry bảng DB |
| Pause/resume/cancel bulk, bật/tắt/sửa lịch | Có; cooperative giữa lượt, queue RAM, một process |
| Runner user/admin, session, owner, agent token | Có; crawler không cần session Runner |
| Local/hybrid config, subprocess executor, preflight, summary UI | Có; executor deterministic, không tự replay sau mất kết nối |
| Journal gửi lại kết quả | Có; không chạy lại testcase |
| Kết quả sau LOST | Lưu/hiện late_result riêng, không kéo dài retention hoặc tạo lại artifact đã xóa; có CLI gửi lại journal cũ |
| Journal hỏng/ghi dở | Giữ nguyên, chặn replay đúng run, không cản mục hợp lệ; artifact lỗi được giữ để kiểm tra |
| Chẩn đoán journal local | CLI chỉ đọc, không token/API, mã lỗi và metadata giới hạn; không tự phục hồi |
| Artifact local, summary cloud, retention/cảnh báo/audit | Có; artifact chi tiết không upload cloud |
| Describe/Record, đầy đủ cột steps/header testcases | Có; không sinh dữ liệu testcase/settings |
| Recorder iframe/shadow mở, checkbox/radio/upload | Có code và DOM test tổng hợp; không thu input/filename/nội dung file; chưa browser UAT |
| AI biên dịch recording theo Runner | Có; gộp fill/Ant Design khi đủ bằng chứng, giữ event mapping và review qua compose/prepare |
| Inspector, picker repair, preparation hỏi từng setting cần thay đổi | Có; browser do người dùng điều hướng |
| Discovery và AI đề xuất locator | Có; candidate cấu trúc đã rà soát, không raw DOM/text/input |
| AI repair | Có đề xuất và xác nhận local; không tự sửa/chạy lại UAT |
| Flow nhiều màn hình | Ghép nháp tường minh bằng compose_runner.py rồi prepare_runner.py |
| Gen nhóm lặp và expected nhiều khối | Có; người dùng chọn 1–100 khối cho header, tự nhập mọi giá trị |
| Record nhiều màn hình/pause/wait/read | Có phím tắt do người dùng chủ động; không thu actual/expected |
| Thử một step | CLI local, highlight + xác nhận từng lần, report metadata; không retry hoặc kết luận testcase PASS |

## Những khả năng chưa có

- AI/MCP tự điều hướng/thực thi nghiệp vụ đã được loại khỏi phạm vi theo làm rõ của
  người dùng: AI biên dịch thao tác do người dùng thực hiện, không điều khiển thay người dùng.
- Shadow DOM đóng, drag-drop, tự suy luận assertion, nhóm lặp từ recording và mọi
  dropdown tùy biến chưa có. Ant Design trong iframe/shadow chưa tự gộp thành select_antd.
- Chuyển artifact chi tiết lên cloud: đã chọn giữ local vì dữ liệu nhạy cảm.
- Queue crawler bền vững/multi-worker, lịch dùng phiên cookie riêng theo user.

Các mục này không được diễn giải là đã hoàn tất chỉ vì bộ test pass. Phần thiết kế
đích rộng hơn triển khai hiện tại; luồng có người duyệt ở phase 13–15 là cách tích
hợp AI hiện có; phase 27 thêm biên dịch recording theo contract, không autonomous self-healing.

## Thứ tự đưa bản mới vào môi trường thử nghiệm

1. Người vận hành sao lưu persistent data khi không có job đang chạy. Không đưa
   file cấu hình/credential thực vào Git hoặc Docker context. `.dockerignore` loại
   workbook, config local và state dev; snapshot tên khác cần để ngoài build context.
2. Cập nhật API trước, UI sau, rồi mới agent. API mới nhận metadata preflight và
   discovery/repair; agent cũ vẫn gửi metrics cũ. API cũ sẽ từ chối report mới.
3. Dùng một process API và một replica trong bản này: bulk queue, điều khiển task
   và khóa append ở RAM. Restart mất task/control; không replay. Record đã lưu còn.
4. Gắn persistent storage cho data crawler và metadata/temp/summary Runner theo
   cấu hình hiện tại. SQLite cần persistent filesystem; PostgreSQL cần nghiệm thu
   riêng trước khi chuyển, không đổi DB chỉ để chạy phase này.
5. Người vận hành tự cấu hình runtime secret. Không mở port API công khai bằng HTTP;
   dùng HTTPS, reverse proxy và giới hạn request/login theo chính sách môi trường.
   Không thay file credential để bật tính năng. Xem RUNNER_SETUP.md để cài/khởi chạy.
6. Kiểm tra `/health` API/UI; sau đó chạy các ca dưới. Health chỉ xác nhận service
   đang phục vụ, không chứng minh agent/AI/UAT hoặc persistent storage hoạt động.

## Ca nghiệm thu người vận hành tự chạy

Chỉ dùng website được phép và dữ liệu thử. Người vận hành nhập credential local;
không gửi credential, URL nội bộ, workbook thật, screenshot hoặc raw log cho trợ lý.

| Ca | Thao tác | Kỳ vọng |
| --- | --- | --- |
| Crawl công khai | Mở UI chưa đăng nhập, crawl nguồn thử | Crawl dùng được; trang Runner yêu cầu đăng nhập |
| Bulk | Kéo bảng nhiều trang, pause rồi resume/cancel | Dừng ở ranh giới lượt, record đã lưu còn; resume không thêm trùng |
| Lịch | Pause lịch, đổi chu kỳ rồi restart | Trạng thái/timing được nạp lại; pause không hủy lượt đã bắt đầu |
| Báo lỗi | Gửi báo cáo sau một lỗi crawl/UI | Admin thấy request ID và metadata, không cookie/input |
| Describe/discovery | Tạo nháp; highlight và xuất snapshot rồi gen steps | Đủ cột, steps inactive, testcases chỉ header, không settings |
| Nhiều màn hình | Compose rồi prepare với template thử | Thứ tự đúng, testcase/settings nguồn giữ nguyên; hỏi riêng setting cần đổi |
| Nhóm lặp/nhiều kết quả | Yêu cầu group và chọn số khối expected trong Describe | Action group hợp lệ, đủ header trống; không sinh dữ liệu hoặc đổi settings |
| Record phím tắt | N chia màn hình, P pause/resume, W wait, A read với Ctrl+Alt | State đúng, thao tác pause không ghi, wait/read inactive và expected trống |
| Record mở rộng | Ghi iframe/shadow mở, checkbox/radio và upload file thử | Scope đúng, không ghi giá trị/filename; upload chỉ có header để tự nhập đường dẫn |
| Nút input | Bấm input button/submit/reset/image trên trang thử, gồm shadow mở | Có bước click, không thu nhãn/value; hai lần bấm không bị AI gộp làm một |
| Nhập xen giữa các frame | Nhập ô A, bấm nút trong frame khác, quay lại sửa A; thử thêm pause/resume | Giữ thứ tự fill/click/fill; gõ liên tiếp cùng ô chỉ ghi một bước; JSON khớp workbook thô |
| AI biên dịch recording | Xuất JSON, rà metadata, gửi AI trên UI rồi compose/prepare | Steps phù hợp Runner, đủ event mapping; review còn sau ghép, testcase chỉ header, không tự thêm settings |
| Preflight | Chạy workbook nháp chưa activate/testcase | ERROR với code/sheet/row, chưa mở browser |
| Executor | User tự nhập/activate một testcase thử có assertion, tạo run | Một process local thực thi; UI nhận số liệu, artifact chi tiết local |
| Mất mạng | Trong môi trường thử, ngắt nối agent/API rồi phục hồi | Journal gửi lại kết quả; không chạy lại testcase đã bắt đầu |
| Kết quả muộn | Sau khi run LOST, để agent gửi kết quả hoặc dùng --resend-run với journal đã hoàn tất | LOST giữ nguyên, late_result hiện riêng, không chạy testcase thêm lần nữa |
| Repair | Đề xuất target, hủy; thử lại và xác nhận | Hủy không tạo file; xác nhận tạo bản sao inactive, nguồn không đổi |
| Thử một step | Chạy try_step_runner.py trên dữ liệu thử, review rồi EXECUTE dòng đã chọn | Đúng một action, source giữ nguyên, report không có giá trị; lỗi sau bắt đầu không retry |
| Target thay đổi | Đổi layout trong lúc review repair | Identity thay đổi bị chặn; nếu vẫn cùng phần tử phải tự xác minh nghiệp vụ |
| Phân quyền | Hai tài khoản thử đọc run của nhau | User thường không đọc được run/artifact của người khác |
| Retention | Đối chiếu notification và hạn artifact | Có cảnh báo ít nhất 24h trước xóa; offline kéo dài hạn, không xóa metadata audit |

Không đổi đồng hồ hệ thống hoặc rút ngắn retention production để thử; nhánh thời gian
được kiểm thử bằng clock giả trong suite. Quan sát notification ở môi trường thử.

Các lệnh local tiêu biểu (người vận hành tự chọn file thử):

```powershell
python -B scripts/test_offline.py -x
python discover_runner.py --output discovery.json
python compose_runner.py --draft config/Login_Draft.xlsx --draft config/Search_Draft.xlsx --output config/Flow_Draft.xlsx
python prepare_runner.py --template config/Existing.xlsx --draft config/Flow_Draft.xlsx --output config/Prepared.xlsx
python preflight_runner.py --config config/Prepared.xlsx
python inspect_runner.py --config config/Prepared.xlsx --output inspection.json
```

Gửi lại **output đã che dữ liệu**, chỉ gồm: mã ca, đạt/không đạt, HTTP status,
preflight code/sheet/row, số PASS/FAIL/ERROR/UNVERIFIED và phiên bản đang chạy.
Nếu lỗi, gửi loại exception đã che nội dung; không gửi full traceback có input/URL.
Chưa đánh dấu nghiệm thu vận hành hoàn tất cho đến khi có kết quả các ca áp dụng.
