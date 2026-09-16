"""Convert structural recording to an inactive workbook, without page content."""
import io
import re

from openpyxl import Workbook

from runner_agent.config import validate_workbook

STRUCTURAL_SELECTOR = re.compile(
    r"[a-z][a-z0-9-]*:nth-of-type\([1-9][0-9]{0,5}\)"
    r"(?: > [a-z][a-z0-9-]*:nth-of-type\([1-9][0-9]{0,5}\)){0,39}")


class Recording:
    def __init__(self, limit=1000):
        self.events = []
        self.limit = limit
        self.dropped = 0

    def accept(self, payload):
        # Strict allowlist; never preserve unknown fields, even in diagnostics.
        if (not isinstance(payload, dict) or set(payload) != {"action", "locator"}
                or payload.get("action") not in ("click", "fill", "select")
                or not isinstance(payload.get("locator"), str)
                or len(payload["locator"]) > 2000
                or not STRUCTURAL_SELECTOR.fullmatch(payload["locator"])):
            self.dropped += 1
            return False
        if len(self.events) >= self.limit:
            self.dropped += 1
            return False
        self.events.append(dict(payload))
        return True


def draft_workbook(recording):
    """No URL or credentials copied; user must review and activate explicitly."""
    for event in recording.events:
        if not Recording().accept(event):
            raise ValueError("Invalid recording event")
    return _workbook(recording.events, recording.dropped)


def planned_workbook(plan):
    """No invented locators: :not(*) matches nothing until manually replaced."""
    from src.runner.planner import Plan
    plan = Plan.model_validate(plan.model_dump())
    from src.runner.workbook_schema import STEP_COLUMNS
    wb = Workbook()
    settings = wb.active
    settings.title = "settings"
    settings.append(["key", "value"])
    for key, value in plan.settings.model_dump().items():
        settings.append([key, str(value)])
    steps = wb.create_sheet("steps")
    steps.append(STEP_COLUMNS)
    for step in plan.steps:
        values = step.model_dump()
        steps.append([values[key] for key in STEP_COLUMNS])
    cases = wb.create_sheet("testcases")
    data_columns = list(plan.testcases[0].data)
    expected_columns = list(plan.testcases[0].expected)
    base_columns = ["tc_id", "mo_ta", "active", "role_code", "specialized_bank"]
    cases.append(base_columns + data_columns + expected_columns)
    for case in plan.testcases:
        values = case.model_dump()
        cases.append([values[key] for key in base_columns] +
                     [case.data[key] for key in data_columns] + [case.expected[key] for key in expected_columns])
    notes = wb.create_sheet("review")
    notes.append(["item", "instruction"])
    notes.append(["status", "DRAFT: all steps and testcases inactive; no browser inspection or execution"])
    notes.append(["settings", "Review URL and every site-specific selector/class/label in settings"])
    notes.append(["locators", "Replace :not(*) and validate locator_type, read_method, wait and dropdown selectors locally"])
    notes.append(["data", "Map all data and expected placeholders to local variables; review every scenario"])
    notes.append(["account", "role_code/specialized_bank resolve local USERNAME/PASSWORD, never write credentials here"])
    notes.append(["assertions", "Assertions are drafts; verify business expectations and group/block mappings before enabling"])
    if not expected_columns:
        notes.append(["missing_assertions", "No requested assertions generated: execution will be UNVERIFIED without checks"])
    return _save_workbook(wb)


def _workbook(events, dropped):
    screen = "recorded"
    wb = Workbook()
    settings = wb.active
    settings.title = "settings"
    settings.append(["key", "value"])
    from src.runner.workbook_schema import STEP_COLUMNS, WorkbookSettings
    for key, value in WorkbookSettings(screen_flow=screen, login_screen=screen,
                                       result_screen="result").model_dump().items():
        settings.append([key, str(value)])
    steps = wb.create_sheet("steps")
    steps.append(STEP_COLUMNS)
    fields = []
    for index, event in enumerate(events, 1):
        name = f"field_{index:04d}"
        needs_value = event["action"] in ("fill", "select")
        steps.append([screen, name, event["action"], "css", event["locator"],
                      "testcase" if needs_value else "empty", "N", "", "", "", "N", "", ""])
        if needs_value:
            fields.append(name)
    cases = wb.create_sheet("testcases")
    cases.append(["tc_id", "mo_ta", "active", "role_code", "specialized_bank", *fields])
    cases.append(["RECORDED_001", "Review locators, input references and assertions", "N", "", "",
                  *(f"${{REC_{field.upper()}}}" for field in fields)])
    notes = wb.create_sheet("review")
    notes.append(["item", "instruction"])
    for row in [
        ("status", "DRAFT: no step or testcase is active"),
        ("url", "Set the start URL locally; no navigation URL was captured"),
        ("locators", "Review structural CSS; layout changes can invalidate it"),
        ("inputs", "Map placeholders to local environment variables; never store real credentials here"),
        ("assertions", "Add read_result assertions before treating execution as a verified test"),
        ("unsupported", "Add iframe, shadow DOM, upload, checkbox, radio and custom controls manually"),
        ("dropped_events", str(dropped)),
    ]:
        notes.append(row)
    return _save_workbook(wb)


def _save_workbook(wb):
    for sheet in wb:
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
    output = io.BytesIO()
    wb.save(output)
    wb.close()
    content = output.getvalue()
    validate_workbook(content)
    return content
