"""Validated workbook contract matching docs/runner.py; generated drafts stay inactive."""
from typing import Annotated, Literal
import re

from pydantic import BaseModel, ConfigDict, Field, model_validator

Identifier = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,49}$")]
Reference = Annotated[str, Field(pattern=r"^\$\{[A-Z][A-Z0-9_]{0,79}\}$")]
DataKey = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,109}$")]

STEP_COLUMNS = ["screen", "step", "action", "locator_type", "locator", "value_source",
                "active", "wait_selector", "dropdown_selector", "match_type",
                "prefill_check", "group", "read_method"]
VALUE_ACTIONS = {"fill", "force_fill", "fill_enter", "select", "select_antd",
                 "force_select_antd", "radio", "nth", "form_item", "fill_sequence"}
READ_ACTIONS = {"read_result", "read_result_group", "read_result_single"}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class WorkbookSettings(Strict):
    url: Literal["https://example.invalid"] = "https://example.invalid"
    screen_flow: str = Field(pattern=r"^[a-z][a-z0-9_]*(,[a-z][a-z0-9_]*)*$", max_length=2000)
    login_screen: Identifier
    result_screen: Identifier
    browser: Literal["chromium", "chrome", "msedge", "firefox", "webkit"] = "chromium"
    headless: Literal["Y", "N"] = "N"
    reuse_session: Literal["N"] = "N"
    parallel_workers: Literal[1] = 1
    slow_mo: int = Field(default=0, ge=0, le=2000)
    default_timeout: int = Field(default=10000, ge=1000, le=120000)
    spinner_timeout: int = Field(default=120000, ge=1000, le=180000)
    popup_timeout: int = Field(default=5000, ge=1000, le=30000)
    screenshot_on_error: Literal["Y", "N"] = "Y"
    debug: Literal["N"] = "N"
    run_filter: Literal[""] = ""
    # Site-specific settings are present but deliberately unresolved.
    popup_button: Literal[":not(*)"] = ":not(*)"
    step_wrapper_selector: Literal[":not(*)"] = ":not(*)"
    spinner_wrapper_class: Literal["RUNNER_REVIEW_REQUIRED"] = "RUNNER_REVIEW_REQUIRED"
    tick_class: Literal["RUNNER_REVIEW_REQUIRED"] = "RUNNER_REVIEW_REQUIRED"
    step_link_xpath: Literal["self::*[false()]"] = "self::*[false()]"
    block_trigger_selector: Literal["(?!)"] = "(?!)"
    result_wait_selector: Literal[""] = ""
    id_field_label: Literal["RUNNER_REVIEW_REQUIRED"] = "RUNNER_REVIEW_REQUIRED"
    id_field_value_selector: Literal[":not(*)"] = ":not(*)"
    spinner_stroke_color: Literal["RUNNER_REVIEW_REQUIRED"] = "RUNNER_REVIEW_REQUIRED"
    home_button_selector: Literal[":not(*)"] = ":not(*)"


class WorkbookStep(Strict):
    screen: Identifier
    step: Identifier
    action: Literal["fill", "force_fill", "fill_enter", "click", "click_if_exists", "check",
                    "radio", "select_antd", "force_select_antd", "select", "nth", "form_item",
                    "fill_sequence", "wait", "read_result", "read_result_single", "read_result_group"]
    locator_type: Literal["css"] = "css"
    locator: Literal[":not(*)"] = ":not(*)"
    value_source: Literal["testcase", "account", "empty", "keyword"]
    active: Literal["N"] = "N"
    wait_selector: Literal["", ":not(*)"] = ""
    dropdown_selector: Literal["", "visible", "not_hidden"] = ""
    match_type: Literal["", "exact", "contains"] = ""
    prefill_check: Literal["Y", "N"] = "N"
    group: Literal[""] = ""
    read_method: Literal["", "css_input", "css_disabled", "label_input", "label_span_title",
                         "button_regex", "sibling_span"] = ""

    @model_validator(mode="after")
    def coherent(self):
        if self.action in VALUE_ACTIONS:
            if self.value_source not in {"testcase", "account", "keyword"}:
                raise ValueError("Value action needs a reference")
            if self.value_source == "account" and self.step not in {"username", "password"}:
                raise ValueError("Account source only supports username/password")
        elif self.value_source != "empty":
            raise ValueError("Non-value action must use empty source")
        if self.action in READ_ACTIONS:
            if not self.step.startswith("read_") or self.step == "read_" or not self.read_method:
                raise ValueError("Read step requires read_ field name and method")
            if "read_" in self.step.removeprefix("read_"):
                raise ValueError("Repeated read_ prefix is ambiguous to the executor")
            if self.match_type not in {"", "exact"}:
                raise ValueError("Assertion comparison must be exact")
        elif self.read_method:
            raise ValueError("Read method only allowed on result actions")
        if self.action == "wait" and not self.wait_selector:
            raise ValueError("Wait requires a selector placeholder")
        return self


class WorkbookCase(Strict):
    tc_id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,79}$")
    mo_ta: str = Field(min_length=1, max_length=300)
    active: Literal["N"] = "N"
    role_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,29}$")
    specialized_bank: str = Field(default="", pattern=r"^(?:[A-Z][A-Z0-9_]{0,29})?$")
    data: dict[DataKey, Reference] = Field(default_factory=dict, max_length=100)
    expected: dict[DataKey, Reference] = Field(default_factory=dict, max_length=100)

    @model_validator(mode="after")
    def safe_description(self):
        if self.mo_ta.lstrip().startswith(("=", "+", "-", "@")) or re.search(
                r"(?i)(?:https?://|bearer\s+|(?:password|username|token|otp|mật\s*khẩu)\s*[:=])", self.mo_ta):
            raise ValueError("Unsafe case description")
        return self


class WorkbookPlan(Strict):
    settings: WorkbookSettings
    steps: list[WorkbookStep] = Field(min_length=1, max_length=100)
    testcases: list[WorkbookCase] = Field(min_length=1, max_length=25)

    @model_validator(mode="after")
    def cross_sheet_links(self):
        flow = self.settings.screen_flow.split(",")
        if len(set(flow)) != len(flow) or set(flow) != {s.screen for s in self.steps}:
            raise ValueError("Screen flow must match step screens exactly")
        if flow[0] != self.settings.login_screen or self.settings.login_screen == self.settings.result_screen:
            raise ValueError("Login must be first and distinct from result screen")
        names = [s.step for s in self.steps]
        if len(names) != len(set(names)):
            raise ValueError("Step names must be unique for data/expected mapping")
        if len({c.tc_id for c in self.testcases}) != len(self.testcases):
            raise ValueError("Duplicate testcase id")
        required_data = {s.step for s in self.steps if s.value_source == "testcase"}
        if any(s.value_source == "keyword" for s in self.steps):
            required_data.add("search_keyword")
        base_columns = {"tc_id", "mo_ta", "active", "role_code", "specialized_bank"}
        if required_data & base_columns:
            raise ValueError("Data field collides with testcase metadata")
        expected_fields = set()
        for step in self.steps:
            if step.action in READ_ACTIONS:
                if step.screen != self.settings.result_screen:
                    raise ValueError("Assertions must use result_screen")
                field = "expected_" + step.step.removeprefix("read_")
                expected_fields.add(field + ("_0" if step.action != "read_result_single" else ""))
        if required_data & expected_fields:
            raise ValueError("Data field collides with expected field")
        for case in self.testcases:
            if set(case.data) != required_data or set(case.expected) != expected_fields:
                raise ValueError("Testcase columns do not match steps")
        return self
