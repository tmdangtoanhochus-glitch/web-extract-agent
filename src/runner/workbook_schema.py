"""Generate steps only; derive testcase headers, never testcase rows or settings."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Identifier = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,49}$")]
STEP_COLUMNS = ["screen", "step", "action", "locator_type", "locator", "value_source",
                "active", "wait_selector", "dropdown_selector", "match_type", "prefill_check", "group", "read_method"]
BASE_CASE_COLUMNS = ["tc_id", "mo_ta", "active", "role_code", "specialized_bank"]
VALUE_ACTIONS = {"fill", "force_fill", "fill_enter", "select", "select_antd", "force_select_antd", "radio", "nth", "form_item", "fill_sequence", "upload"}
READ_ACTIONS = {"read_result", "read_result_group", "read_result_single"}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class WorkbookStep(Strict):
    screen: Identifier
    step: Identifier
    action: Literal["fill", "force_fill", "fill_enter", "click", "click_if_exists", "check", "uncheck", "upload", "radio", "select_antd", "force_select_antd", "select", "nth", "form_item", "fill_sequence", "wait", "read_result", "read_result_single", "read_result_group"]
    locator_type: Literal["css"] = "css"
    locator: Literal[":not(*)"] = ":not(*)"
    value_source: Literal["testcase", "account", "empty", "keyword"]
    active: Literal["N"] = "N"
    wait_selector: Literal["", ":not(*)"] = ""
    dropdown_selector: Literal["", "visible", "not_hidden"] = ""
    match_type: Literal["", "exact", "contains"] = ""
    prefill_check: Literal["Y", "N"] = "N"
    group: Annotated[str, Field(pattern=r"^(?:[a-z][a-z0-9_]{0,49})?$")] = ""
    read_method: Literal["", "css_input", "css_disabled", "label_input", "label_span_title", "button_regex", "sibling_span"] = ""

    @model_validator(mode="after")
    def coherent(self):
        if self.action == "upload" and self.value_source != "testcase":
            raise ValueError("Upload file must be supplied by the user in testcase")
        if self.group:
            # run_repeat_group has a narrower action dispatcher than run_step.
            if not ((self.action in {"fill", "fill_enter", "select", "select_antd", "force_select_antd"}
                     and self.value_source == "testcase") or
                    (self.action == "click" and self.value_source == "empty")):
                raise ValueError("Repeat group supports testcase values or an empty click only")
        if self.action in VALUE_ACTIONS:
            if self.value_source not in {"testcase", "account", "keyword"}:
                raise ValueError("Value action needs a reference")
            if self.value_source == "account" and self.step not in {"username", "password"}:
                raise ValueError("Account source only supports username/password")
        elif self.value_source != "empty":
            raise ValueError("Non-value action must use empty source")
        if self.action in READ_ACTIONS:
            if (not self.step.startswith("read_") or self.step == "read_" or not self.read_method
                    or "read_" in self.step.removeprefix("read_")):
                raise ValueError("Read step requires unambiguous read_ name and method")
            if self.match_type not in {"", "exact"}:
                raise ValueError("Assertion comparison must be exact")
        elif self.read_method:
            raise ValueError("Read method only allowed on result actions")
        if self.action == "wait" and not self.wait_selector:
            raise ValueError("Wait requires a selector placeholder")
        return self


def testcase_columns(steps, result_blocks=1):
    if type(result_blocks) is not int or not 1 <= result_blocks <= 100:
        raise ValueError("Choose 1..100 result blocks")
    columns = list(BASE_CASE_COLUMNS)
    for step in steps:
        name = None
        if step["value_source"] == "testcase":
            name = step["step"]
        elif step["value_source"] == "keyword":
            name = "search_keyword"
        elif step["action"] in READ_ACTIONS:
            name = "expected_" + step["step"].removeprefix("read_")
            if step["action"] != "read_result_single":
                for index in range(result_blocks):
                    if f"{name}_{index}" not in columns:
                        columns.append(f"{name}_{index}")
                continue
        if name and name not in columns:
            columns.append(name)
    if len(columns) > 16384:
        raise ValueError("Too many testcase columns for Excel")
    return columns


def header_result_blocks(steps, headers):
    """Validate complete header-only drafts, including explicit expected block count."""
    for count in range(1, 101):
        if headers == testcase_columns(steps, count):
            return count
    raise ValueError("Testcase headers do not match steps and contiguous result blocks")


class WorkbookPlan(Strict):
    steps: list[WorkbookStep] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def check_links(self):
        names = [step.step for step in self.steps]
        if len(names) != len(set(names)):
            raise ValueError("Step names must be unique")
        data = {step.step for step in self.steps if step.value_source == "testcase"}
        if data & set(BASE_CASE_COLUMNS):
            raise ValueError("Data field collides with testcase metadata")
        expected = {"expected_" + step.step.removeprefix("read_") +
                    ("_0" if step.action != "read_result_single" else "")
                    for step in self.steps if step.action in READ_ACTIONS}
        if data & expected:
            raise ValueError("Data field collides with expected field")
        if len({s.screen for s in self.steps if s.action in READ_ACTIONS}) > 1:
            raise ValueError("Executor supports one result screen per workbook")
        groups = {}
        previous = None
        closed = set()
        for step in self.steps:
            if step.group != previous:
                if previous:
                    closed.add(previous)
                if step.group and step.group in closed:
                    raise ValueError("Repeat group steps must be contiguous")
                previous = step.group
            if step.group:
                groups.setdefault(step.group, []).append(step)
        for members in groups.values():
            if len({s.screen for s in members}) != 1 or not any(s.value_source == "testcase" for s in members):
                raise ValueError("Repeat group needs testcase values on one screen")
        return self
