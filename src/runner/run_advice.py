"""Báo lỗi và gợi ý sửa cho một run Automation — chỉ dùng METADATA đã có trên server.

Contract preflight (`preflight_contract.py`) là metadata đóng: mã lỗi + sheet + số dòng, không có giá trị
workbook, selector hay mật khẩu; số ca PASS/FAIL/lỗi cũng chỉ là số đếm. Vì vậy gợi ý ở đây (rule-based và
AI) không bao giờ thấy dữ liệu nhạy cảm, và không tự sửa hay chạy lại gì (CLAUDE.md mục 1).
"""
from __future__ import annotations

ATTENTION_STATUSES = {"FAILED", "ERROR", "UNVERIFIED", "LOST"}

# Gợi ý cố định theo mã preflight — kiểm thử được, không phụ thuộc AI.
CODE_HINTS = {
    "INVALID_WORKBOOK": "File không đọc được hoặc thiếu sheet bắt buộc (settings, steps, testcases). Mở lại bằng Excel, "
                        "đối chiếu với workbook mẫu docs/samples/Sample_Inputs.xlsx rồi chạy preflight_runner.py ở máy local.",
    "INVALID_HEADERS": "Tiêu đề cột của sheet không đúng. Không đổi tên cột; thêm cột còn thiếu bằng prepare_runner.py.",
    "MISSING_SETTINGS_USE_PREPARE": "Thiếu key trong sheet settings. Chạy prepare_runner.py để bổ sung header/setting còn thiếu.",
    "DUPLICATE_SETTING": "Có key trùng trong sheet settings. Giữ đúng một dòng cho mỗi key.",
    "MISSING_OR_PLACEHOLDER_URL": "Sheet settings chưa có url thật (hoặc còn là giá trị giữ chỗ). Điền URL trang cần test.",
    "INVALID_URL": "url trong settings không hợp lệ. Dùng dạng https://... đầy đủ.",
    "NO_ACTIVE_STEPS": "Không có step nào active=Y. Bật (Y) các dòng cần chạy ở cột active của sheet steps.",
    "ENTER_AND_ACTIVATE_USER_TESTCASES": "Chưa có testcase nào active=Y. Tự nhập testcase (giá trị nhập và expected_*) rồi đặt active=Y.",
    "SCREEN_NOT_IN_FLOW": "Có step thuộc màn hình không nằm trong screen_flow của settings. Thêm màn hình vào screen_flow "
                          "hoặc sửa tên screen của step cho khớp.",
    "UNRESOLVED_LOCATOR": "Locator còn là giữ chỗ (:not(*)). Dùng Inspector/Repair hoặc Record để lấy locator thật rồi điền vào dòng đó.",
    "UNRESOLVED_WAIT": "Bước wait chưa có selector thật. Điền selector phần tử cần chờ hiển thị.",
    "RESULT_SCREEN_MISMATCH": "Các bước đọc kết quả (read_*) không nằm ở màn hình result_screen của settings. "
                              "Đặt result_screen đúng tên màn hình chứa bước đọc, hoặc chuyển bước đọc sang màn hình đó.",
    "MISSING_OR_DUPLICATE_ID": "tc_id trống hoặc trùng. Mỗi testcase cần một tc_id duy nhất (chữ, số, _ và -).",
    "NO_ACTIVE_ASSERTIONS": "Không có bước đọc kết quả nào đang bật, nên chạy xong sẽ là UNVERIFIED. Thêm bước read_* và cột expected_*.",
    "INVALID_ACTION": "action không thuộc danh sách hỗ trợ. Xem danh sách action trong khung 'Automation là gì?'.",
    "INVALID_LOCATOR_TYPE": "locator_type không hợp lệ. Dùng css (hoặc xpath, role, text, label...).",
    "INVALID_VALUE_SOURCE": "value_source không hợp lệ. Dùng testcase, account, empty hoặc keyword.",
    "INVALID_REPEAT_GROUP": "Cấu hình nhóm lặp (cột group) không hợp lệ. Nhóm lặp chỉ hỗ trợ fill/select với giá trị từ testcase, "
                            "hoặc click với value_source=empty.",
}

STATUS_HINTS = {
    "FAILED": "Có ca FAIL: giá trị đọc được khác expected_*. Mở file kết quả Excel ở thư mục runs của agent (máy local), "
              "xem cột real_* so với exp_*, kiểm tra ảnh chụp lỗi; xác định lỗi ở dữ liệu mong đợi hay ở website.",
    "ERROR": "Run lỗi khi chạy (không phải lệch kết quả). Nếu không có mục preflight bị chặn, xem log của agent ở máy local "
             "và ảnh chụp lỗi; hay gặp: locator không còn khớp (chạy Inspector), website chậm (tăng default_timeout), "
             "chưa đăng nhập được (kiểm tra runner.env).",
    "UNVERIFIED": "Chạy xong nhưng không có giá trị mong đợi để so nên không kết luận được. Thêm bước read_* và điền cột expected_*.",
    "LOST": "Server mất theo dõi run (agent ngừng báo trong 5 phút hoặc run chờ quá 24 giờ). Kiểm tra agent còn chạy không "
            "và xem journal (--journal-status) trước khi tạo run khác; thao tác trên website có thể đã xảy ra.",
}


def needs_attention(run: dict) -> bool:
    preflight = run.get("preflight") or {}
    return run.get("status") in ATTENTION_STATUSES or preflight.get("status") == "blocked"


def run_metadata(run: dict) -> dict:
    """Bản tóm tắt an toàn của run: trạng thái, số đếm, mã preflight (không giá trị workbook)."""
    preflight = run.get("preflight") or (run.get("late_result") or {}).get("preflight") or {}
    meta = {"run_id": run.get("run_id"), "status": run.get("status"),
            **{key: run.get(key) for key in ("passed", "failed", "errors", "unverified", "duration")}}
    if preflight:
        meta["preflight"] = {
            "status": preflight.get("status"),
            "active_steps": preflight.get("active_steps"), "active_testcases": preflight.get("active_testcases"),
            "issues": [{key: item.get(key) for key in ("sheet", "row", "code")} for item in preflight.get("issues", [])[:30]],
            "warnings": [{key: item.get(key) for key in ("sheet", "row", "code")} for item in preflight.get("warnings", [])[:30]],
        }
    if run.get("late_result"):
        meta["late_result_status"] = run["late_result"].get("status")
    return meta


def rule_based_hints(meta: dict) -> list[str]:
    hints = []
    preflight = meta.get("preflight") or {}
    seen = set()
    for item in preflight.get("issues", []):
        code = item.get("code")
        if code in seen or code not in CODE_HINTS:
            continue
        seen.add(code)
        where = f" (sheet {item.get('sheet')}" + (f", dòng {item['row']})" if item.get("row") else ")")
        hints.append(f"{code}{where}: {CODE_HINTS[code]}")
    if meta.get("status") in STATUS_HINTS and not (meta.get("status") == "ERROR" and preflight.get("status") == "blocked"):
        hints.append(f"{meta['status']}: {STATUS_HINTS[meta['status']]}")
    return hints
