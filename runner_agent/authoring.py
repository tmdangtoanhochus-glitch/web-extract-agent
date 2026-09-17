"""Steps and testcase headers only. Settings and testcase data belong to users."""
import io
import re
from openpyxl import Workbook
from .config import validate_workbook
from src.runner.workbook_schema import STEP_COLUMNS, testcase_columns
from src.runner.scoped_locator import STRUCTURAL_SELECTOR, decode


class Recording:
    def __init__(self, limit=1000):
        self.events, self.limit, self.dropped = [], limit, 0
        self.screen_index, self.paused, self.suppressed = 1, False, 0
        self.assertion_screen = None
        self._last_fill = None

    @property
    def screen(self):
        return "recorded" if self.screen_index == 1 else f"recorded_{self.screen_index:03d}"

    def control(self, payload):
        if not isinstance(payload, dict) or set(payload) != {"control"}:
            return False
        if payload["control"] == "toggle_pause":
            self._last_fill = None
            self.paused = not self.paused
            return True
        if payload["control"] == "next_screen" and self.screen_index < 100:
            self._last_fill = None
            self.screen_index += 1
            return True
        return False

    def accept(self, payload):
        try:
            parts = decode(payload.get("locator")) if isinstance(payload, dict) else None
        except (ValueError, TypeError):
            parts = None
        if (not isinstance(payload, dict) or not {"action", "locator"} <= set(payload)
                or set(payload) - {"action", "locator", "widget", "related_locator"}
                or payload.get("action") not in ("click", "fill", "select", "wait", "read_result_single", "check", "uncheck", "upload")
                or not isinstance(payload.get("locator"), str)
                or len(payload["locator"]) > 2000
                or not parts):
            self.dropped += 1
            self._last_fill = None
            return False
        if "widget" in payload or "related_locator" in payload:
            from src.runner.recording_plan import RecordedEvent
            try:
                RecordedEvent(id=1, screen=self.screen, **payload)
            except ValueError:
                self.dropped += 1
                self._last_fill = None
                return False
        if self.paused:
            self._last_fill = None
            self.suppressed += 1
            return False
        fill = (self.screen, payload) if payload["action"] == "fill" else None
        if fill is not None and fill == self._last_fill:
            return True
        self._last_fill = None
        if len(self.events) >= self.limit:
            self.dropped += 1
            return False
        if payload["action"] in {"upload", "check", "uncheck"} and parts[-1]["css"].split(" > ")[-1].split(":")[0] != "input":
            self.dropped += 1
            return False
        if payload["action"] == "read_result_single":
            tag = parts[-1]["css"].split(" > ")[-1].split(":", 1)[0]
            if tag not in {"input", "textarea", "select"} or self.assertion_screen not in {None, self.screen}:
                self.dropped += 1
                return False
            self.assertion_screen = self.screen
        self.events.append({**payload, "screen": self.screen})
        if fill is not None:
            self._last_fill = (self.screen, dict(payload))
        return True


def draft_workbook(recording):
    rows = []
    for index, event in enumerate(recording.events, 1):
        if (not re.fullmatch(r"recorded(?:_[0-9]{3})?", event.get("screen", "")) or
                not Recording().accept({key: value for key, value in event.items() if key != "screen"})):
            raise ValueError("Invalid recording event")
        reading = event["action"] == "read_result_single"
        name = ("read_" if reading else "") + f"field_{index:04d}"
        rows.append(dict(zip(STEP_COLUMNS, [event["screen"], name, event["action"],
            "css", event["locator"], "testcase" if event["action"] in {"fill", "select", "upload"} else "empty",
            "N", event["locator"] if event["action"] == "wait" else "", "", "exact" if reading else "",
            "N", "", "css_input" if reading else ""])))
    return _workbook(rows, recording.dropped)


def planned_workbook(plan, result_blocks=1):
    from src.runner.workbook_schema import WorkbookPlan
    plan = WorkbookPlan.model_validate(plan.model_dump())
    return _workbook([step.model_dump() for step in plan.steps], result_blocks=result_blocks)


def _workbook(rows, dropped=0, result_blocks=1, compilation_notes=()):
    wb = Workbook()
    steps = wb.active
    steps.title = "steps"
    steps.append(STEP_COLUMNS)
    for row in rows:
        steps.append([row[key] for key in STEP_COLUMNS])
    cases = wb.create_sheet("testcases")
    headers = testcase_columns(rows, result_blocks)
    data = {s["step"] for s in rows if s["value_source"] == "testcase"}
    expected = {"expected_" + s["step"].removeprefix("read_") + suffix
                for s in rows if s["action"] in {"read_result", "read_result_group", "read_result_single"}
                for suffix in ([""] if s["action"] == "read_result_single" else [f"_{i}" for i in range(result_blocks)])}
    if data & expected:
        raise ValueError("Input field collides with an expected block header")
    cases.append(headers)
    notes = wb.create_sheet("review")
    notes.append(["item", "instruction"])
    explanations = {
        "NONE": "Đã đối chiếu action với bằng chứng; vẫn cần kiểm tra locator trên website.",
        "REVIEW_LOCATOR": "Chưa xác định chắc locator; dùng Inspector để chọn lại trước khi bật step.",
        "REVIEW_REPEAT": "Có thể là nhóm lặp; cần xác định locator theo chỉ số và dữ liệu testcase, chưa tự tạo group.",
        "REVIEW_CUSTOM_CONTROL": "Chưa đủ bằng chứng chọn action điều khiển tùy biến; cần rà soát thủ công.",
    }
    for note in compilation_notes:
        notes.append([note["step"], "events=" + ",".join(map(str, note["events"])) + "; " + note["review"] +
                      "; " + explanations[note["review"]]])
    for item in [
        ("scope", "Steps and testcase HEADERS only. Enter all testcase rows yourself."),
        ("settings", "No settings generated. Use prepare_runner.py with your existing config; changes require explanation and approval."),
        ("locators", "Review locators/read_method/wait/dropdown locally before activating any step."),
        ("credentials", "Use local account references/placeholders; never put real credentials in the workbook."),
        ("assertions", "Enter expected data yourself; read steps do not establish business expectations."),
        ("repeat_groups", "User enters semicolon-separated values in testcase cells. Review indexed locators locally; no values generated."),
        ("result_blocks", str(result_blocks)),
        ("dropped_events", str(dropped)),
    ]:
        notes.append(item)
    return _save_workbook(wb)


def _save_workbook(wb):
    for sheet in wb:
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
    output = io.BytesIO()
    wb.save(output)
    wb.close()
    content = output.getvalue()
    validate_workbook(content, require_settings=False)
    return content
