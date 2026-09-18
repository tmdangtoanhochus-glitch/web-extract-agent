"""Closed metadata contract: no workbook values, selectors or arbitrary messages."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Code = Literal["INVALID_WORKBOOK", "INVALID_HEADERS", "MISSING_SETTINGS_USE_PREPARE",
    "DUPLICATE_SETTING", "MISSING_OR_PLACEHOLDER_URL", "INVALID_URL", "NO_ACTIVE_STEPS",
    "ENTER_AND_ACTIVATE_USER_TESTCASES", "SCREEN_NOT_IN_FLOW", "UNRESOLVED_LOCATOR",
    "UNRESOLVED_WAIT", "RESULT_SCREEN_MISMATCH", "MISSING_OR_DUPLICATE_ID",
    "NO_ACTIVE_ASSERTIONS", "INVALID_ACTION", "INVALID_LOCATOR_TYPE", "INVALID_VALUE_SOURCE",
    "INVALID_REPEAT_GROUP"]


class Issue(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    sheet: Literal["workbook", "settings", "steps", "testcases"]
    row: int | None = Field(default=None, ge=1, le=1048576)
    code: Code


class PreflightReport(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    status: Literal["passed", "blocked"]
    active_steps: int = Field(ge=0, le=1048576)
    active_testcases: int = Field(ge=0, le=1048576)
    issues: list[Issue] = Field(max_length=100)
    warnings: list[Issue] = Field(max_length=100)
    truncated: bool = False

    @model_validator(mode="after")
    def consistent(self):
        if (self.status == "blocked") != bool(self.issues):
            raise ValueError("Preflight status inconsistent with issues")
        return self


def metadata(report):
    issues, warnings = report["issues"], report["warnings"]
    return PreflightReport(status="blocked" if issues else "passed",
        active_steps=report["active_steps"], active_testcases=report["active_testcases"],
        issues=issues[:100], warnings=warnings[:100], truncated=len(issues) > 100 or len(warnings) > 100
        ).model_dump(exclude_none=True)
